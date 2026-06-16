"""
FastAPI-based RAG (Retrieval-Augmented Generation) System
Entry point for the application
"""

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import upload, query
from app.models.schemas import QueryRequest, QueryResponse, RetrievedContext
from app.security import limiter
from app.utils.config import get_settings


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def _session_cleanup_loop() -> None:
    """Periodically remove sessions inactive longer than TTL."""
    from app.services.session_store import get_session_store

    settings = get_settings()
    store = get_session_store()
    interval = settings.SESSION_CLEANUP_INTERVAL_SECONDS

    while True:
        await asyncio.sleep(interval)
        try:
            removed = store.cleanup_expired()
            if removed:
                logger.info("Background cleanup removed %d expired session(s)", removed)
        except Exception as exc:
            logger.error("Session cleanup task failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle with background session cleanup."""
    logger.info("Application startup — in-memory session RAG")
    cleanup_task = asyncio.create_task(_session_cleanup_loop())
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("Application shutdown")


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    settings = get_settings()
    
    app = FastAPI(
        title="RAG System API",
        description="Retrieval-Augmented Generation System for code analysis",
        version="1.0.0",
        lifespan=lifespan
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.middleware("http")
    async def api_key_auth_middleware(request: Request, call_next):
        if not settings.auth_enabled:
            return await call_next(request)

        protected_prefixes = ("/api/upload", "/api/query", "/query")
        if request.url.path.startswith(protected_prefixes):
            provided_key = request.headers.get("X-API-Key", "").strip()
            expected_key = (settings.API_ACCESS_KEY or "").strip()
            if not expected_key or not provided_key or not secrets.compare_digest(provided_key, expected_key):
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Unauthorized"},
                )
        return await call_next(request)


    @app.get("/health", tags=["health"])
    async def health_check():
        return {
        "status": "healthy",
        "message": "Backend is running"
        }
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.effective_allowed_origins,
        allow_origin_regex=r"^http://localhost(:[0-9]+)?$" if not settings.is_production else None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
    app.include_router(query.router, prefix="/api/query", tags=["query"])

    index_path = Path(__file__).parent / "index.html"

    @app.get("/", include_in_schema=False)
    async def serve_ui():
        """Serve the web UI (avoids file:// CORS issues)."""
        return FileResponse(index_path)

    # Full RAG query endpoint
    @app.post("/query", response_model=QueryResponse)
    @limiter.limit("120/hour")
    async def full_rag_query(request: QueryRequest):
        if not request.query or not request.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        try:
            from app.services.rag_service import get_rag_service
            rag_service = await get_rag_service()
            result = await rag_service.answer_query(
                query=request.query,
                top_k=request.top_k,
                filters=request.filters,
                session_id=request.session_id,
            )

            retrieved_snippets = []
            relevant_files = []
            for item in result.get("context", []):
                metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
                file_name = metadata.get("file_name") or metadata.get("filename")
                if file_name and file_name not in relevant_files:
                    relevant_files.append(file_name)

                retrieved_snippets.append(RetrievedContext(
                    chunk_id=item.get("chunk_id", ""),
                    content=item.get("content", ""),
                    language=metadata.get("language", "unknown"),
                    file_id=metadata.get("file_id", ""),
                    similarity_score=1 - float(item.get("distance", 0.0)),
                ))

            return QueryResponse(
                answer=result.get("answer", ""),
                context=retrieved_snippets,
                relevant_file_names=relevant_files,
                retrieved_snippets=retrieved_snippets,
                model=result.get("model", "unknown"),
                tokens_used=result.get("tokens_used", 0),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"RAG query failed: {e}")
            raise HTTPException(status_code=500, detail="RAG query failed")

    # Health check endpoint
    # @app.get("/health", tags=["health"])
    # async def health_check():
    #     """Health check endpoint"""
    #     return {"status": "healthy"}
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
