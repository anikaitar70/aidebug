# Dependency Map

## `app/__init__.py`
- Imports: None
- Imported by: None
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/api/__init__.py`
- Imports: None
- Imported by: main.py
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/api/query.py`
- Imports: app.models.schemas, app.security, app.services.embedding_service, app.services.llm_service, app.services.retrieval_service, fastapi, logging, re, traceback, typing
- Imported by: None
- Routes exposed: @router.post("/search", response_model=QueryResponse), @router.post("/retrieval-only"), @router.get("/stats")
- Frontend references: index.html
- Documentation references: API_SECURITY_REVIEW.md, SECURITY_FINDINGS.md

## `app/api/upload.py`
- Imports: app.models.schemas, app.security, app.services.code_parser, app.services.embedding_service, app.services.file_service, app.services.retrieval_service, app.services.session_store, app.utils.config, app.utils.zip_handler, fastapi, logging, os, pathlib, re, tempfile, typing, uuid
- Imported by: None
- Routes exposed: @router.post("/batch"), @router.post("/zip", response_model=dict), @router.post("/zip/process"), @router.delete("/zip/{upload_id}"), @router.delete("/file/{file_id}")
- Frontend references: index.html
- Documentation references: API_SECURITY_REVIEW.md, GETTING_STARTED.md, QUICKSTART_ZIP.md, SECURITY_FINDINGS.md, ZIP_UPLOAD.md

## `app/models/__init__.py`
- Imports: None
- Imported by: None
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/models/schemas.py`
- Imports: datetime, pydantic, typing
- Imported by: app/api/query.py, app/api/upload.py
- Routes exposed: None
- Frontend references: None
- Documentation references: QUICKSTART_ZIP.md

## `app/security.py`
- Imports: app.utils.config, slowapi, slowapi.util
- Imported by: app/api/query.py, app/api/upload.py, main.py
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/services/__init__.py`
- Imports: None
- Imported by: None
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/services/code_parser.py`
- Imports: logging, pathlib, re, typing
- Imported by: app/api/upload.py
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/services/embedding_service.py`
- Imports: app.utils.config, logging, numpy, sentence_transformers, typing
- Imported by: app/api/query.py, app/api/upload.py
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/services/file_service.py`
- Imports: app.utils.config, logging, os, pathlib, typing, uuid
- Imported by: app/api/upload.py
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/services/llm_service.py`
- Imports: app.utils.config, google.generativeai, logging, typing
- Imported by: app/api/query.py
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/services/query_classifier.py`
- Imports: __future__, dataclasses, re, typing
- Imported by: app/services/retrieval_service.py
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/services/retrieval_service.py`
- Imports: __future__, app.services.query_classifier, app.services.session_store, hashlib, logging, numpy, re, time, typing
- Imported by: app/api/query.py, app/api/upload.py
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/services/session_store.py`
- Imports: __future__, app.utils.config, dataclasses, logging, threading, time, typing
- Imported by: app/api/upload.py, app/services/retrieval_service.py, main.py
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/utils/__init__.py`
- Imports: None
- Imported by: None
- Routes exposed: None
- Frontend references: None
- Documentation references: None

## `app/utils/config.py`
- Imports: pydantic_settings, typing
- Imported by: app/api/upload.py, app/security.py, app/services/embedding_service.py, app/services/file_service.py, app/services/llm_service.py, app/services/session_store.py, main.py
- Routes exposed: None
- Frontend references: None
- Documentation references: API_SECURITY_REVIEW.md, GETTING_STARTED.md, QUICKSTART_ZIP.md, ZIP_UPLOAD.md

## `app/utils/zip_handler.py`
- Imports: datetime, io, logging, os, pathlib, shutil, stat, tempfile, typing, uuid, zipfile
- Imported by: app/api/upload.py, test_zip_upload.py
- Routes exposed: None
- Frontend references: None
- Documentation references: API_SECURITY_REVIEW.md, QUICKSTART_ZIP.md, SECURITY_FINDINGS.md, ZIP_UPLOAD.md

## `examples_zip_upload.py`
- Imports: io, json, pathlib, requests, zipfile
- Imported by: None
- Routes exposed: None
- Frontend references: None
- Documentation references: GETTING_STARTED.md, QUICKSTART_ZIP.md, ZIP_UPLOAD.md

## `main.py`
- Imports: app.api, app.security, app.services.session_store, app.utils.config, asyncio, contextlib, fastapi, fastapi.middleware.cors, fastapi.responses, logging, pathlib, secrets, slowapi, slowapi.errors, uvicorn
- Imported by: None
- Routes exposed: @app.middleware("http"), @app.middleware("http"), @app.get("/health", tags=["health"]), @app.get("/", include_in_schema=False)
- Frontend references: index.html
- Documentation references: API_SECURITY_REVIEW.md, GETTING_STARTED.md, README.md, SECURITY_FINDINGS.md

## `test_zip_upload.py`
- Imports: app.utils.zip_handler, io, logging, pathlib, pytest, sys, tempfile, unittest.mock, zipfile
- Imported by: None
- Routes exposed: None
- Frontend references: None
- Documentation references: QUICKSTART_ZIP.md
