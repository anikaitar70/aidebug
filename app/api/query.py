"""Query API endpoints"""

import logging
import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Header, Request

from app.models.schemas import (
    QueryRequest,
    QueryResponse,
    RetrievedContext
)
from app.services.embedding_service import get_embedding_service
from app.services.retrieval_service import get_retrieval_service
from app.services.llm_service import get_llm_service
from app.security import limiter

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
async def search_code(request: Request, payload: QueryRequest):
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
        
        llm_service = await get_llm_service()
        grouped_context = retrieval_service.assemble_grouped_context(results)
        llm_result = await llm_service.generate_response(
            query=payload.query,
            context_chunks=grouped_context
        )
        logger.info("  Model used: %s", llm_result['model'])
        
        return QueryResponse(
            answer=llm_result['answer'],
            context=context_chunks,
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
        
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Stats retrieval failed")
