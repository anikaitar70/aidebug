"""
Retrieval quality evaluation for ML/classification queries.

Run: python test_retrieval_quality.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Synthetic repository mimicking the reported failure case
SYNTHETIC_FILES = {
    "frontend/src/App.js": '''import React, { useState } from 'react';
import { classifyText } from '../api/client';

function App() {
  const [text, setText] = useState('');
  const [label, setLabel] = useState('');

  const handleClassify = async () => {
    const result = await classifyText(text);
    setLabel(result.label);
  };

  return (
    <div className="app">
      <h1>Text Classifier UI</h1>
      <textarea value={text} onChange={e => setText(e.target.value)} />
      <button onClick={handleClassify}>Classify Text</button>
      <p>Result: {label}</p>
    </div>
  );
}

export default App;
''',
    "frontend/src/App.test.js": '''import { render, screen } from '@testing-library/react';
import App from './App';

test('renders classify button', () => {
  render(<App />);
  expect(screen.getByText(/Classify Text/i)).toBeInTheDocument();
});
''',
    "node_modules/yaml/dist/index.js": '''// yaml parser dependency
function classifySchema(tag) {
  return tag === '!!str' ? 'string' : 'unknown';
}
module.exports = { classifySchema };
''',
    "node_modules/xmlchars/xmlchars.js": '''// xml character classification tables
function classifyChar(code) {
  if (code < 32) return 'control';
  return 'text';
}
module.exports = { classifyChar };
''',
    "backend/classifier.py": '''"""Text classification model implementation."""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
import joblib

class TextClassifier:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=5000)
        self.model = MultinomialNB()

    def train(self, texts, labels):
        X = self.vectorizer.fit_transform(texts)
        self.model.fit(X, labels)

    def classify_text(self, text: str) -> str:
        """Classify input text into a category label."""
        X = self.vectorizer.transform([text])
        return self.model.predict(X)[0]

    def predict_proba(self, text: str):
        X = self.vectorizer.transform([text])
        return self.model.predict_proba(X)[0]
''',
    "backend/model.py": '''"""Model loading and inference."""
import joblib
from backend.classifier import TextClassifier

_model = None

def load_model(path: str = "models/classifier.joblib"):
    global _model
    _model = joblib.load(path)
    return _model

def predict(text: str) -> dict:
    """Run prediction on input text."""
    if _model is None:
        load_model()
    label = _model.classify_text(text)
    proba = _model.predict_proba(text)
    return {"label": label, "confidence": float(max(proba))}
''',
    "backend/services/predict.py": '''"""Prediction service layer."""
from backend.model import predict as run_predict

def predict_text(text: str) -> dict:
    """Service entry point for text prediction."""
    if not text.strip():
        return {"error": "empty input"}
    return run_predict(text)
''',
    "backend/train.py": '''"""Training pipeline."""
from backend.classifier import TextClassifier

def train_model(dataset_path: str):
    texts, labels = load_dataset(dataset_path)
    clf = TextClassifier()
    clf.train(texts, labels)
    return clf
''',
}

EVAL_QUERIES = [
    "How does it classify the text?",
    "Which model is used?",
    "How does prediction work?",
    "Trace inference flow.",
]


async def index_synthetic_repo(session_id: str, apply_filters: bool = True) -> dict:
    from app.api.upload import process_uploaded_file
    from app.utils.path_filters import audit_indexed_paths, should_index_path

    indexed_paths = []
    skipped_paths = []

    for rel_path, content in SYNTHETIC_FILES.items():
        if apply_filters and not should_index_path(rel_path):
            skipped_paths.append(rel_path)
            continue
        file_id = str(uuid.uuid4())
        await process_uploaded_file(
            session_id=session_id,
            file_id=file_id,
            filename=Path(rel_path).name,
            content=content.encode("utf-8"),
            relative_path=rel_path,
        )
        indexed_paths.append(rel_path)

    audit = audit_indexed_paths(indexed_paths)
    audit["skipped_paths"] = skipped_paths
    audit["apply_filters"] = apply_filters
    return audit


async def run_evaluation() -> None:
    from app.services.embedding_service import get_embedding_service
    from app.services.retrieval_service import get_retrieval_service
    from app.services.session_store import get_session_store

    session_id = f"eval_{uuid.uuid4().hex[:24]}"
    get_session_store().get_or_create(session_id)

    print("=" * 72)
    print("PHASE 2 — REPOSITORY INDEXING AUDIT")
    print("=" * 72)

    # Audit without filters (simulates old behavior)
    unfiltered_audit = await index_synthetic_repo(f"{session_id}_unfiltered", apply_filters=False)
    print("\nWithout path filters (legacy behavior):")
    print(json.dumps(unfiltered_audit, indent=2))

    # Audit with filters (new behavior)
    filtered_audit = await index_synthetic_repo(session_id, apply_filters=True)
    print("\nWith path filters (new behavior):")
    print(json.dumps(filtered_audit, indent=2))

    embedding_service = await get_embedding_service()
    retrieval_service = await get_retrieval_service()

    print("\n" + "=" * 72)
    print("PHASE 1 & 9 — RETRIEVAL TRACE + EVALUATION")
    print("=" * 72)

    all_results = {}
    for query in EVAL_QUERIES:
        print(f"\n--- Query: {query!r} ---")
        query_embedding = await embedding_service.embed_text(query)
        trace = await retrieval_service.trace_retrieval(
            session_id=session_id,
            query_embedding=query_embedding,
            query_text=query,
            top_k=5,
        )

        print(f"Intent: {trace['intent']}")
        print(f"Answerable: {trace['answerable']} ({trace['answerability_reason']})")

        print("\nRaw vector search (top 5):")
        for r in trace["raw_vector_results"][:5]:
            print(f"  sim={r['vector_similarity']:.3f}  {r['file_path']}  fn={r['function_name']}")

        print("\nReranked (top 5):")
        for r in trace["reranked_results"][:5]:
            print(
                f"  rank={r['rank_score']:.3f}  imp={r['path_importance']:.2f}  "
                f"{r['file_path']}  fn={r['function_name']}"
            )

        print("\nFinal returned chunks:")
        for r in trace["final_results"]:
            print(
                f"  sim={r['similarity']:.3f}  [{r['context_group']}]  "
                f"{r['file_path']}  fn={r['function_name']}"
            )

        retrieved_files = [r["file_path"] for r in trace["final_results"]]
        has_impl = any(
            any(k in f for k in ("classifier", "model", "predict", "train"))
            for f in retrieved_files
        )
        has_noise = any(
            "node_modules" in f or f.endswith("App.js") or f.endswith("App.test.js")
            for f in retrieved_files
        )
        quality = "PASS" if has_impl and not has_noise else "FAIL"
        print(f"\nQuality: {quality}  (impl={has_impl}, noise={has_noise})")

        all_results[query] = {
            "intent": trace["intent"],
            "retrieved_files": retrieved_files,
            "retrieved_functions": [r["function_name"] for r in trace["final_results"]],
            "answerable": trace["answerable"],
            "quality": quality,
        }

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    passed = sum(1 for r in all_results.values() if r["quality"] == "PASS")
    print(f"Queries passing: {passed}/{len(EVAL_QUERIES)}")
    print(json.dumps(all_results, indent=2))


if __name__ == "__main__":
    asyncio.run(run_evaluation())
