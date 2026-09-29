from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.auth.jwt import get_current_user
from app.auth.jwt import refresh_access_token
from app.auth.permissions import require_admin
from app.api.v1 import chat
from app.core.config import settings
from app.database.models import User
from app.main import app, should_warm_embeddings_at_startup
from app.schemas.chat import ChatRequest
from app.schemas.auth import RegisterRequest
from app.seed_admin import seed_admin
from app.core.security import create_refresh_token
from app.auth import jwt as jwt_module


def test_vercel_skips_embedding_warmup_but_local_runtime_keeps_it(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    assert should_warm_embeddings_at_startup() is False

    monkeypatch.delenv("VERCEL")
    assert should_warm_embeddings_at_startup() is True


@pytest.mark.parametrize("role", ["EMPLOYEE", "STUDENT"])
def test_registration_accepts_employee_and_student_roles(role: str) -> None:
    request = RegisterRequest(
        name="Test User",
        email="user@example.com",
        password="Strong!Password42",
        role=role,
    )

    assert request.role == role


def test_registration_rejects_privileged_roles() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            name="Test User",
            email="user@example.com",
            password="Strong!Password42",
            role="ADMIN",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["EMPLOYEE", "STUDENT"])
async def test_admin_guard_rejects_non_admin_roles(role: str) -> None:
    user = User(id="user-1", name="Test User", email="user@example.com", role=role)

    with pytest.raises(HTTPException) as error:
        await require_admin(current_user=user)

    assert error.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["ADMIN", "SUPER_ADMIN"])
async def test_admin_guard_accepts_admin_roles(role: str) -> None:
    user = User(id="admin-1", name="Admin User", email="admin@example.com", role=role)

    assert await require_admin(current_user=user) is user


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["EMPLOYEE", "STUDENT"])
async def test_normal_users_get_403_from_admin_apis(role: str) -> None:
    employee = User(id="employee-1", name="Employee", email="employee@example.com", role=role)

    async def current_user_override():
        return employee

    app.dependency_overrides[get_current_user] = current_user_override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            responses = await asyncio.gather(
                client.get("/api/v1/admin/dashboard"),
                client.get("/api/v1/admin/audit-logs"),
                client.get("/api/v1/admin/audit-logs/export"),
                client.post("/api/v1/admin/vector/reindex"),
            )
        assert [response.status_code for response in responses] == [403, 403, 403, 403]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_unauthenticated_user_gets_401_from_admin_dashboard() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/dashboard")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_accepts_naive_sqlite_session_expiry(monkeypatch) -> None:
    user = User(
        id="00000000-0000-0000-0000-000000000013",
        name="Employee",
        email="employee@example.com",
        role="EMPLOYEE",
        is_active=True,
    )
    session = SimpleNamespace(
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
        is_revoked=False,
    )

    class UserRepository:
        def __init__(self, db):
            pass

        async def get_session_by_jti(self, jti):
            return session

        async def get_by_id(self, user_id):
            return user if user_id == user.id else None

        async def touch_session(self, jti):
            pass

    monkeypatch.setattr(jwt_module, "UserRepository", UserRepository)
    tokens = await refresh_access_token(
        create_refresh_token(user.id),
        db=object(),
    )

    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]


@pytest.mark.asyncio
async def test_daily_chat_limit_rejects_before_creating_conversation(monkeypatch) -> None:
    user = User(
        id="00000000-0000-0000-0000-000000000010",
        name="Employee",
        email="employee@example.com",
        role="EMPLOYEE",
    )

    class LimitedConversationRepository:
        def __init__(self, db):
            self.created = False

        async def count_user_messages_since(self, user_id, since):
            return settings.DAILY_CHAT_LIMIT

        async def create_conversation(self, **kwargs):
            self.created = True

    monkeypatch.setattr(chat, "ConversationRepository", LimitedConversationRepository)
    with pytest.raises(HTTPException) as error:
        await chat.ask(
            ChatRequest(question="What is the policy?"),
            request=SimpleNamespace(state=SimpleNamespace()),
            current_user=user,
            db=object(),
        )

    assert error.value.status_code == 429
    assert "Retry-After" in error.value.headers


@pytest.mark.asyncio
async def test_chat_ask_succeeds_with_debug_without_logging_question(monkeypatch, caplog) -> None:
    user = User(
        id="00000000-0000-0000-0000-000000000011",
        name="Employee",
        email="employee@example.com",
        role="EMPLOYEE",
    )

    class ConversationRepository:
        def __init__(self, db):
            pass

        async def count_user_messages_since(self, user_id, since):
            return 0

        async def create_conversation(self, **kwargs):
            return SimpleNamespace(id="conversation-id")

        async def get_recent_messages(self, conversation_id):
            return []

        def format_history(self, messages):
            return "No previous conversation."

        async def add_message(self, *, role, **kwargs):
            return SimpleNamespace(id=f"message-{role}")

    class Pipeline:
        def query(self, question):
            return SimpleNamespace(
                answer="Grounded answer",
                citations=[],
                has_answer=True,
                context_docs=[],
                retrieval_time_ms=1.0,
                reranking_time_ms=0.5,
                embedding_time_ms=0.1,
                vector_search_time_ms=0.1,
                permission_filter_time_ms=0.0,
                lexical_search_time_ms=0.1,
                context_time_ms=0.1,
                prompt_time_ms=0.1,
                llm_time_ms=2.0,
                llm_first_token_ms=None,
                prompt_chars=80,
                approximate_prompt_tokens=20,
                total_time_ms=3.0,
                model="test-model",
                query="What does the policy say?",
                retrieval_debug=[],
            )

    class AuditLogRepository:
        def __init__(self, db):
            pass

        async def log(self, **kwargs):
            pass

    async def allowed_documents(current_user, db):
        return set()

    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(chat, "ConversationRepository", ConversationRepository)
    monkeypatch.setattr(chat, "AuditLogRepository", AuditLogRepository)
    monkeypatch.setattr(chat, "get_allowed_document_ids_for_user", allowed_documents)
    monkeypatch.setattr(chat, "build_pipeline", lambda **kwargs: Pipeline())

    question = "What does the policy say?"
    response = await chat.ask(
        ChatRequest(question=question),
        request=SimpleNamespace(
            state=SimpleNamespace(),
            url=SimpleNamespace(path="/api/v1/chat/ask"),
        ),
        current_user=user,
        db=object(),
    )

    assert response.answer == "Grounded answer"
    assert any(
        record.getMessage() == "RAG request prepared"
        and getattr(record, "question_length", None) == len(question)
        for record in caplog.records
    )
    assert all(getattr(record, "query", None) != question for record in caplog.records)


@pytest.mark.asyncio
async def test_chat_stream_persists_final_answer_and_citations(monkeypatch) -> None:
    user = User(
        id="00000000-0000-0000-0000-000000000012",
        name="Employee",
        email="employee@example.com",
        role="EMPLOYEE",
    )
    stored_messages = []
    audit_entries = []
    citation = {
        "index": 1,
        "filename": "handbook.pdf",
        "page": 7,
        "document_id": "document-1",
        "excerpt": "The policy states the supported facts.",
    }

    class ConversationRepository:
        def __init__(self, db):
            pass

        async def count_user_messages_since(self, user_id, since):
            return 0

        async def create_conversation(self, **kwargs):
            return SimpleNamespace(id="conversation-id")

        async def get_recent_messages(self, conversation_id):
            return []

        def format_history(self, messages):
            return "No previous conversation."

        async def add_message(self, *, role, content, citations=None, **kwargs):
            stored_messages.append({"role": role, "content": content, "citations": citations})
            return SimpleNamespace(id=f"message-{role}")

    class Pipeline:
        def query_stream(self, question, on_token, response_style=None, should_stop=None):
            on_token("Grounded ")
            on_token("answer")
            return SimpleNamespace(
                answer="Grounded answer",
                citations=[citation],
                has_answer=True,
                context_docs=[object()],
                retrieval_time_ms=1.0,
                reranking_time_ms=0.5,
                embedding_time_ms=0.1,
                vector_search_time_ms=0.1,
                permission_filter_time_ms=0.0,
                lexical_search_time_ms=0.1,
                context_time_ms=0.1,
                prompt_time_ms=0.1,
                llm_time_ms=2.0,
                llm_first_token_ms=1.0,
                prompt_chars=80,
                approximate_prompt_tokens=20,
                total_time_ms=3.0,
                model="test-model",
                query=question,
                retrieval_debug=[],
            )

    class AuditLogRepository:
        def __init__(self, db):
            pass

        async def log(self, **kwargs):
            audit_entries.append(kwargs)

    class TestRequest:
        state = SimpleNamespace(auth_elapsed_ms=2.0)
        url = SimpleNamespace(path="/api/v1/chat/ask/stream")

        async def is_disconnected(self):
            return False

    async def allowed_documents(current_user, db):
        return {"document-1"}

    monkeypatch.setattr(chat, "ConversationRepository", ConversationRepository)
    monkeypatch.setattr(chat, "AuditLogRepository", AuditLogRepository)
    monkeypatch.setattr(chat, "get_allowed_document_ids_for_user", allowed_documents)
    monkeypatch.setattr(chat, "build_pipeline", lambda **kwargs: Pipeline())

    response = await chat.ask_stream(
        ChatRequest(question="What does the policy say?"),
        request=TestRequest(),
        current_user=user,
        db=object(),
    )
    body = "".join([chunk async for chunk in response.body_iterator])

    assert response.media_type == "text/event-stream"
    assert 'event: token\ndata: {"token": "Grounded "}' in body
    assert 'event: token\ndata: {"token": "answer"}' in body
    assert 'event: complete\ndata:' in body
    assert [message["role"] for message in stored_messages] == ["user", "assistant"]
    assert stored_messages[-1]["citations"] == [citation]
    assert audit_entries[0]["action"] == "rag_query"


@pytest.mark.asyncio
async def test_admin_audit_list_returns_paginated_response() -> None:
    admin = User(id="00000000-0000-0000-0000-000000000001", name="Admin", email="admin@example.com", role="ADMIN")

    async def current_user_override():
        return admin

    app.dependency_overrides[get_current_user] = current_user_override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/admin/audit-logs?page=1&page_size=10")
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload["logs"], list)
        assert payload["page"] == 1
        assert payload["page_size"] == 10
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_seed_refuses_non_development_environment(monkeypatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "production")

    with pytest.raises(RuntimeError, match="APP_ENV=development"):
        await seed_admin()


@pytest.mark.asyncio
async def test_admin_seed_requires_explicit_email(monkeypatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "")

    with pytest.raises(RuntimeError, match="ADMIN_EMAIL"):
        await seed_admin()
