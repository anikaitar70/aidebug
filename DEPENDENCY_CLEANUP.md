# Dependency Cleanup

## Method

- Parsed imports across all Python files in the repository.
- Cross-checked with `requirements.txt`.
- Preserved runtime-transitive requirements needed by framework behavior (for example `python-multipart` for `UploadFile`, `python-dotenv` for `.env` loading).

## Removed Dependencies

- `openai`  
  - **Reason:** never imported or used by runtime paths.
- `langchain`  
  - **Reason:** never imported.
- `langchain-community`  
  - **Reason:** never imported.
- `python-jose`  
  - **Reason:** never imported; no JWT auth implementation in code.
- `PyYAML`  
  - **Reason:** no `yaml` imports.
- `tenacity`  
  - **Reason:** no imports.
- `httpx`  
  - **Reason:** not required directly by repository code.
- `aiofiles`  
  - **Reason:** not imported or required by current implementation.

## Kept Dependencies (justification)

- `python-multipart`  
  - Required by FastAPI file upload handling.
- `python-dotenv`  
  - Used by settings loading from `.env`.
- `requests`  
  - Used by `examples_zip_upload.py`.
- `google-generativeai`, `sentence-transformers`, `numpy`, `slowapi`, `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`  
  - Directly used by active runtime paths.
