"""
Precision evaluation benchmark — before/after intent-aware retrieval.

Usage:
    python benchmarks/precision_benchmark.py
"""

import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from create_sample_project import create_sample_zip
from app.services.code_parser import CodeParser
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService


@dataclass
class PrecisionCase:
    query: str
    expected_symbols: Set[str] = field(default_factory=set)
    forbidden_symbols: Set[str] = field(default_factory=set)
    expected_files: Set[str] = field(default_factory=set)
    min_precision: float = 0.6


EVAL_CASES = [
    PrecisionCase(
        query="Which functions create JWT tokens?",
        expected_symbols={"generateJWT"},
        forbidden_symbols={"verify_password", "create_session", "authenticate_user", "handleGetProfile"},
        expected_files={"handlers.js"},
        min_precision=0.8,
    ),
    PrecisionCase(
        query="What happens when authentication fails?",
        expected_symbols={"handleLogin", "authenticate_user"},
        forbidden_symbols={"generateJWT", "handleGetProfile", "create_session"},
        expected_files={"handlers.js", "main.py"},
        min_precision=0.6,
    ),
    PrecisionCase(
        query="Trace login flow from request to JWT.",
        expected_symbols={"handleLogin", "generateJWT", "authenticate_user"},
        forbidden_symbols={"handleGetProfile", "create_session"},
        expected_files={"handlers.js"},
        min_precision=0.6,
    ),
    PrecisionCase(
        query="Which files participate in authentication?",
        expected_symbols={"handleLogin", "authenticate_user", "verify_password"},
        forbidden_symbols={"handleGetProfile"},
        expected_files={"handlers.js", "main.py"},
        min_precision=0.5,
    ),
    PrecisionCase(
        query="Generate repository architecture summary.",
        expected_symbols=set(),
        forbidden_symbols=set(),
        expected_files={"main.py", "handlers.js", "config.json"},
        min_precision=0.4,
    ),
]


async def index_sample(retrieval: RetrievalService, embedding: EmbeddingService, session_id: str) -> int:
    import io
    import zipfile

    count = 0
    zip_data = create_sample_zip()
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            content = zf.read(name).decode("utf-8", errors="ignore")
            fid = str(uuid.uuid4())
            lang = CodeParser.get_language(name)
            for chunk in CodeParser.parse_by_functions(content, lang, name):
                meta = CodeParser.build_chunk_metadata(chunk, fid, name, lang)
                vec = await embedding.embed_text(CodeParser.build_embedding_text(chunk, name))
                await retrieval.store_embedding(session_id, str(uuid.uuid4()), chunk.content, vec, meta)
                count += 1
    return count


def evaluate(case: PrecisionCase, results: List[Dict]) -> Dict:
    symbols_found: Set[str] = set()
    files_found: Set[str] = set()
    forbidden_hit = 0

    for item in results:
        meta = item.get("metadata", {})
        fn = str(meta.get("function_name") or "")
        if fn:
            symbols_found.add(fn)
        fp = str(meta.get("file_path") or meta.get("filename") or "")
        if fp:
            files_found.add(Path(fp).name)

        for bad in case.forbidden_symbols:
            if fn == bad:
                forbidden_hit += 1

    sym_hits = case.expected_symbols & symbols_found
    file_hits = case.expected_files & files_found

    sym_precision = len(sym_hits) / max(len(case.expected_symbols), 1) if case.expected_symbols else 1.0
    file_precision = len(file_hits) / max(len(case.expected_files), 1) if case.expected_files else 1.0
    noise_penalty = forbidden_hit / max(len(results), 1)

    precision = (sym_precision * 0.6 + file_precision * 0.4) * (1.0 - noise_penalty)
    passed = precision >= case.min_precision and forbidden_hit == 0

    return {
        "query": case.query,
        "retrieved": len(results),
        "symbols_found": sorted(sym_hits),
        "symbols_missed": sorted(case.expected_symbols - symbols_found),
        "forbidden_hit": forbidden_hit,
        "files_found": sorted(file_hits),
        "precision": round(precision, 3),
        "passed": passed,
        "top": [
            {
                "file": r.get("metadata", {}).get("file_path"),
                "function": r.get("metadata", {}).get("function_name"),
                "group": r.get("context_group"),
            }
            for r in results[:6]
        ],
    }


async def run() -> Dict:
    embedding = EmbeddingService()
    retrieval = RetrievalService()
    session_id = "precision-eval"
    indexed = await index_sample(retrieval, embedding, session_id)

    cases = []
    total_precision = 0.0
    passed = 0

    for case in EVAL_CASES:
        vec = await embedding.embed_text(case.query)
        results = await retrieval.retrieve_similar(
            session_id=session_id,
            query_embedding=vec,
            top_k=5,
            query_text=case.query,
            enhanced=True,
        )
        report = evaluate(case, results)
        cases.append(report)
        total_precision += report["precision"]
        if report["passed"]:
            passed += 1

    return {
        "chunks_indexed": indexed,
        "cases": cases,
        "aggregate_precision": round(total_precision / len(EVAL_CASES), 3),
        "passed": passed,
        "total": len(EVAL_CASES),
    }


def main() -> None:
    report = asyncio.run(run())
    print("=" * 72)
    print("PRECISION EVALUATION — Intent-Aware Retrieval")
    print("=" * 72)
    print(f"Chunks indexed: {report['chunks_indexed']}")
    print(f"Aggregate precision: {report['aggregate_precision']}")
    print(f"Passed: {report['passed']}/{report['total']}")
    print()

    for case in report["cases"]:
        status = "PASS" if case["passed"] else "FAIL"
        print(f"[{status}] {case['query']}")
        print(f"  precision={case['precision']}  forbidden_hits={case['forbidden_hit']}")
        print(f"  symbols: {case['symbols_found']}  missed: {case['symbols_missed']}")
        print(f"  top results:")
        for item in case["top"]:
            print(f"    - {item['file']} :: {item['function']} [{item['group']}]")
        print()

    out = ROOT / "benchmarks" / "precision_benchmark_results.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Results written to {out}")


if __name__ == "__main__":
    main()
