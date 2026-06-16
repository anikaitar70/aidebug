# AI Debug RAG API

FastAPI backend for uploading source code, indexing it into embeddings, and asking natural-language questions with Gemini-backed RAG responses.

## Project Overview

- Upload source files or ZIP archives
- Parse code into chunks and metadata
- Store embeddings in session-scoped in-memory retrieval store
- Query code context and generate LLM answers

## Architecture

- `main.py`: app bootstrap, routers, CORS, health endpoint
- `app/api`: upload and query HTTP routes
- `app/services`: parsing, embedding, retrieval, RAG orchestration
- `app/utils`: configuration and ZIP safety handling
- `index.html`: lightweight UI served by backend root route

## Screenshots

Add screenshots to `docs/screenshots/` and reference them here:

- `docs/screenshots/upload.png`
- `docs/screenshots/query.png`
- `docs/screenshots/results.png`

## Installation

1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Create local env file:
   - Copy `.env.example` to `.env`
4. Fill real values only in local `.env` (never commit secrets).

## Local Setup

Run locally:

- `python main.py`

API and UI:

- API docs: `http://localhost:8000/docs`
- UI: `http://localhost:8000/`

## Environment Variables

Use `.env.example` as the source of truth. Key values:

- `GOOGLE_API_KEY`
- `LLM_MODEL`
- `LLM_TEMPERATURE`
- `MAX_FILE_SIZE`
- `ALLOWED_ORIGINS`
- `SESSION_TTL_SECONDS`
- `SESSION_CLEANUP_INTERVAL_SECONDS`

## Security Notes

- Never commit `.env` with real values.
- ZIP uploads are filtered for traversal, symlink entries, and archive abuse limits.
- Session IDs gate data access between users but are not full authentication.

## Deployment

For production setup on OVH VPS, see `DEPLOYMENT.md`.
