"""Upload API endpoints"""

import logging
import tempfile
import re
from typing import List
import uuid
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks, Header, Query, Request

from app.models.schemas import FileUploadResponse
from app.services.file_service import get_file_service
from app.services.code_parser import CodeParser
from app.services.embedding_service import get_embedding_service
from app.services.retrieval_service import get_retrieval_service
from app.services.session_store import get_session_store
from app.security import limiter
from app.utils.config import get_settings
from app.utils.path_filters import should_index_path

logger = logging.getLogger(__name__)

router = APIRouter()
UPLOAD_ID_PATTERN = re.compile(r"^rag_zip_[A-Za-z0-9_]{1,64}$")
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{24,128}$")
settings = get_settings()


def _resolve_session_id(session_id: str | None, x_session_id: str | None = None) -> str:
    """Resolve session ID from query param or header."""
    resolved = (session_id or x_session_id or "").strip()
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="session_id is required (pass as query param or X-Session-Id header)",
        )
    if not SESSION_ID_PATTERN.fullmatch(resolved):
        raise HTTPException(status_code=400, detail="Invalid session_id format")
    return resolved


def _resolve_upload_temp_dir(upload_id: str) -> Path:
    """Validate upload_id and map to a safe temp directory."""
    candidate = (upload_id or "").strip()
    if not UPLOAD_ID_PATTERN.fullmatch(candidate):
        raise HTTPException(status_code=400, detail="Invalid upload_id format")
    return Path(tempfile.gettempdir()) / candidate


async def process_uploaded_file(
    session_id: str,
    file_id: str,
    filename: str,
    content: bytes,
    relative_path: str | None = None,
) -> int:
    """Background task: parse, embed, and store file. Returns chunk count stored."""
    try:
        file_path = (relative_path or filename).replace('\\', '/')
        if not should_index_path(file_path):
            logger.debug("Skipping excluded path during indexing: %s", file_path)
            return 0

        logger.info(f"Processing file: {file_path} (ID: {file_id}) for session {session_id}")

        language = CodeParser.get_language(file_path)
        content_str = content.decode('utf-8', errors='ignore')
        chunks = CodeParser.parse_by_functions(content_str, language, file_path)

        logger.info(f"Parsed {len(chunks)} chunks from {file_path}")

        embedding_service = await get_embedding_service()
        retrieval_service = await get_retrieval_service()

        stored = 0
        for chunk in chunks:
            chunk_id = str(uuid.uuid4())
            embedding_text = CodeParser.build_embedding_text(chunk, file_path)
            embedding = await embedding_service.embed_text(embedding_text)
            metadata = CodeParser.build_chunk_metadata(
                chunk=chunk,
                file_id=file_id,
                file_path=file_path,
                language=language,
            )

            success = await retrieval_service.store_embedding(
                session_id=session_id,
                chunk_id=chunk_id,
                content=chunk.content,
                embedding=embedding,
                metadata=metadata,
            )
            if success:
                stored += 1
        
        logger.info(f"Completed processing for file: {filename} ({stored} chunks stored)")
        return stored
    except Exception as e:
        logger.error(f"Failed to process file {filename}: {e}")
        return 0


async def index_extracted_zip(session_id: str, upload_id: str) -> None:
    """Process all files in an extracted zip, then remove temp files."""
    import os

    temp_dir = Path(tempfile.gettempdir()) / upload_id
    retrieval_service = await get_retrieval_service()
    session_store = get_session_store()

    # Clear stale embeddings from prior uploads in this session
    cleared = session_store.clear_session(session_id)
    if cleared:
        logger.info(
            "Re-index: cleared %d stale chunks from session %s before new upload",
            cleared,
            session_id,
        )

    count_before = retrieval_service.get_chunk_count(session_id)

    files_processed = 0
    chunks_generated = 0

    for root, dirs, files in os.walk(temp_dir):
        # Prune excluded directories during walk
        dirs[:] = [
            d for d in dirs
            if should_index_path(str(Path(root).relative_to(temp_dir) / d))
        ]
        for filename in files:
            file_path = Path(root) / filename
            relative_path = str(file_path.relative_to(temp_dir)).replace('\\', '/')
            if not should_index_path(relative_path):
                continue
            try:
                content = file_path.read_bytes()
                content.decode('utf-8', errors='ignore')
            except Exception:
                continue

            file_id = str(uuid.uuid4())
            relative_path = str(file_path.relative_to(temp_dir)).replace('\\', '/')
            chunk_count = await process_uploaded_file(
                session_id=session_id,
                file_id=file_id,
                filename=filename,
                content=content,
                relative_path=relative_path,
            )
            if chunk_count > 0:
                files_processed += 1
                chunks_generated += chunk_count

    count_after = retrieval_service.get_chunk_count(session_id)
    embeddings_stored = count_after - count_before

    logger.info("VERIFICATION — Indexing complete")
    logger.info("  Session: %s", session_id)
    logger.info("  Files processed: %d", files_processed)
    logger.info("  Chunks generated: %d", chunks_generated)
    logger.info("  Embeddings stored: %d", embeddings_stored)
    logger.info("  Session chunk count: %d", count_after)

    # Remove uploaded files after indexing — embeddings live in session memory only
    try:
        from app.utils.zip_handler import get_zip_extractor
        extractor = get_zip_extractor(settings.MAX_FILE_SIZE)
        if temp_dir.exists():
            extractor.cleanup_temp_dir(str(temp_dir))
            logger.info("memory_freed removed_temp_dir=%s session_id=%s", upload_id, session_id)
    except Exception as exc:
        logger.warning("Failed to cleanup temp dir %s: %s", upload_id, exc)


@router.post("/batch")
@limiter.limit("10/hour")
async def upload_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """
    Upload multiple files at once
    
    Returns list of upload responses for each file
    """
    resolved_session_id = _resolve_session_id(session_id, x_session_id)
    get_session_store().get_or_create(resolved_session_id)

    results = []
    
    for file in files:
        if file.filename is None or file.size is None:
            results.append({"filename": "unknown", "error": "Invalid file"})
            continue
        
        try:
            file_service = get_file_service()
            content = await file.read()
            
            file_id, file_path = await file_service.save_upload_file(file.filename, content)
            
            background_tasks.add_task(
                process_uploaded_file,
                session_id=resolved_session_id,
                file_id=file_id,
                filename=file.filename,
                content=content
            )
            
            language = CodeParser.get_language(file.filename)
            content_str = content.decode('utf-8', errors='ignore')
            chunks = CodeParser.parse_by_functions(content_str, language, file.filename)
            
            results.append({
                "file_id": file_id,
                "filename": file.filename,
                "size": len(content),
                "chunks": len(chunks)
            })
        except Exception as e:
            logger.error(f"Batch upload error for {file.filename}: {e}")
            results.append({"filename": file.filename, "error": str(e)})
    
    return {
        "session_id": resolved_session_id,
        "uploaded_files": results,
        "total": len(results),
    }


@router.post("/zip", response_model=dict)
@limiter.limit("10/hour")
async def upload_zip(
    request: Request,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """
    Upload and extract a .zip file containing code files
    
    - **file**: Zip file containing source code
    - **session_id**: Browser-generated session identifier
    
    Returns:
    - upload_id: Unique identifier for this upload
    - session_id: Session the upload is associated with
    - extracted_files: List of extracted code files with metadata
    - temp_directory: Path where files are temporarily stored
    """
    resolved_session_id = _resolve_session_id(session_id, x_session_id)
    get_session_store().get_or_create(resolved_session_id)

    if file.filename is None:
        raise HTTPException(status_code=400, detail="Invalid file")
    
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(
            status_code=400,
            detail="Only .zip files are supported"
        )
    
    try:
        from app.utils.zip_handler import get_zip_extractor
        
        zip_content = await file.read()
        if len(zip_content) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"ZIP payload exceeds {settings.MAX_FILE_SIZE // (1024 * 1024)} MB limit",
            )
        
        extractor = get_zip_extractor()
        temp_dir, extracted_files = await extractor.extract_zip(zip_content)
        
        if not extracted_files:
            raise HTTPException(
                status_code=400,
                detail="No code files found in zip archive"
            )
        
        total_size = sum(f['size'] for f in extracted_files)
        upload_id = Path(temp_dir).name
        temp_dir = Path(tempfile.gettempdir()) / upload_id
        
        if not temp_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Upload not found: {upload_id}"
            )
        
        response = {
            "session_id": resolved_session_id,
            "upload_id": upload_id,
            "filename": file.filename,
            "zip_size": len(zip_content),
            "extracted_files_count": len(extracted_files),
            "total_extracted_size": total_size,
            "extracted_files": extracted_files,
            "created_at": __import__('datetime').datetime.utcnow().isoformat()
        }
        
        logger.info(
            f"Zip upload successful: {file.filename} -> "
            f"{len(extracted_files)} files extracted to {temp_dir} (session={resolved_session_id})"
        )
        
        return response
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Zip upload failed: {e}")
        raise HTTPException(status_code=500, detail="Zip upload failed")


@router.post("/zip/process")
@limiter.limit("10/hour")
async def process_zip_extraction(
    request: Request,
    upload_id: str,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """
    Process extracted zip files: parse, embed, and store in session memory
    
    - **upload_id**: Upload ID from previous zip upload
    - **session_id**: Browser-generated session identifier
    """
    resolved_session_id = _resolve_session_id(session_id, x_session_id)

    try:
        import os
        temp_dir = _resolve_upload_temp_dir(upload_id)
        
        if not temp_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Upload not found: {upload_id}"
            )
        
        processed_count = 0
        for root, dirs, files in os.walk(temp_dir):
            for filename in files:
                file_path = Path(root) / filename
                try:
                    file_path.read_bytes().decode('utf-8', errors='ignore')
                    processed_count += 1
                except Exception:
                    continue

        if processed_count == 0:
            raise HTTPException(
                status_code=400,
                detail="No valid code files found to process"
            )

        background_tasks.add_task(index_extracted_zip, resolved_session_id, upload_id)

        return {
            "status": "processing",
            "session_id": resolved_session_id,
            "upload_id": upload_id,
            "files_queued": processed_count,
            "message": f"Queued {processed_count} files for processing"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Zip processing failed: {e}")
        raise HTTPException(status_code=500, detail="Zip processing failed")


@router.delete("/zip/{upload_id}")
async def cleanup_zip_extraction(upload_id: str):
    """
    Clean up temporary directory from zip extraction
    
    - **upload_id**: Upload ID from zip upload
    """
    try:
        from app.utils.zip_handler import get_zip_extractor
        temp_dir = _resolve_upload_temp_dir(upload_id)
        
        if not temp_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Upload directory not found: {upload_id}"
            )
        
        extractor = get_zip_extractor()
        success = extractor.cleanup_temp_dir(str(temp_dir))
        
        if success:
            return {
                "status": "deleted",
                "upload_id": upload_id,
                "message": f"Cleaned up {temp_dir}"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to clean up directory"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail="Cleanup failed")


@router.delete("/file/{file_id}")
async def delete_file(
    file_id: str,
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """
    Delete uploaded file and its embeddings from session memory
    
    - **file_id**: File identifier
    - **session_id**: Browser-generated session identifier
    """
    resolved_session_id = _resolve_session_id(session_id, x_session_id)

    try:
        retrieval_service = await get_retrieval_service()
        await retrieval_service.delete_chunks(resolved_session_id, file_id)
        
        return {"status": "deleted", "file_id": file_id, "session_id": resolved_session_id}
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(status_code=500, detail="File deletion failed")
