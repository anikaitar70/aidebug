# File Removal Plan

## Classification Legend

- **ACTIVE**: used by runtime and/or tests/docs.
- **LEGACY**: old implementation replaced by active path.
- **UNUSED**: no import/reference/runtime usage.
- **DUPLICATE**: overlapping implementation of active behavior.
- **EXPERIMENTAL**: one-off diagnostics/benchmarks not required for deployment.

## Verified Removal Candidates (Executed)

### 1) `app/services/rag_service.py`
- **Classification:** DUPLICATE / LEGACY
- **Reason:** second query pipeline duplicating `/api/query/search` path.
- **Evidence:** only used by removed `POST /query` route in `main.py`; frontend uses `/api/query/search`.
- **Risk:** Low after `/query` route removal.
- **Replacement:** `app/api/query.py` + `app/services/llm_service.py`.

### 2) `app/services/google_embedding_service.py`
- **Classification:** UNUSED / LEGACY
- **Reason:** alternative embedding path never imported by active routes.
- **Evidence:** no `imported_by` runtime references.
- **Risk:** Low.
- **Replacement:** `app/services/embedding_service.py`.

### 3) `app/services/chunk_service.py`
- **Classification:** UNUSED
- **Reason:** not used by upload/query runtime path.
- **Evidence:** no imports; parser pipeline uses `CodeParser`.
- **Risk:** Low.
- **Replacement:** `app/services/code_parser.py`.

### 4) `create_sample_project.py`, `sample_project.zip`
- **Classification:** EXPERIMENTAL
- **Reason:** synthetic sample generator/artifact for old walkthrough.
- **Evidence:** no runtime imports after benchmark/diagnostic cleanup.
- **Risk:** Low.
- **Replacement:** user-provided ZIPs through UI.

### 5) `benchmarks/*`, `benchmark_baseline/chroma.sqlite3`, `benchmark_enhanced/chroma.sqlite3`
- **Classification:** EXPERIMENTAL / GENERATED
- **Reason:** benchmark-only code/results not needed for service runtime.
- **Evidence:** no runtime imports or deployment references.
- **Risk:** Low.
- **Replacement:** none (can be reintroduced in dedicated perf branch).

### 6) `scripts/diagnose_jwt_retrieval.py`, `diagnose_gemini.py`, `trace_pipeline.py`, `verify_e2e.py`
- **Classification:** EXPERIMENTAL / UNUSED
- **Reason:** one-off local diagnostics.
- **Evidence:** no runtime imports, no deployment coupling.
- **Risk:** Low.
- **Replacement:** standardized verification documented in `SECURITY_VERIFICATION.md`.
