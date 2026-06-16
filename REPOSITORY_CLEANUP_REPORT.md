# Repository Cleanup Report

## Summary

Repository was reduced to active runtime components and essential documentation for public release. Duplicate query paths, abandoned experiments, benchmark artifacts, and unused dependencies were removed.

## Phase Results

### Dependency Map

- Generated: `DEPENDENCY_MAP.md`
- Includes per-file imports, imported-by relationships, exposed routes, frontend references, and documentation references.

### File Classification

- **ACTIVE:** `main.py`, `app/api/upload.py`, `app/api/query.py`, `app/services/retrieval_service.py`, `app/services/embedding_service.py`, `app/services/llm_service.py`, `app/services/code_parser.py`, `app/services/file_service.py`, `app/services/session_store.py`, `app/services/query_classifier.py`, config/schema/security modules.
- **LEGACY/DUPLICATE removed:** `app/services/rag_service.py`, `app/services/google_embedding_service.py`, `app/services/chunk_service.py`.
- **EXPERIMENTAL removed:** benchmark scripts/results and ad-hoc diagnostics.

### Files Deleted

- `app/services/rag_service.py`
- `app/services/google_embedding_service.py`
- `app/services/chunk_service.py`
- `diagnose_gemini.py`
- `trace_pipeline.py`
- `verify_e2e.py`
- `scripts/diagnose_jwt_retrieval.py`
- `benchmarks/precision_benchmark.py`
- `benchmarks/retrieval_benchmark.py`
- `benchmarks/precision_benchmark_results.json`
- `benchmarks/retrieval_benchmark_results.json`
- `benchmark_baseline/chroma.sqlite3`
- `benchmark_enhanced/chroma.sqlite3`
- `create_sample_project.py`
- `sample_project.zip`

### Dependencies Removed

- `openai`
- `langchain`
- `langchain-community`
- `python-jose`
- `PyYAML`
- `tenacity`
- `httpx`
- `aiofiles`

Details: `DEPENDENCY_CLEANUP.md`

## Architecture Before

- Dual query flows (`/query` and `/api/query/search`)
- Multiple embedding/chunking service variants
- Benchmark/diagnostic code mixed with runtime code
- Broader dependency set than required

## Architecture After

- Single runtime query path: `/api/query/search`
- Single active embedding service (`EmbeddingService`)
- Single active parsing/chunking path (`CodeParser`)
- Runtime-focused service tree with fewer dead paths
- Leaner dependency set

## Verification

Executed runtime verification with TestClient (production mode + API key):

- `GET /health` -> 200
- `POST /api/upload/zip` -> 200
- `POST /api/upload/zip/process` -> 200
- `POST /api/query/search` -> 200
- Answer returned with non-empty context

Flow confirmed:

Upload -> Index -> Query -> Answer

## Code Reduction (approximate)

- Python files: **31 -> 21** (10 removed)
- Requirements entries: **18 -> 10** (8 removed)
- Removed generated benchmark DB/files and sample artifact ZIPs
