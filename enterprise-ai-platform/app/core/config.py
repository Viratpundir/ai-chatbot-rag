"""
app/core/config.py
------------------
Centralised settings loaded from environment variables / .env file.
All secrets live in the environment — nothing is hardcoded here.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import AnyHttpUrl, EmailStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root


class Settings(BaseSettings):
    """
    Application settings.  Values are read (in order) from:
      1. Environment variables
      2. .env file in the project root
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_NAME: str = "Enterprise AI Knowledge Platform"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"          # development | staging | production
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    # Generate a strong random key with: python -c "import secrets; print(secrets.token_hex(64))"
    JWT_SECRET_KEY: str = secrets.token_hex(64)   # override in production via env
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    # SQLite keeps the application runnable for local demos. Set DATABASE_URL
    # to PostgreSQL in staging/production.
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'enterprise_ai.db'}"
    DATABASE_ECHO: bool = False

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_ENABLED: bool = False

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------
    EMAIL_HOST: str = "smtp.example.com"
    EMAIL_PORT: int = 587
    EMAIL_USERNAME: str = ""
    EMAIL_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@enterprise.com"
    EMAIL_FROM_NAME: str = "Enterprise AI Platform"
    EMAIL_USE_TLS: bool = True

    # ------------------------------------------------------------------
    # OTP
    # ------------------------------------------------------------------
    OTP_EXPIRE_SECONDS: int = 300          # 5 minutes
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN_SECONDS: int = 60  # 1 minute between resends

    # ------------------------------------------------------------------
    # Email domain restrictions
    # ------------------------------------------------------------------
    # Comma-separated list of allowed domains.  Leave empty to allow all.
    # Example:  ALLOWED_EMAIL_DOMAINS=company.com,university.edu
    ALLOWED_EMAIL_DOMAINS: str = ""

    @property
    def allowed_email_domains_list(self) -> List[str]:
        """Return parsed list of allowed domains (lowercase, stripped)."""
        if not self.ALLOWED_EMAIL_DOMAINS.strip():
            return []
        return [d.strip().lower() for d in self.ALLOWED_EMAIL_DOMAINS.split(",") if d.strip()]

    # ------------------------------------------------------------------
    # Password policy
    # ------------------------------------------------------------------
    PASSWORD_MIN_LENGTH: int = 8
    MAX_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 30

    # ------------------------------------------------------------------
    # LLM / Ollama
    # ------------------------------------------------------------------
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:1b"
    LLM_TEMPERATURE: float = 0.2

    # OpenAI (optional fallback)
    OPENAI_API_KEY: str = ""

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ------------------------------------------------------------------
    # Vector store
    # ------------------------------------------------------------------
    VECTOR_STORE_PATH: str = str(BASE_DIR / "data" / "vector_store")

    # ------------------------------------------------------------------
    # Document storage
    # ------------------------------------------------------------------
    UPLOAD_DIR: str = str(BASE_DIR / "data" / "uploads")
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "docx", "txt", "md", "html"]
    ALLOW_STUDENT_UPLOAD: bool = True
    ALLOW_EMPLOYEE_UPLOAD: bool = True
    UPLOAD_ALLOWED_ROLES: List[str] = ["ADMIN", "SUPER_ADMIN", "EMPLOYEE", "STUDENT"]

    # ------------------------------------------------------------------
    # RAG pipeline
    # ------------------------------------------------------------------
    RETRIEVAL_TOP_K: int = 5
    RERANKER_TOP_N: int = 3
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    INITIAL_RETRIEVAL_K: int = 20
    FINAL_RETRIEVAL_K: int = 5
    VECTOR_WEIGHT: float = 0.6
    BM25_WEIGHT: float = 0.4
    BM25_K1: float = 1.5
    BM25_B: float = 0.75
    RERANKER_ENABLED: bool = True
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    QUERY_EXPANSION_ENABLED: bool = True
    CONTEXT_EXPANSION_ENABLED: bool = True
    CONTEXT_EXPANSION_NEIGHBORS: int = 1
    DEBUG_RETRIEVAL: bool = False

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    # In production, set this to your actual frontend origin(s).
    CORS_ORIGINS: List[str] = ["http://localhost:8501", "http://localhost:3000"]

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("APP_ENV")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v.lower() not in allowed:
            raise ValueError(f"APP_ENV must be one of {allowed}")
        return v.lower()

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def upload_dir_path(self) -> Path:
        p = Path(self.UPLOAD_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def vector_store_path(self) -> Path:
        p = Path(self.VECTOR_STORE_PATH)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    return Settings()


# Convenience alias used throughout the codebase
settings = get_settings()
