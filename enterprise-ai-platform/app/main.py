"""
app/main.py
-----------
Enterprise AI Knowledge Platform — FastAPI application entry point.

Responsibilities
----------------
- Create the FastAPI app with metadata, versioning, and OpenAPI docs.
- Register all v1 API routers under /api/v1/.
- Configure CORS.
- Add request-id middleware.
- Add structured logging middleware.
- Add global exception handlers with safe error responses.
- Expose health and version endpoints at the root level.
- Run startup / shutdown lifecycle hooks.
"""

from __future__ import annotations

import time
import uuid
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import admin, auth, chat, conversations, documents, users
from app.core.config import settings
from app.core.logging import get_logger, request_id_var, setup_logging, user_id_var
from app.database.database import connect_db, disconnect_db
from app.database.database import db_session
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Boot logging as early as possible
# ---------------------------------------------------------------------------
setup_logging(
    level="DEBUG" if settings.DEBUG else "INFO",
    json_output=settings.is_production,
)
logger = get_logger(__name__)


def validate_production_storage_settings() -> None:
    """Fail early when a production deployment would silently use ephemeral storage."""
    if not settings.is_production:
        return

    problems = []
    if settings.DATABASE_URL.startswith("sqlite"):
        problems.append("DATABASE_URL must point to a persistent PostgreSQL database")
    if not os.getenv("JWT_SECRET_KEY"):
        problems.append("JWT_SECRET_KEY must be a stable environment secret")
    if not settings.S3_BUCKET:
        problems.append("S3_BUCKET must be configured for persistent uploaded PDFs")
    if not settings.CELERY_ENABLED:
        problems.append("CELERY_ENABLED must be true so ingestion runs in the worker")
    if urlsplit(settings.REDIS_URL).hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
        problems.append("REDIS_URL must point to the shared production Redis service")
    if not Path(settings.VECTOR_STORE_PATH).is_absolute() and not PurePosixPath(settings.VECTOR_STORE_PATH).is_absolute():
        problems.append("VECTOR_STORE_PATH must be an absolute shared persistent mount")
    if not settings.OPENAI_API_KEY and urlsplit(settings.OLLAMA_HOST).hostname in {
        None, "localhost", "127.0.0.1", "0.0.0.0"
    }:
        problems.append("Configure a reachable OLLAMA_HOST or OPENAI_API_KEY")

    if problems:
        raise RuntimeError("Invalid production configuration: " + "; ".join(problems))


# ---------------------------------------------------------------------------
# Lifespan  (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: validate configuration, warm up singletons.
    Shutdown: release resources gracefully.
    """
    logger.info(
        "Starting Enterprise AI Knowledge Platform",
        extra={
            "version": settings.APP_VERSION,
            "env": settings.APP_ENV,
            "debug": settings.DEBUG,
        },
    )

    validate_production_storage_settings()

    # Ensure upload and vector-store directories exist
    settings.upload_dir_path.mkdir(parents=True, exist_ok=True)
    settings.vector_store_path.mkdir(parents=True, exist_ok=True)

    # Verify database connectivity (non-fatal — app starts even if DB is temporarily down)
    await connect_db()
    if settings.DATABASE_URL.startswith("sqlite"):
        async with db_session() as db:
            await db.execute(
                text(
                    "UPDATE documents "
                    "SET status = 'failed', "
                    "error_message = 'Ingestion interrupted by backend restart', "
                    "processing_completed_at = CURRENT_TIMESTAMP, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE status = 'processing'"
                )
            )

    # Warm up the embedding model so the first request is not slow
    try:
        from app.rag.embeddings import get_embeddings
        get_embeddings()
        logger.info("Embedding model warmed up")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not warm up embedding model", extra={"error": str(exc)})

    yield  # application is now running

    # Graceful shutdown
    await disconnect_db()
    logger.info("Shutting down Enterprise AI Knowledge Platform")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## Enterprise AI Knowledge & Document Intelligence Platform

A production-oriented enterprise AI platform featuring:

- **Secure authentication** — email/password + email OTP
- **Role-Based Access Control** — SUPER_ADMIN / ADMIN / EMPLOYEE / STUDENT
- **Document-level permissions** — users never see documents they are not authorised to access
- **Advanced RAG pipeline** — hybrid semantic + keyword retrieval, cross-encoder reranking, hallucination guardrails, source citations
- **AI Guide Agent** — intent-aware agent with modular tool registry
- **Audit logging** — every sensitive operation is logged
- **Conversation history** — per-user isolated conversation threads

### API Versioning
All endpoints are under `/api/v1/`.

### Authentication
After Stage 5, all protected endpoints require a `Bearer <token>` header.
""",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request-ID + latency middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """
    Inject a unique request_id into every request context.
    Log request start / end with latency.
    Attach X-Request-ID header to the response.
    """
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request_id_var.set(rid)

    start = time.perf_counter()
    request.state.request_started_at = start
    logger.debug(
        "Request started",
        extra={
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else "unknown",
        },
    )

    response = await call_next(request)

    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Process-Time-Ms"] = str(latency_ms)

    logger.info(
        "Request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        },
    )
    return response


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler — returns a safe generic error so stack traces
    never leak to the client in production.
    """
    logger.error(
        "Unhandled exception",
        extra={"path": request.url.path, "error": str(exc)},
        exc_info=exc,
    )
    message = (
        str(exc) if settings.DEBUG
        else "An internal server error occurred. Please try again later."
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_response(500, message),
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=_error_response(404, f"Endpoint not found: {request.url.path}"),
    )


def _error_response(code: int, message: str) -> Dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id_var.get(""),
        }
    }


# ---------------------------------------------------------------------------
# Root health / version endpoints
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "api_docs": f"{settings.API_V1_PREFIX}/docs",
        "health": "/health",
    }


@app.get("/health", tags=["System"])
async def health():
    """Basic liveness probe — returns 200 if the app process is running."""
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
    }


@app.get(f"{settings.API_V1_PREFIX}/health", tags=["System"])
async def api_health():
    return {
        "status": "ok",
        "service": "enterprise-ai-backend",
    }


@app.get("/version", tags=["System"])
async def version():
    return {
        "version": settings.APP_VERSION,
        "name": settings.APP_NAME,
    }


# ---------------------------------------------------------------------------
# Register API v1 routers
# ---------------------------------------------------------------------------

_V1 = settings.API_V1_PREFIX

app.include_router(auth.router,          prefix=_V1)
app.include_router(users.router,         prefix=_V1)
app.include_router(documents.router,     prefix=_V1)
app.include_router(chat.router,          prefix=_V1)
app.include_router(conversations.router, prefix=_V1)
app.include_router(admin.router,         prefix=_V1)

logger.debug(
    "Routers registered",
    extra={"prefix": _V1, "router_count": 6},
)
