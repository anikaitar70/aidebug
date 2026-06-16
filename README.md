# AI Debug RAG API

Code-question answering backend for uploaded repositories.  
This project indexes uploaded source files and answers natural-language questions using retrieved code context plus Gemini generation.

## What This Repository Demonstrates

- FastAPI service design with clear API boundaries (`upload`, `query`, `stats`)
- Practical RAG pipeline for code retrieval
- Security-focused upload handling (ZIP path checks, archive limits, API key mode, rate limits)
- Deployable single-service architecture for a personal VPS



## Retrieval Pipeline

1. Client uploads ZIP (`/api/upload/zip`).
2. Archive is validated and extracted with safety checks.
3. Extracted files are parsed into structured chunks (`CodeParser`).
4. Chunks are embedded (`EmbeddingService`) and stored per session (`RetrievalService`).
5. Query request (`/api/query/search`) is embedded and matched against stored vectors.
6. Top-k chunks are passed to `LLMService` to generate the response.
7. API returns answer + supporting retrieved snippets.

## Technology Stack

- **Backend:** FastAPI, Uvicorn, Pydantic
- **RAG Core:** custom parser/retrieval services, NumPy
- **Embeddings:** `sentence-transformers`
- **LLM:** `google-generativeai` (Gemini)
- **Security/Hardening:** `slowapi`, ZIP extraction safeguards, environment-based auth/CORS
- **Frontend:** static `index.html` served by backend

## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python main.py
```

- UI: `http://localhost:8000/`
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## Deployment

Use the OVH VPS guide in `DEPLOYMENT.md`.

At minimum in production:

- set `ENVIRONMENT=production`
- set non-empty `API_ACCESS_KEY`
- set valid `GOOGLE_API_KEY`
- restrict `ALLOWED_ORIGINS`
- run behind Nginx/HTTPS with request size and rate controls

## Example Questions

- "Where is authentication implemented?"
- "How are sessions created and cleaned up?"
- "Which endpoint handles ZIP upload processing?"
- "Show file parsing logic before embeddings are generated."
- "What causes a 401 vs 429 response?"

## Limitations

- Session-scoped in-memory retrieval store (not persistent database storage)
- No user identity model (API key guard, not per-user auth)
- Retrieval quality depends on chunking and embedding model behavior
- LLM answers can still be imperfect or incomplete despite context grounding
- Large repositories may take noticeable indexing time

## Future Improvements

- Replace in-memory retrieval backend with persistent vector store options
- Add richer evaluation benchmarks for retrieval and answer quality
- Add asynchronous background job status API for long indexing tasks
- Migrate to current Google GenAI SDK interface and remove deprecated warnings
- Add integration tests that cover full upload-index-query lifecycle in CI
