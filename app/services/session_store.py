"""Thread-safe in-memory session store for ephemeral RAG state."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

DEFAULT_SESSION_TTL_SECONDS = 30 * 60  # 30 minutes


@dataclass
class SessionData:
    """In-memory data for a single browser session."""

    chunks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    fingerprints: Set[str] = field(default_factory=set)
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
            session.touch()
            logger.info(
                "session_cleared session_id=%s chunks_removed=%d",
                session_id,
                cleared,
            )
            return cleared


_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """Get or create the global session store singleton."""
    global _session_store
    if _session_store is None:
        from app.utils.config import get_settings

        settings = get_settings()
        _session_store = SessionStore(ttl_seconds=settings.SESSION_TTL_SECONDS)
    return _session_store
