"""Application configuration"""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # Server
    DEBUG: bool = True
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"
    API_ACCESS_KEY: str | None = None
    AUTH_ENABLED: bool = True
    RATE_LIMIT_ENABLED: bool = True
    
    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:8080",
    ]
    PRODUCTION_ALLOWED_ORIGINS: List[str] = [
        "https://anikait.page",
        "https://www.anikait.page",
    ]
    
    # File Upload
    MAX_FILE_SIZE: int = 25 * 1024 * 1024  # 25MB
    UPLOAD_DIR: str = "uploads"
    ALLOWED_EXTENSIONS: List[str] = [
        ".py", ".js", ".ts", ".java", ".cpp", ".c", ".go", ".rs", ".rb"
    ]
    
    # Embedding
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    
    # Session Store
    SESSION_TTL_SECONDS: int = 30 * 60  # 30 minutes inactivity
    SESSION_CLEANUP_INTERVAL_SECONDS: int = 5 * 60  # background cleanup every 5 min
    
    # LLM (Gemini key is supplied per-request by the user — not stored server-side)
    LLM_MODEL: str = "gemini-2.5-flash"
    LLM_TEMPERATURE: float = 0.7
    GOOGLE_LLM_MODEL: str = "gemini-2.5-flash"
    RAG_LOG_PATH: str = "logs/rag_queries.jsonl"
    
    # Processing
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def auth_enabled(self) -> bool:
        return self.AUTH_ENABLED

    @property
    def rate_limit_enabled(self) -> bool:
        return self.RATE_LIMIT_ENABLED

    @property
    def effective_allowed_origins(self) -> List[str]:
        if self.is_production:
            return self.PRODUCTION_ALLOWED_ORIGINS
        return self.ALLOWED_ORIGINS


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get application settings"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
