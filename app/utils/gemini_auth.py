"""Resolve per-request Gemini API keys supplied by the client."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException


def resolve_gemini_api_key(
    body_key: Optional[str] = None,
    header_key: Optional[str] = None,
    *,
    required: bool = True,
) -> Optional[str]:
    """
    Resolve Gemini API key from request header or body.

    The key is used in-memory for a single Gemini API call only.
    It is never written to disk, session storage, or logs.
    """
    # Prefer header so the key is less likely to appear in request-body logs
    key = (header_key or body_key or "").strip()
    if not key:
        if required:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Gemini API key is required. "
                    "Provide gemini_api_key in the request body or X-Gemini-Api-Key header."
                ),
            )
        return None
    if len(key) < 20:
        raise HTTPException(status_code=400, detail="Invalid Gemini API key format.")
    return key
