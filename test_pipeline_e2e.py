"""
End-to-end pipeline test simulating stale session + re-index fix.

Run: python test_pipeline_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

SYNTHETIC_FILES = {
    "frontend/src/App.js": "function handleClassify() { return classifyText(input); }",
    "frontend/src/App.test.js": "test('classify', () => expect(handleClassify()).toBeDefined());",
    "node_modules/yaml/dist/index.js": "function classifySchema(t) { return t; }",
    "backend/classifier.py": '''def classify_text(text):
    """Classify text using sklearn."""
    from sklearn.naive_bayes import MultinomialNB
    return model.predict(vectorizer.transform([text]))[0]
''',
    "backend/model.py": "def load_model(): return joblib.load('model.joblib')\ndef predict(t): return load_model().predict(t)",
}

BENCHMARK_QUERIES = [
    "How does it classify the text?",
    "Which model is used?",
    "Trace the prediction flow.",
    "How is inference performed?",
]


async def index_files(session_id: str, files: dict, apply_filters: bool) -> int:
    from app.api.upload import process_uploaded_file
    from app.utils.path_filters import should_index_path

    total = 0
    for rel_path, content in files.items():
        if apply_filters and not should_index_path(rel_path):
            continue
        n = await process_uploaded_file(
            session_id=session_id,
            file_id=str(uuid.uuid4()),
            filename=Path(rel_path).name,
            content=content.encode(),
            relative_path=rel_path,
        )
        total += n
    return total


async def run_query_debug(session_id: str, query: str) -> dict:
    from app.services.embedding_service import get_embedding_service
    from app.services.retrieval_service import get_retrieval_service
    from app.services.query_classifier import classify_query_intent

    embedding_service = await get_embedding_service()
    retrieval_service = await get_retrieval_service()
    emb = await embedding_service.embed_text(query)
    trace = await retrieval_service.trace_retrieval(session_id, emb, query, top_k=5)
    final = await retrieval_service.retrieve_similar(
        session_id=session_id,
        query_embedding=emb,
        query_text=query,
        top_k=5,
        enhanced=True,
    )
    llm_ctx = retrieval_service.build_llm_context_preview(final)
    intent = classify_query_intent(query)
    answerable, reason = retrieval_service.check_answerability(final, intent, query)
    audit = retrieval_service.get_index_audit(session_id)

    return {
        "query": query,
        "intent": trace.get("intent"),
        "index_audit_summary": {
            "total_chunks": audit["total_chunks"],
            "node_modules_chunks": audit["node_modules_chunks"],
            "has_stale": audit["has_stale_excluded_paths"],
        },
        "raw_top3": [r["file_path"] for r in trace.get("raw_vector_results", [])[:3]],
        "final_files": [r["file_path"] for r in trace.get("final_results", [])],
        "final_functions": [r["function_name"] for r in trace.get("final_results", [])],
        "llm_context_files": [c["file_path"] for c in llm_ctx["chunks"]],
        "llm_estimated_tokens": llm_ctx["estimated_tokens"],
        "answerable": answerable,
        "answerability_reason": reason,
    }


async def main() -> None:
    from app.services.session_store import get_session_store

    print("=" * 72)
    print("STALE SESSION SIMULATION (append without clear — old behavior)")
    print("=" * 72)

    stale_session = f"stale_{uuid.uuid4().hex[:20]}"
    get_session_store().get_or_create(stale_session)

    # First upload: unfiltered (simulates pre-patch index with node_modules)
    await index_files(stale_session, SYNTHETIC_FILES, apply_filters=False)
    audit1 = (await run_query_debug(stale_session, BENCHMARK_QUERIES[0]))["index_audit_summary"]
    print(f"After unfiltered index: {json.dumps(audit1)}")

  # Second upload: filtered but WITHOUT clear (simulates re-upload bug)
    await index_files(stale_session, {
        k: v for k, v in SYNTHETIC_FILES.items() if "node_modules" not in k
    }, apply_filters=True)
    stale_result = await run_query_debug(stale_session, BENCHMARK_QUERIES[0])
    print(f"\nQuery after APPEND re-upload (stale bug):")
    print(f"  raw_top3:      {stale_result['raw_top3']}")
    print(f"  final_files:   {stale_result['final_files']}")
    print(f"  llm_context:   {stale_result['llm_context_files']}")
    print(f"  answerable:    {stale_result['answerable']} ({stale_result['answerability_reason']})")

    print("\n" + "=" * 72)
    print("FIXED SESSION (clear on re-index)")
    print("=" * 72)

    fixed_session = f"fixed_{uuid.uuid4().hex[:20]}"
    get_session_store().get_or_create(fixed_session)
    await index_files(fixed_session, SYNTHETIC_FILES, apply_filters=False)
    get_session_store().clear_session(fixed_session)  # simulates index_extracted_zip clear
    await index_files(fixed_session, SYNTHETIC_FILES, apply_filters=True)

    print("\nBENCHMARK QUERIES (fixed session):")
    results = {}
    for q in BENCHMARK_QUERIES:
        r = await run_query_debug(fixed_session, q)
        results[q] = r
        has_impl = any("classifier" in f or "model" in f or "predict" in f for f in r["llm_context_files"])
        has_noise = any("node_modules" in f or f.endswith("App.test.js") for f in r["llm_context_files"])
        status = "PASS" if has_impl and not has_noise else "FAIL"
        print(f"\n  [{status}] {q}")
        print(f"    final:   {r['final_files']}")
        print(f"    llm_ctx: {r['llm_context_files']}")
        print(f"    fns:     {r['final_functions']}")

    passed = sum(
        1 for r in results.values()
        if any("classifier" in f or "model" in f for f in r["llm_context_files"])
        and not any("node_modules" in f for f in r["llm_context_files"])
    )
    print(f"\n{'=' * 72}")
    print(f"FIXED SESSION: {passed}/{len(BENCHMARK_QUERIES)} queries send ML code to Gemini")
    print(json.dumps({q: {"llm_context_files": r["llm_context_files"]} for q, r in results.items()}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
