"""
app/api/v1/chat.py
------------------
Chat and conversation endpoints.

Stage 1:  /chat/ask is fully wired to the RAG pipeline (no auth yet).
          All conversation-history endpoints are stubs (Stage 11).
Stage 5:  Auth middleware injected.
Stage 6:  allowed_document_ids derived from user role.
Stage 11: Conversation persistence.
"""

from __future__ import annotations

import uuid
import asyncio
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import StreamingResponse

from app.agent.guide import build_agent
from app.auth.jwt import get_current_user
from app.auth.permissions import get_allowed_document_ids_for_user, restrict_document_ids
from app.core.config import settings
from app.core.logging import get_logger, request_id_var
from app.database.database import get_db
from app.database.models import User
from app.database.repositories import AuditLogRepository, ConversationRepository
from app.rag.pipeline import RAGProviderError, RAGProviderTimeout, build_pipeline
from app.schemas.chat import (
    AgentRequest,
    AgentResponse,
    AgentToolCall,
    ChatRequest,
    ChatResponse,
    CitationItem,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationRename,
    ConversationResponse,
    MessageResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])


@dataclass
class _PreparedChat:
    repository: ConversationRepository
    conversation_id: str
    pipeline: Any
    endpoint: str
    auth_ms: Optional[float]
    database_ms: float
    authorization_ms: float


def _safe_exception_message(exc: Exception) -> str:
    message = str(exc)
    if settings.OPENAI_API_KEY:
        message = message.replace(settings.OPENAI_API_KEY, "[redacted]")
    message = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [redacted]", message)
    message = re.sub(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)(\s*[:=]\s*)[^\s,;]+",
        r"\1\2[redacted]",
        message,
    )
    return message[:500]


def _chat_http_error(
    exc: Exception,
    *,
    user_id: str,
    endpoint: str,
    stage: str,
) -> HTTPException:
    if isinstance(exc, RAGProviderTimeout):
        code, detail = status.HTTP_504_GATEWAY_TIMEOUT, "The AI service took too long to respond. Please try again."
    elif isinstance(exc, RAGProviderError):
        code, detail = status.HTTP_503_SERVICE_UNAVAILABLE, "The AI service is temporarily unavailable. Please try again."
    else:
        code, detail = status.HTTP_500_INTERNAL_SERVER_ERROR, "Something went wrong while processing your question. Please try again."
    logger.error(
        "RAG API request failed",
        extra={
            "request_id": request_id_var.get(""),
            "user_id": user_id,
            "endpoint": endpoint,
            "stage": stage,
            "exception_type": type(exc).__name__,
            "exception_message": _safe_exception_message(exc),
            "status_code": code,
        },
    )
    return HTTPException(status_code=code, detail=detail)


async def _prepare_chat(
    body: ChatRequest,
    current_user: User,
    db,
    request: Request,
) -> _PreparedChat:
    database_started = time.perf_counter()
    conversation_repo = ConversationRepository(db)
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reset_at = day_start + timedelta(days=1)
    questions_today = await conversation_repo.count_user_messages_since(
        current_user.id, day_start
    )
    if questions_today >= settings.DAILY_CHAT_LIMIT:
        retry_after = max(1, int((reset_at - now).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily chat limit reached ({settings.DAILY_CHAT_LIMIT} questions). Try again after UTC midnight.",
            headers={"Retry-After": str(retry_after)},
        )

    if body.conversation_id:
        conversation = await conversation_repo.get_conversation(
            body.conversation_id, current_user.id
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
    else:
        conversation = await conversation_repo.create_conversation(
            user_id=current_user.id,
            title=body.question[:80],
        )

    history = conversation_repo.format_history(
        await conversation_repo.get_recent_messages(conversation.id)
    )
    await conversation_repo.add_message(
        conversation_id=conversation.id,
        role="user",
        content=body.question,
    )
    database_ms = (time.perf_counter() - database_started) * 1000

    authorization_started = time.perf_counter()
    allowed_ids = await get_allowed_document_ids_for_user(current_user, db)
    if body.document_ids and not body.all_authorized:
        unauthorized_ids = set(body.document_ids) - allowed_ids
        if unauthorized_ids:
            logger.warning(
                "Unauthorized document selection in RAG request",
                extra={"user_id": current_user.id},
            )
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access one or more selected documents.",
            )
    selected_scope = restrict_document_ids(
        allowed_ids,
        selected_document_ids=body.document_ids,
        all_authorized=body.all_authorized,
    )
    if body.document_ids and not selected_scope:
        raise HTTPException(status_code=422, detail="Select at least one ready document.")
    authorization_ms = (time.perf_counter() - authorization_started) * 1000

    request_log = {
        "request_id": request_id_var.get(""),
        "user_id": current_user.id,
        "endpoint": request.url.path,
        "auth_ms": getattr(request.state, "auth_elapsed_ms", None),
        "database_ms": round(database_ms, 1),
        "authorization_ms": round(authorization_ms, 1),
        "authorized_document_count": len(allowed_ids),
        "selected_document_count": len(body.document_ids or []),
        "question_length": len(body.question),
        "all_authorized": body.all_authorized,
    }
    logger.info("RAG request prepared", extra=request_log)

    return _PreparedChat(
        repository=conversation_repo,
        conversation_id=conversation.id,
        endpoint=request.url.path,
        pipeline=build_pipeline(
            allowed_document_ids=selected_scope,
            user_id=current_user.id,
            conversation_history=history,
        ),
        auth_ms=getattr(request.state, "auth_elapsed_ms", None),
        database_ms=database_ms,
        authorization_ms=authorization_ms,
    )


async def _persist_chat_response(
    prepared: _PreparedChat,
    rag_response,
    current_user: User,
    db,
    first_token_request_ms: Optional[float] = None,
) -> ChatResponse:
    persistence_started = time.perf_counter()
    citations = [CitationItem(**citation) for citation in rag_response.citations]
    assistant_message = await prepared.repository.add_message(
        conversation_id=prepared.conversation_id,
        role="assistant",
        content=rag_response.answer,
        citations=rag_response.citations,
        retrieval_time_ms=rag_response.retrieval_time_ms,
        llm_time_ms=rag_response.llm_time_ms,
        total_time_ms=rag_response.total_time_ms,
        model_used=rag_response.model,
        has_answer=rag_response.has_answer,
    )
    await AuditLogRepository(db).log(
        action="rag_query",
        user_id=current_user.id,
        resource_type="conversation",
        resource_id=prepared.conversation_id,
        metadata={
            "query_length": len(rag_response.query),
            "chunks": len(rag_response.context_docs),
        },
    )
    persistence_ms = (time.perf_counter() - persistence_started) * 1000
    logger.info(
        "RAG response persisted",
        extra={
            "request_id": request_id_var.get(""),
            "user_id": current_user.id,
            "endpoint": "/api/v1/chat/ask",
            "source_endpoint": prepared.endpoint,
            "database_persistence_ms": round(persistence_ms, 1),
            "context_chunks": len(rag_response.context_docs),
            "citation_count": len(rag_response.citations),
        },
    )
    return ChatResponse(
        answer=rag_response.answer,
        citations=citations,
        has_answer=rag_response.has_answer,
        conversation_id=prepared.conversation_id,
        message_id=assistant_message.id,
        retrieval_time_ms=rag_response.retrieval_time_ms,
        reranking_time_ms=rag_response.reranking_time_ms,
        embedding_time_ms=rag_response.embedding_time_ms,
        vector_search_time_ms=rag_response.vector_search_time_ms,
        permission_filter_time_ms=rag_response.permission_filter_time_ms,
        lexical_search_time_ms=rag_response.lexical_search_time_ms,
        context_time_ms=rag_response.context_time_ms,
        prompt_time_ms=rag_response.prompt_time_ms,
        llm_time_ms=rag_response.llm_time_ms,
        llm_first_token_ms=rag_response.llm_first_token_ms,
        time_to_first_token_ms=first_token_request_ms,
        prompt_chars=rag_response.prompt_chars,
        approximate_prompt_tokens=rag_response.approximate_prompt_tokens,
        total_time_ms=rag_response.total_time_ms,
        model=rag_response.model,
        retrieval_debug=rag_response.retrieval_debug,
    )


# ---------------------------------------------------------------------------
# RAG Chat  (Stage 1: live, no auth)
# ---------------------------------------------------------------------------

@router.post(
    "/ask",
    response_model=ChatResponse,
    summary="Ask a question against authorised documents",
)
async def ask(
    body: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Run the full RAG pipeline for *question*.

    Stage 1:  No authentication — open access (dev / demo only).
    Stage 5+: Authenticated user's allowed_document_ids are injected here.

    Returns a grounded answer with source citations and latency metrics.
    """
    stage = "request_setup"
    try:
        prepared = await _prepare_chat(body, current_user, db, request)
        stage = "rag_pipeline"
        rag_response = await asyncio.to_thread(prepared.pipeline.query, body.question)
        stage = "history_persistence"
        response = await _persist_chat_response(prepared, rag_response, current_user, db)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise _chat_http_error(
            exc,
            user_id=current_user.id,
            endpoint=request.url.path,
            stage=stage,
        ) from exc

    logger.info(
        "RAG API request completed",
        extra={
            "request_id": request_id_var.get(""),
            "user_id": current_user.id,
            "endpoint": request.url.path,
            "auth_ms": prepared.auth_ms,
            "database_ms": round(prepared.database_ms, 1),
            "authorization_ms": round(prepared.authorization_ms, 1),
            "request_elapsed_ms": round(
                (time.perf_counter() - getattr(request.state, "request_started_at", time.perf_counter())) * 1000,
                1,
            ),
            "retrieval_ms": rag_response.retrieval_time_ms,
            "embedding_ms": rag_response.embedding_time_ms,
            "vector_search_ms": rag_response.vector_search_time_ms,
            "permission_filter_ms": rag_response.permission_filter_time_ms,
            "lexical_search_ms": rag_response.lexical_search_time_ms,
            "reranking_ms": rag_response.reranking_time_ms,
            "context_ms": rag_response.context_time_ms,
            "prompt_ms": rag_response.prompt_time_ms,
            "prompt_chars": rag_response.prompt_chars,
            "approximate_prompt_tokens": rag_response.approximate_prompt_tokens,
            "llm_ms": rag_response.llm_time_ms,
            "llm_first_token_ms": rag_response.llm_first_token_ms,
            "rag_pipeline_ms": rag_response.total_time_ms,
            "context_chunks": len(rag_response.context_docs),
            "citation_count": len(rag_response.citations),
        },
    )
    return response


@router.post("/ask/stream", summary="Stream a document-grounded answer with citations")
async def ask_stream(
    body: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        prepared = await _prepare_chat(body, current_user, db, request)
    except HTTPException:
        raise
    except Exception as exc:
        raise _chat_http_error(
            exc,
            user_id=current_user.id,
            endpoint=request.url.path,
        ) from exc

    token_queue: asyncio.Queue[str] = asyncio.Queue()
    cancelled = threading.Event()
    loop = asyncio.get_running_loop()
    request_started_at = getattr(request.state, "request_started_at", time.perf_counter())
    first_token_request_ms: Optional[float] = None

    def queue_token(token: str) -> None:
        nonlocal first_token_request_ms
        if first_token_request_ms is None:
            first_token_request_ms = (time.perf_counter() - request_started_at) * 1000
            logger.info(
                "RAG first token delivered",
                extra={
                    "request_id": request_id_var.get(""),
                    "user_id": current_user.id,
                    "endpoint": request.url.path,
                    "time_to_first_token_ms": round(first_token_request_ms, 1),
                },
            )
        token_queue.put_nowait(token)

    def on_token(token: str) -> None:
        loop.call_soon_threadsafe(queue_token, token)

    def encode_event(event: str, payload: Dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"

    async def events():
        yield encode_event("status", {"stage": "retrieval"})
        stage = "rag_pipeline"
        generation = asyncio.create_task(
            asyncio.to_thread(
                prepared.pipeline.query_stream,
                body.question,
                on_token,
                None,
                cancelled.is_set,
            )
        )
        try:
            while not generation.done() or not token_queue.empty():
                if await request.is_disconnected():
                    cancelled.set()
                    await db.rollback()
                    return
                try:
                    token = await asyncio.wait_for(token_queue.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                yield encode_event("token", {"token": token})

            rag_response = await generation
            stage = "history_persistence"
            response = await _persist_chat_response(
                prepared,
                rag_response,
                current_user,
                db,
                first_token_request_ms=first_token_request_ms,
            )
            logger.info(
                "RAG API request completed",
                extra={
                    "request_id": request_id_var.get(""),
                    "user_id": current_user.id,
                    "endpoint": request.url.path,
                    "auth_ms": prepared.auth_ms,
                    "database_ms": round(prepared.database_ms, 1),
                    "authorization_ms": round(prepared.authorization_ms, 1),
                    "request_to_first_token_ms": round(first_token_request_ms, 1) if first_token_request_ms is not None else None,
                    "request_elapsed_ms": round((time.perf_counter() - request_started_at) * 1000, 1),
                    "rag_pipeline_ms": rag_response.total_time_ms,
                    "context_chunks": len(rag_response.context_docs),
                    "citation_count": len(rag_response.citations),
                },
            )
            yield encode_event("complete", response.model_dump())
        except asyncio.CancelledError:
            cancelled.set()
            generation.cancel()
            await db.rollback()
            raise
        except Exception as exc:
            cancelled.set()
            await db.rollback()
            http_error = _chat_http_error(
                exc,
                user_id=current_user.id,
                endpoint=request.url.path,
                stage=stage,
            )
            yield encode_event(
                "error",
                {"message": http_error.detail, "retryable": True},
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Conversations (Stage 11 stubs)
# ---------------------------------------------------------------------------

@router.get("/stats", summary="Get current user's chat statistics")
async def chat_stats(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reset_at = day_start + timedelta(days=1)
    repository = ConversationRepository(db)
    questions_today = await repository.count_user_messages_since(
        current_user.id, day_start
    )
    return {
        "questions_asked": await repository.count_user_messages(current_user.id),
        "questions_today": questions_today,
        "daily_limit": settings.DAILY_CHAT_LIMIT,
        "remaining_today": max(0, settings.DAILY_CHAT_LIMIT - questions_today),
        "resets_at": reset_at.isoformat(),
    }

@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    summary="List current user's conversations",
)
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    repo = ConversationRepository(db)
    conversations, total = await repo.list_conversations(
        current_user.id, offset=(page - 1) * page_size, limit=page_size
    )
    return ConversationListResponse(
        conversations=[
            ConversationResponse(
                conversation_id=c.id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=await repo.count_messages(c.id),
            )
            for c in conversations
        ],
        total=total,
    )


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation",
)
async def create_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    conversation = await ConversationRepository(db).create_conversation(
        user_id=current_user.id, title=body.title or "New Conversation"
    )
    return ConversationResponse(
        conversation_id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Get a conversation with its messages",
)
async def get_conversation(
    conversation_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    repo = ConversationRepository(db)
    conversation = await repo.get_conversation(conversation_id, current_user.id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = [
        MessageResponse(
            message_id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            citations=[CitationItem(**citation) for citation in (message.citations or [])]
            if message.citations else None,
        )
        for message in conversation.messages
    ]
    return ConversationDetailResponse(
        conversation_id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(messages),
        messages=messages,
    )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Rename a conversation",
)
async def rename_conversation(
    body: ConversationRename,
    conversation_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    conversation = await ConversationRepository(db).rename_conversation(
        conversation_id, current_user.id, body.title
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return ConversationResponse(
        conversation_id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=await ConversationRepository(db).count_messages(conversation.id),
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation",
)
async def delete_conversation(
    conversation_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    repo = ConversationRepository(db)
    if await repo.get_conversation(conversation_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    await repo.delete_conversation(conversation_id, current_user.id)
    return None


# ---------------------------------------------------------------------------
# Agent (Stage 16 stub)
# ---------------------------------------------------------------------------

@router.post(
    "/agent",
    response_model=AgentResponse,
    summary="Interact with the AI Guide Agent",
)
async def agent_chat(
    body: AgentRequest,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    AI Guide Agent — understands intent and selects an explicitly registered
    tool. RAG tools receive only documents allowed for the authenticated user.
    """
    allowed_ids = await get_allowed_document_ids_for_user(current_user, db)

    async def rag_query(
        question: str,
        user: User,
        document_ids=None,
        all_authorized=True,
        response_style="guide",
    ):
        if document_ids and not all_authorized and set(document_ids) - allowed_ids:
            raise HTTPException(
                status_code=403,
                detail="You cannot access one or more selected documents.",
            )
        scope = restrict_document_ids(
            allowed_ids,
            selected_document_ids=document_ids,
            all_authorized=all_authorized,
        )
        pipeline = build_pipeline(
            allowed_document_ids=scope,
            user_id=user.id,
            response_style=response_style,
        )
        try:
            response = await asyncio.to_thread(pipeline.query, question, response_style)
        except Exception as exc:  # noqa: BLE001
            raise _chat_http_error(
                exc,
                user_id=user.id,
                endpoint="/api/v1/chat/agent",
                stage="rag_pipeline",
            ) from exc
        logger.info(
            "AI Guide retrieval completed",
            extra={
                "user_id": user.id,
                "retrieved_chunk_count": len(response.context_docs),
                "citation_count": len(response.citations),
                "llm_status": "answered" if response.has_answer else "insufficient_context",
                "retrieval_debug": response.retrieval_debug if settings.DEBUG_RETRIEVAL else None,
            },
        )
        return response

    result = await build_agent(rag_query).run(
        message=body.message,
        user=current_user,
        confirm_action=body.confirm_action,
        pending_action=body.pending_action,
        document_ids=body.document_ids,
        all_authorized=body.all_authorized,
    )

    tool_calls = [
        AgentToolCall(
            tool_name=call["tool_name"],
            arguments=call["arguments"],
            result=call.get("result"),
        )
        for call in result.tool_calls
    ]
    return AgentResponse(
        reply=result.reply,
        intent=result.intent,
        tool_calls=tool_calls,
        pending_confirmation=result.pending_confirmation,
        conversation_id=body.conversation_id or str(uuid.uuid4()),
        message_id=str(uuid.uuid4()),
        total_time_ms=result.total_time_ms,
    )
