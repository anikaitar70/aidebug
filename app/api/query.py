"""Query API endpoints"""

import logging
import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Header, Request

from app.models.schemas import (
    QueryRequest,
    QueryResponse,
    RetrievedContext,
    ProjectOverviewResponse,
)
from app.services.embedding_service import get_embedding_service
from app.services.retrieval_service import get_retrieval_service
from app.services.llm_service import get_llm_service
from app.services.query_classifier import classify_query_intent
from app.services.session_store import get_session_store
from app.security import limiter
from app.utils.gemini_auth import resolve_gemini_api_key

logger = logging.getLogger(__name__)

router = APIRouter()
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{24,128}$")


def _resolve_session_id(
    request_session_id: Optional[str],
    query_session_id: Optional[str] = None,
    x_session_id: Optional[str] = None,
) -> str:
    """Resolve session ID from request body, query param, or header."""
    resolved = (request_session_id or query_session_id or x_session_id or "").strip()
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="session_id is required (pass in request body, query param, or X-Session-Id header)",
        )
    if not SESSION_ID_PATTERN.fullmatch(resolved):
        raise HTTPException(status_code=400, detail="Invalid session_id format")
    return resolved


@router.post("/search", response_model=QueryResponse)
@limiter.limit("120/hour")
async def search_code(
    request: Request,
    payload: QueryRequest,
    x_gemini_api_key: str | None = Header(default=None, alias="X-Gemini-Api-Key"),
):
    """
    Search for relevant code chunks using semantic search
    
    - **query**: Search query or question
    - **top_k**: Number of results to return (default: 5)
    - **filters**: Optional metadata filters
    - **session_id**: Browser session identifier
    
    Returns relevant code chunks and LLM-generated answer
    """
    try:
        if not payload.query or not payload.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        session_id = _resolve_session_id(payload.session_id)
        gemini_key = resolve_gemini_api_key(payload.gemini_api_key, x_gemini_api_key)
        
        embedding_service = await get_embedding_service()
        query_embedding = await embedding_service.embed_text(payload.query)
        
        retrieval_service = await get_retrieval_service()
        results = await retrieval_service.retrieve_similar(
            session_id=session_id,
            query_embedding=query_embedding,
            top_k=payload.top_k,
            filters=payload.filters,
            query_text=payload.query,
            enhanced=True,
        )
        
        if not results:
            logger.info("VERIFICATION — Query complete")
            logger.info("  Session: %s", session_id)
            logger.info("  Retrieved chunk count: 0")
            logger.info("  Top similarity score: 0.000")
            logger.info("  Model used: none")
            return QueryResponse(
                answer="No relevant code chunks found for your query.",
                context=[],
                model="none",
                tokens_used=0
            )

        top_similarity = max(
            1 - float(result.get('distance', 0)) for result in results
        )
        logger.info("VERIFICATION — Query complete")
        logger.info("  Session: %s", session_id)
        logger.info("  Retrieved chunk count: %d", len(results))
        logger.info("  Top similarity score: %.3f", top_similarity)
        
        context_chunks = []
        for result in results:
            similarity = 1 - result.get('distance', 0)
            meta = result.get('metadata', {})

            context_chunks.append(RetrievedContext(
                chunk_id=result['chunk_id'],
                content=result['content'],
                language=meta.get('language', 'unknown'),
                file_id=meta.get('file_id', ''),
                file_path=meta.get('file_path', meta.get('filename', '')),
                filename=meta.get('filename', ''),
                function_name=meta.get('function_name', ''),
                class_name=meta.get('class_name', ''),
                start_line=meta.get('start_line'),
                end_line=meta.get('end_line'),
                similarity_score=similarity,
                expansion_type=result.get('expansion_type'),
                context_group=result.get('context_group'),
            ))

        intent = classify_query_intent(payload.query)
        answerable, answer_reason = retrieval_service.check_answerability(
            results, intent, payload.query
        )
        if not answerable:
            logger.warning(
                "RETRIEVAL_QUALITY_FAILURE query=%r intent=%s reason=%s files=%s",
                payload.query,
                intent.primary,
                answer_reason,
                [c.file_path for c in context_chunks],
            )
            return QueryResponse(
                answer=(
                    "Relevant implementation code was not retrieved. "
                    "Retrieval quality appears insufficient."
                ),
                context=context_chunks,
                model="none",
                tokens_used=0,
            )
        
        llm_service = await get_llm_service()
        grouped_context = retrieval_service.assemble_grouped_context(results)
        llm_result = await llm_service.generate_response(
            query=payload.query,
            context_chunks=grouped_context,
            api_key=gemini_key,
        )
        logger.info("  Model used: %s", llm_result['model'])
        
        return QueryResponse(
            answer=llm_result['answer'],
            context=context_chunks,
            relevant_file_names=sorted({c.file_path for c in context_chunks if c.file_path}),
            retrieved_snippets=context_chunks,
            model=llm_result['model'],
            tokens_used=llm_result.get('tokens_used', 0)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        logger.error("=" * 80)
        logger.error("QUERY FAILED")
        logger.error(f"ERROR: {str(e)}")
        logger.error("FULL TRACEBACK:")
        logger.error(traceback.format_exc())
        logger.error("=" * 80)

        raise HTTPException(status_code=500, detail="Query processing failed")


@router.post("/retrieval-only")
@limiter.limit("120/hour")
async def retrieval_only(request: Request, payload: QueryRequest):
    """
    Retrieve similar code chunks without LLM generation
    
    Useful for exploring the codebase quickly
    """
    try:
        session_id = _resolve_session_id(payload.session_id)

        embedding_service = await get_embedding_service()
        query_embedding = await embedding_service.embed_text(payload.query)
        
        retrieval_service = await get_retrieval_service()
        results = await retrieval_service.retrieve_similar(
            session_id=session_id,
            query_embedding=query_embedding,
            top_k=payload.top_k,
            filters=payload.filters,
            query_text=payload.query,
            enhanced=True,
        )
        
        context_chunks = []
        for result in results:
            similarity = 1 - result.get('distance', 0)
            meta = result.get('metadata', {})
            context_chunks.append({
                'chunk_id': result['chunk_id'],
                'content': result['content'],
                'language': meta.get('language', 'unknown'),
                'file_id': meta.get('file_id', ''),
                'file_path': meta.get('file_path', ''),
                'filename': meta.get('filename', ''),
                'function_name': meta.get('function_name', ''),
                'class_name': meta.get('class_name', ''),
                'line_range': {
                    'start': meta.get('start_line'),
                    'end': meta.get('end_line')
                },
                'expansion_type': result.get('expansion_type'),
                'context_group': result.get('context_group'),
                'similarity_score': similarity
            })
        
        return {
            "session_id": session_id,
            "query": payload.query,
            "results_count": len(context_chunks),
            "results": context_chunks
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Retrieval failed")


@router.get("/stats")
@limiter.limit("120/hour")
async def get_stats(
    request: Request,
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """Get statistics about the session's in-memory vector store"""
    try:
        resolved_session_id = _resolve_session_id(None, session_id, x_session_id)
        retrieval_service = await get_retrieval_service()
        collection_count = retrieval_service.get_chunk_count(resolved_session_id)

        stats = {
            "status": "operational",
            "storage": "in-memory",
            "session_id": resolved_session_id,
            "collection_count": collection_count,
        }
        if collection_count > 0:
            audit = retrieval_service.get_index_audit(resolved_session_id)
            stats["index_audit"] = {
                "total_files": audit.get("total_files", 0),
                "node_modules_chunks": audit.get("node_modules_chunks", 0),
                "has_stale_excluded_paths": audit.get("has_stale_excluded_paths", False),
                "index_version": audit.get("index_version", "unknown"),
                "top_paths": [
                    p["file_path"] for p in audit.get("top_indexed_paths", [])[:5]
                ],
            }
        
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Stats retrieval failed")


@router.get("/index-audit")
@limiter.limit("120/hour")
async def get_index_audit(
    request: Request,
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """Audit indexed corpus for a session — detect stale node_modules / build artifacts."""
    try:
        resolved_session_id = _resolve_session_id(None, session_id, x_session_id)
        retrieval_service = await get_retrieval_service()
        audit = retrieval_service.get_index_audit(resolved_session_id)
        return audit
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Index audit failed: {e}")
        raise HTTPException(status_code=500, detail="Index audit failed")


@router.delete("/session")
@limiter.limit("30/hour")
async def clear_session(
    request: Request,
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """Clear all indexed chunks for a session (force re-upload)."""
    try:
        from app.services.session_store import get_session_store

        resolved_session_id = _resolve_session_id(None, session_id, x_session_id)
        cleared = get_session_store().clear_session(resolved_session_id)
        return {
            "status": "cleared",
            "session_id": resolved_session_id,
            "chunks_removed": cleared,
            "message": "Session cleared. Re-upload your repository ZIP to re-index.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session clear failed: {e}")
        raise HTTPException(status_code=500, detail="Session clear failed")


@router.post("/debug")
@limiter.limit("60/hour")
async def debug_query(
    request: Request,
    payload: QueryRequest,
    x_gemini_api_key: str | None = Header(default=None, alias="X-Gemini-Api-Key"),
):
    """
    Full pipeline debug trace: raw search → rerank → final → LLM context → answer.

    Reveals exactly what Gemini receives.
    """
    try:
        if not payload.query or not payload.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        session_id = _resolve_session_id(payload.session_id)
        gemini_key = resolve_gemini_api_key(payload.gemini_api_key, x_gemini_api_key)

        embedding_service = await get_embedding_service()
        query_embedding = await embedding_service.embed_text(payload.query)

        retrieval_service = await get_retrieval_service()
        index_audit = retrieval_service.get_index_audit(session_id)
        trace = await retrieval_service.trace_retrieval(
            session_id=session_id,
            query_embedding=query_embedding,
            query_text=payload.query,
            top_k=payload.top_k,
        )

        final_results = await retrieval_service.retrieve_similar(
            session_id=session_id,
            query_embedding=query_embedding,
            top_k=payload.top_k,
            filters=payload.filters,
            query_text=payload.query,
            enhanced=True,
        )

        intent = classify_query_intent(payload.query)
        answerable, answer_reason = retrieval_service.check_answerability(
            final_results, intent, payload.query
        )
        llm_context = retrieval_service.build_llm_context_preview(final_results)

        answer = None
        model_used = "none"
        tokens_used = 0

        if answerable and final_results:
            llm_service = await get_llm_service()
            llm_result = await llm_service.generate_response(
                query=payload.query,
                context_chunks=llm_context["grouped_context_strings"],
                api_key=gemini_key,
            )
            answer = llm_result["answer"]
            model_used = llm_result["model"]
            tokens_used = llm_result.get("tokens_used", 0)
        elif not final_results:
            answer = "No relevant code chunks found for your query."
        else:
            answer = (
                "Relevant implementation code was not retrieved. "
                "Retrieval quality appears insufficient."
            )

        return {
            "query": payload.query,
            "session_id": session_id,
            "intent": trace.get("intent"),
            "index_audit": index_audit,
            "raw_results": trace.get("raw_vector_results", []),
            "reranked_results": trace.get("reranked_results", []),
            "final_results": trace.get("final_results", []),
            "answerable": answerable,
            "answerability_reason": answer_reason,
            "FINAL_CONTEXT_SENT_TO_LLM": llm_context,
            "answer": answer,
            "model": model_used,
            "tokens_used": tokens_used,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        logger.error("DEBUG QUERY FAILED: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail="Debug query failed")


@router.get("/project-overview", response_model=ProjectOverviewResponse)
@limiter.limit("120/hour")
async def get_project_overview(
    request: Request,
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """Return project description and sample questions generated after indexing."""
    try:
        resolved_session_id = _resolve_session_id(None, session_id, x_session_id)
        overview = get_session_store().get_project_overview(resolved_session_id)
        return ProjectOverviewResponse(
            ready=overview.get("ready", False),
            description=overview.get("description", ""),
            sample_questions=overview.get("sample_questions", []),
            total_chunks=overview.get("total_chunks", 0),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Project overview failed: {e}")
        raise HTTPException(status_code=500, detail="Project overview failed")
