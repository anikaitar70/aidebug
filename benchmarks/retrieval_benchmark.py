"""
Retrieval quality benchmark: baseline vs enhanced pipeline.

Usage:
    python benchmarks/retrieval_benchmark.py
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
class BenchmarkCase:
    query: str
    expected_files: Set[str] = field(default_factory=set)
    expected_symbols: Set[str] = field(default_factory=set)
    expected_content: Set[str] = field(default_factory=set)
    min_top_k: int = 5


BENCHMARK_CASES = [
    BenchmarkCase(
        query="How does authentication work?",
        expected_files={"main.py"},
        expected_symbols={"authenticate_user", "verify_password"},
        expected_content={"password", "user"},
    ),
    BenchmarkCase(
        query="What happens when authentication fails?",
        expected_files={"handlers.js", "main.py"},
        expected_symbols={"handleLogin", "authenticate_user", "verify_password"},
        expected_content={"401", "Invalid credentials"},
        min_top_k=8,
    ),
    BenchmarkCase(
        query="Which files participate in login?",
        expected_files={"handlers.js", "main.py"},
        expected_symbols={"handleLogin", "authenticate_user"},
        min_top_k=10,
    ),
    BenchmarkCase(
        query="Trace authentication from request to database.",
        expected_files={"handlers.js", "main.py"},
        expected_symbols={"handleLogin", "authenticate_user", "verify_password"},
        expected_content={"401", "get_user", "database"},
        min_top_k=12,
    ),
    BenchmarkCase(
        query="Explain the repository architecture.",
        expected_files={"main.py", "handlers.js", "config.json"},
        min_top_k=10,
    ),
]


async def index_sample_project(
    retrieval: RetrievalService,
    embedding: EmbeddingService,
    session_id: str,
    use_enriched: bool = True,
) -> int:
    """Index sample_project.zip contents into a retrieval service."""
    zip_data = create_sample_zip()
    import zipfile
    import io

    count = 0
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        for name in zf.namelist():
            if name.endswith('/'):
                continue
            content = zf.read(name)
            try:
                content_str = content.decode('utf-8')
            except UnicodeDecodeError:
                continue

            file_id = str(uuid.uuid4())
            file_path = name.replace('\\', '/')
            language = CodeParser.get_language(file_path)
            chunks = CodeParser.parse_by_functions(content_str, language, file_path)

            for chunk in chunks:
                chunk_id = str(uuid.uuid4())

                if use_enriched:
                    embedding_text = CodeParser.build_embedding_text(chunk, file_path)
                    metadata = CodeParser.build_chunk_metadata(
                        chunk=chunk,
                        file_id=file_id,
                        file_path=file_path,
                        language=language,
                    )
                else:
                    embedding_text = chunk.content
                    metadata = {
                        'file_id': file_id,
                        'filename': Path(file_path).name,
                        'language': language,
                        'start_line': chunk.start_line,
                        'end_line': chunk.end_line,
                        'chunk_type': chunk.chunk_type,
                    }

                vector = await embedding.embed_text(embedding_text)
                await retrieval.store_embedding(
                    session_id=session_id,
                    chunk_id=chunk_id,
                    content=chunk.content,
                    embedding=vector,
                    metadata=metadata,
                )
                count += 1
    return count


def _extract_result_signals(results: List[Dict]) -> Dict[str, Set[str]]:
    files: Set[str] = set()
    symbols: Set[str] = set()
    content_tokens: Set[str] = set()

    for item in results:
        meta = item.get("metadata", {})
        file_path = str(meta.get("file_path", meta.get("filename", "")))
        if file_path:
            files.add(Path(file_path).name)

        for key in ("function_name", "class_name"):
            val = meta.get(key, "")
            if val:
                symbols.add(str(val))

        content_lower = item.get("content", "").lower()
        for token in ("401", "invalid credentials", "password", "database", "get_user"):
            if token in content_lower:
                content_tokens.add(token)

    return {"files": files, "symbols": symbols, "content": content_tokens}


def evaluate_case(case: BenchmarkCase, results: List[Dict], k: int) -> Dict:
    """Compute precision@K and context completeness for one query."""
    top = results[:k]
    signals = _extract_result_signals(top)

    file_hits = case.expected_files & signals["files"]
    symbol_hits = case.expected_symbols & signals["symbols"]
    content_hits = case.expected_content & signals["content"]

    file_precision = len(file_hits) / max(len(case.expected_files), 1)
    symbol_precision = len(symbol_hits) / max(len(case.expected_symbols), 1) if case.expected_symbols else 1.0
    content_precision = len(content_hits) / max(len(case.expected_content), 1) if case.expected_content else 1.0

    completeness = (
        file_precision * 0.35
        + symbol_precision * 0.40
        + content_precision * 0.25
    )

    return {
        "query": case.query,
        "k": k,
        "retrieved_count": len(top),
        "files_found": sorted(file_hits),
        "files_missed": sorted(case.expected_files - signals["files"]),
        "symbols_found": sorted(symbol_hits),
        "symbols_missed": sorted(case.expected_symbols - signals["symbols"]),
        "content_found": sorted(content_hits),
        "precision_at_k": round((file_precision + symbol_precision + content_precision) / 3, 3),
        "context_completeness": round(completeness, 3),
        "top_results": [
            {
                "file": r.get("metadata", {}).get("file_path", ""),
                "function": r.get("metadata", {}).get("function_name", ""),
                "expansion": r.get("expansion_type"),
                "distance": round(float(r.get("distance", 0)), 4),
            }
            for r in top
        ],
    }


async def run_benchmark() -> Dict:
    """Run baseline vs enhanced retrieval comparison."""
    embedding = EmbeddingService()

    baseline_session = "benchmark-baseline"
    enhanced_session = "benchmark-enhanced"

    baseline_retrieval = RetrievalService()
    enhanced_retrieval = RetrievalService()

    indexed = await index_sample_project(
        enhanced_retrieval, embedding, enhanced_session, use_enriched=True
    )
    await index_sample_project(
        baseline_retrieval, embedding, baseline_session, use_enriched=False
    )

    baseline_results = []
    enhanced_results = []

    for case in BENCHMARK_CASES:
        query_embedding = await embedding.embed_text(case.query)
        k = max(case.min_top_k, 5)

        baseline = await baseline_retrieval.retrieve_similar(
            session_id=baseline_session,
            query_embedding=query_embedding,
            top_k=k,
            query_text=case.query,
            enhanced=False,
        )
        enhanced = await enhanced_retrieval.retrieve_similar(
            session_id=enhanced_session,
            query_embedding=query_embedding,
            top_k=k,
            query_text=case.query,
            enhanced=True,
        )

        baseline_results.append(evaluate_case(case, baseline, k))
        enhanced_results.append(evaluate_case(case, enhanced, k))

    def aggregate(results: List[Dict]) -> Dict:
        if not results:
            return {"precision_at_k": 0, "context_completeness": 0}
        return {
            "precision_at_k": round(
                sum(r["precision_at_k"] for r in results) / len(results), 3
            ),
            "context_completeness": round(
                sum(r["context_completeness"] for r in results) / len(results), 3
            ),
        }

    report = {
        "chunks_indexed": indexed,
        "baseline": {
            "aggregate": aggregate(baseline_results),
            "cases": baseline_results,
        },
        "enhanced": {
            "aggregate": aggregate(enhanced_results),
            "cases": enhanced_results,
        },
        "improvement": {},
    }

    b_agg = report["baseline"]["aggregate"]
    e_agg = report["enhanced"]["aggregate"]
    report["improvement"] = {
        "precision_at_k_delta": round(
            e_agg["precision_at_k"] - b_agg["precision_at_k"], 3
        ),
        "context_completeness_delta": round(
            e_agg["context_completeness"] - b_agg["context_completeness"], 3
        ),
    }

    return report


def print_report(report: Dict) -> None:
    """Print human-readable benchmark summary."""
    print("=" * 72)
    print("RETRIEVAL BENCHMARK — Baseline vs Enhanced")
    print("=" * 72)
    print(f"Chunks indexed: {report['chunks_indexed']}")
    print()

    b = report["baseline"]["aggregate"]
    e = report["enhanced"]["aggregate"]
    d = report["improvement"]

    print(f"{'Metric':<28} {'Baseline':>12} {'Enhanced':>12} {'Delta':>10}")
    print("-" * 72)
    print(f"{'Precision@K (avg)':<28} {b['precision_at_k']:>12.3f} {e['precision_at_k']:>12.3f} {d['precision_at_k_delta']:>+10.3f}")
    print(f"{'Context Completeness':<28} {b['context_completeness']:>12.3f} {e['context_completeness']:>12.3f} {d['context_completeness_delta']:>+10.3f}")
    print()

    for idx, case in enumerate(BENCHMARK_CASES):
        print(f"Query {idx + 1}: {case.query}")
        br = report["baseline"]["cases"][idx]
        er = report["enhanced"]["cases"][idx]
        print(f"  Baseline  P@K={br['precision_at_k']:.3f}  completeness={br['context_completeness']:.3f}")
        print(f"            symbols: {br['symbols_found']}  missed: {br['symbols_missed']}")
        print(f"  Enhanced  P@K={er['precision_at_k']:.3f}  completeness={er['context_completeness']:.3f}")
        print(f"            symbols: {er['symbols_found']}  missed: {er['symbols_missed']}")
        print(f"            files:   {er['files_found']}  missed: {er['files_missed']}")
        print("  Enhanced top results:")
        for rank, item in enumerate(er["top_results"][:5], 1):
            func = f" ({item['function']})" if item['function'] else ""
            exp = f" [{item['expansion']}]" if item['expansion'] else ""
            print(f"    {rank}. {item['file']}{func}{exp}  d={item['distance']}")
        print()


def main() -> None:
    report = asyncio.run(run_benchmark())
    print_report(report)

    output_path = ROOT / "benchmarks" / "retrieval_benchmark_results.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Full results written to {output_path}")


if __name__ == "__main__":
    main()
