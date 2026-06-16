# Getting Started

## Prerequisites

- Python 3.10+
- `pip`
- Gemini API key (`GOOGLE_API_KEY`)

## Install

```powershell
cd "c:\Users\anika\Desktop\New folder (4)\AI Debug"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configure

```powershell
copy .env.example .env
```

Set at least:

- `ENVIRONMENT=development`
- `GOOGLE_API_KEY=your_google_api_key_here`

## Run

```powershell
python main.py
```

- UI: `http://localhost:8000/`
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## End-to-End Flow

1. Upload a source ZIP from the UI.
2. Wait for extraction and indexing.
3. Ask a query in the UI search box.
4. Review generated answer and retrieved snippets.

## API Quick Test

```bash
curl -X POST "http://localhost:8000/api/upload/zip?session_id=test-session" \
  -F "file=@your-codebase.zip"

curl -X POST "http://localhost:8000/api/upload/zip/process?upload_id=<upload_id>&session_id=test-session"

curl -X POST "http://localhost:8000/api/query/search" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"Where is authentication handled?\",\"top_k\":5,\"session_id\":\"test-session\"}"
```

In production mode, add header:

- `X-API-Key: <API_ACCESS_KEY>`
