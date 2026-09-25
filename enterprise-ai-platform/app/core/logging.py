"""
app/core/logging.py
-------------------
Structured JSON logging for the entire platform.

Features
- JSON output in production, human-readable in development
- request_id propagation via contextvars
- Sensitive-field scrubbing (password, otp, token, secret, api_key)
- RAG-specific trace helper (retrieval_time, llm_time, etc.)
- Agent execution trace helper
"""

from __future__ import annotations

import json
import logging
import sys
import time
import traceback
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Context variable – injected by middleware, available everywhere in the stack
# ---------------------------------------------------------------------------
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")

# ---------------------------------------------------------------------------
# Fields that must never appear in logs
# ---------------------------------------------------------------------------
_SCRUB_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "hashed_password",
        "otp",
        "otp_code",
        "otp_hash",
        "token",
        "access_token",
        "refresh_token",
        "jwt",
        "secret",
        "api_key",
        "openai_api_key",
        "email_password",
        "authorization",
    }
)

_SCRUB_PLACEHOLDER = "***REDACTED***"


def _scrub(data: Any, depth: int = 0) -> Any:
    """Recursively redact sensitive keys from dicts / lists."""
    if depth > 8:
        return data
    if isinstance(data, dict):
        return {
            k: _SCRUB_PLACEHOLDER if k.lower() in _SCRUB_KEYS else _scrub(v, depth + 1)
            for k, v in data.items()
        }
    if isinstance(data, (list, tuple)):
        return [_scrub(item, depth + 1) for item in data]
    return data


# ---------------------------------------------------------------------------
# Custom JSON formatter
# ---------------------------------------------------------------------------
class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Attach request / user context if available
        rid = request_id_var.get("")
        uid = user_id_var.get("")
        if rid:
            payload["request_id"] = rid
        if uid:
            payload["user_id"] = uid

        # Extra fields attached via logger.info("msg", extra={...})
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                payload[key] = _scrub(value)

        # Exception info
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(_scrub(payload), default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Human-readable formatter for development
# ---------------------------------------------------------------------------
class DevFormatter(logging.Formatter):
    _COLOURS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        colour = self._COLOURS.get(record.levelname, "")
        rid = request_id_var.get("")
        rid_part = f" [{rid[:8]}]" if rid else ""
        base = (
            f"{colour}{record.levelname:<8}{self._RESET} "
            f"{record.name}{rid_part} | {record.getMessage()}"
        )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


# ---------------------------------------------------------------------------
# Setup function – call once at application startup
# ---------------------------------------------------------------------------
def setup_logging(level: str = "INFO", json_output: bool = False) -> None:
    """
    Configure root logger.

    Args:
        level:       Logging level string (DEBUG / INFO / WARNING / ERROR).
        json_output: Use JSON formatter (True in production, False in dev).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter() if json_output else DevFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore", "faiss"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------
def get_logger(name: str) -> logging.Logger:
    """Return a named logger pre-configured by setup_logging()."""
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Structured trace helpers
# ---------------------------------------------------------------------------
class RAGTrace:
    """
    Context manager that times and logs a full RAG request.

    Usage::

        with RAGTrace(user_id="u1", query="...") as trace:
            trace.set_retrieval_time(0.45)
            trace.set_chunks(5)
            trace.set_llm_time(1.2)
            trace.set_model("llama3.2:1b")
    """

    _log = get_logger("rag.trace")

    def __init__(self, user_id: str, query: str) -> None:
        self.request_id = str(uuid.uuid4())
        self.user_id = user_id
        self._query_length = len(query)
        self._start = 0.0
        self._data: Dict[str, Any] = {
            "request_id": self.request_id,
            "user_id": user_id,
            "query_length": self._query_length,
        }

    def __enter__(self) -> "RAGTrace":
        self._start = time.perf_counter()
        request_id_var.set(self.request_id)
        user_id_var.set(self.user_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._data["total_latency_ms"] = round(
            (time.perf_counter() - self._start) * 1000, 2
        )
        self._data["status"] = "error" if exc_type else "success"
        if exc_type:
            self._data["error"] = str(exc_val)
        self._log.info("rag_request_completed", extra=self._data)

    def set_retrieval_time(self, seconds: float) -> None:
        self._data["retrieval_time_ms"] = round(seconds * 1000, 2)

    def set_reranking_time(self, seconds: float) -> None:
        self._data["reranking_time_ms"] = round(seconds * 1000, 2)

    def set_llm_time(self, seconds: float) -> None:
        self._data["llm_time_ms"] = round(seconds * 1000, 2)

    def set_chunks(self, count: int) -> None:
        self._data["chunks_retrieved"] = count

    def set_model(self, model: str) -> None:
        self._data["model"] = model

    def set_extra(self, **kwargs: Any) -> None:
        self._data.update(kwargs)


class AgentTrace:
    """
    Context manager that logs an AI agent execution trace.

    Usage::

        with AgentTrace(user_id="u1", intent="search_documents") as trace:
            trace.set_tool("search_documents")
            trace.set_tool_time(0.3)
    """

    _log = get_logger("agent.trace")

    def __init__(self, user_id: str, intent: Optional[str] = None) -> None:
        self.request_id = str(uuid.uuid4())
        self.user_id = user_id
        self._start = 0.0
        self._data: Dict[str, Any] = {
            "request_id": self.request_id,
            "user_id": user_id,
            "intent": intent or "unknown",
        }

    def __enter__(self) -> "AgentTrace":
        self._start = time.perf_counter()
        request_id_var.set(self.request_id)
        user_id_var.set(self.user_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._data["total_latency_ms"] = round(
            (time.perf_counter() - self._start) * 1000, 2
        )
        self._data["status"] = "error" if exc_type else "success"
        if exc_type:
            self._data["error"] = str(exc_val)
        self._log.info("agent_execution_completed", extra=self._data)

    def set_tool(self, tool_name: str) -> None:
        self._data["selected_tool"] = tool_name

    def set_tool_time(self, seconds: float) -> None:
        self._data["tool_execution_time_ms"] = round(seconds * 1000, 2)

    def set_retrieval_time(self, seconds: float) -> None:
        self._data["retrieval_time_ms"] = round(seconds * 1000, 2)

    def set_llm_time(self, seconds: float) -> None:
        self._data["llm_time_ms"] = round(seconds * 1000, 2)

    def set_extra(self, **kwargs: Any) -> None:
        self._data.update(kwargs)
