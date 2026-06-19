"""Thread-safe in-memory session store for ephemeral RAG state."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

DEFAULT_SESSION_TTL_SECONDS = 30 * 60  # 30 minutes


@dataclass
class SessionData:
    """In-memory data for a single browser session."""

    chunks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    fingerprints: Set[str] = field(default_factory=set)
    project_description: str = ""
    sample_questions: List[str] = field(default_factory=list)
    # Indexing progress (updated during background zip processing)
    indexing_status: str = "idle"  # idle | indexing | complete | error
    indexing_total_files: int = 0
    indexing_processed_files: int = 0
    indexing_current_file: str = ""
    indexing_chunks_created: int = 0
    indexing_error: str = ""
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_accessed_at = time.time()

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    def memory_estimate_bytes(self) -> int:
        """Rough estimate of session memory usage."""
        total = 0
        for item in self.chunks.values():
            total += len(item.get("content", "").encode("utf-8", errors="ignore"))
            embedding = item.get("embedding", [])
            total += len(embedding) * 8  # float64
            meta = item.get("metadata", {})
            total += sum(len(str(v)) for v in meta.values())
        return total


class SessionStore:
    """Thread-safe store mapping session_id to ephemeral RAG data."""

    def __init__(self, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> None:
        self._sessions: Dict[str, SessionData] = {}
        self._lock = threading.RLock()
        self._ttl_seconds = ttl_seconds

    def get_or_create(self, session_id: str) -> SessionData:
        """Return session data, creating a new session if needed."""
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionData()
                logger.info(
                    "session_created session_id=%s active_sessions=%d",
                    session_id,
                    len(self._sessions),
                )
            session = self._sessions[session_id]
            session.touch()
            return session

    def get(self, session_id: str) -> Optional[SessionData]:
        """Return session data without creating a new session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.touch()
            return session

    def delete(self, session_id: str) -> bool:
        """Remove a session and free its memory."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                return False
            freed_bytes = session.memory_estimate_bytes()
            chunk_count = session.chunk_count
            logger.info(
                "session_deleted session_id=%s chunks=%d memory_freed_bytes=%d active_sessions=%d",
                session_id,
                chunk_count,
                freed_bytes,
                len(self._sessions),
            )
            return True

    def cleanup_expired(self) -> int:
        """Remove sessions inactive longer than TTL. Returns count removed."""
        now = time.time()
        expired_ids: list[str] = []

        with self._lock:
            for session_id, session in self._sessions.items():
                if now - session.last_accessed_at > self._ttl_seconds:
                    expired_ids.append(session_id)

        removed = 0
        for session_id in expired_ids:
            if self.delete(session_id):
                removed += 1

        if removed:
            logger.info("memory_freed expired_sessions=%d active_sessions=%d", removed, self.session_count())

        return removed

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def total_chunk_count(self) -> int:
        with self._lock:
            return sum(s.chunk_count for s in self._sessions.values())

    def chunk_count(self, session_id: str) -> int:
        with self._lock:
            session = self._sessions.get(session_id)
            return session.chunk_count if session else 0

    def clear_session(self, session_id: str) -> int:
        """Remove all chunks from a session. Returns chunks cleared."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return 0
            cleared = session.chunk_count
            session.chunks.clear()
            session.fingerprints.clear()
            session.project_description = ""
            session.sample_questions.clear()
            session.indexing_status = "idle"
            session.indexing_total_files = 0
            session.indexing_processed_files = 0
            session.indexing_current_file = ""
            session.indexing_chunks_created = 0
            session.indexing_error = ""
            session.touch()
            logger.info(
                "session_cleared session_id=%s chunks_removed=%d",
                session_id,
                cleared,
            )
            return cleared

    def set_project_overview(
        self,
        session_id: str,
        description: str,
        sample_questions: List[str],
    ) -> None:
        with self._lock:
            session = self.get_or_create(session_id)
            session.project_description = description
            session.sample_questions = list(sample_questions)
            session.touch()

    def get_project_overview(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return {
                    "ready": False,
                    "description": "",
                    "sample_questions": [],
                }
            return {
                "ready": session.chunk_count > 0 and bool(session.sample_questions),
                "description": session.project_description,
                "sample_questions": list(session.sample_questions),
                "total_chunks": session.chunk_count,
            }

    def start_indexing(self, session_id: str, total_files: int) -> None:
        with self._lock:
            session = self.get_or_create(session_id)
            session.indexing_status = "indexing"
            session.indexing_total_files = total_files
            session.indexing_processed_files = 0
            session.indexing_current_file = ""
            session.indexing_chunks_created = 0
            session.indexing_error = ""
            session.touch()

    def update_indexing_progress(
        self,
        session_id: str,
        *,
        processed_files: int,
        current_file: str = "",
        chunks_created: int = 0,
    ) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            session.indexing_processed_files = processed_files
            session.indexing_current_file = current_file
            session.indexing_chunks_created = chunks_created
            session.touch()

    def complete_indexing(self, session_id: str, chunks_created: int) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            session.indexing_status = "complete"
            session.indexing_processed_files = session.indexing_total_files
            session.indexing_current_file = ""
            session.indexing_chunks_created = chunks_created
            session.touch()

    def fail_indexing(self, session_id: str, error: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            session.indexing_status = "error"
            session.indexing_error = error[:500]
            session.touch()

    def get_index_status(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return {
                    "status": "idle",
                    "total_files": 0,
                    "processed_files": 0,
                    "remaining_files": 0,
                    "percent": 0,
                    "current_file": "",
                    "chunks_created": 0,
                    "error": "",
                }
            total = session.indexing_total_files
            processed = session.indexing_processed_files
            remaining = max(0, total - processed)
            percent = int((processed / total) * 100) if total > 0 else 0
            if session.indexing_status == "complete":
                percent = 100
            return {
                "status": session.indexing_status,
                "total_files": total,
                "processed_files": processed,
                "remaining_files": remaining,
                "percent": percent,
                "current_file": session.indexing_current_file,
                "chunks_created": session.indexing_chunks_created,
                "error": session.indexing_error,
            }


_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """Get or create the global session store singleton."""
    global _session_store
    if _session_store is None:
        from app.utils.config import get_settings

        settings = get_settings()
        _session_store = SessionStore(ttl_seconds=settings.SESSION_TTL_SECONDS)
    return _session_store
