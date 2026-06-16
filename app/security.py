"""Shared security utilities (rate limiter)."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.utils.config import get_settings

settings = get_settings()
limiter = Limiter(key_func=get_remote_address, enabled=settings.rate_limit_enabled)
