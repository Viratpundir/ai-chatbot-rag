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

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.agent.guide import build_agent
from app.auth.jwt import get_current_user
from app.auth.permissions import get_allowed_document_ids_for_user, restrict_document_ids
from app.core.logging import get_logger
from app.database.database import get_db
from app.database.models import User
from app.database.repositories import AuditLogRepository, ConversationRepository
from app.rag.pipeline import build_pipeline
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
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Run the full RAG pipeline for *question*.

    Stage 1:  No authentication — open access (dev / demo only).
    Stage 5+: Authenticated user's allowed_document_ids are injected here.

    Returns a grounded answer with source citations and latency metrics.
    """
    conversation_repo = ConversationRepository(db)
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
    allowed_ids = await get_allowed_document_ids_for_user(current_user, db)
    if body.document_ids and not body.all_authorized:
        unauthorized_ids = set(body.document_ids) - allowed_ids
        if unauthorized_ids:
            logger.warning(
                "[AUTHORIZATION] unauthorized document request",
                extra={"user_id": current_user.id},
            )
            raise HTTPException(
                status_code=403,
                detail="You cannot access one or more selected documents.",
            )
    selected_scope = restrict_document_ids(
        allowed_ids,
        selected_document_ids=body.document_ids,
        all_authorized=body.all_authorized,
    )
    if body.document_ids and not selected_scope:
        raise HTTPException(status_code=422, detail="Select at least one ready document.")

    pipeline = build_pipeline(
        allowed_document_ids=selected_scope,
        user_id=current_user.id,
        conversation_history=history,
    )

    try:
        rag_response = await asyncio.to_thread(pipeline.query, body.question)
    except Exception as exc:
        logger.error("RAG pipeline error", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your question.",
        ) from exc

    citations = [CitationItem(**c) for c in rag_response.citations]

    assistant_message = await conversation_repo.add_message(
        conversation_id=conversation.id,
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
        resource_id=conversation.id,
        metadata={"query_length": len(body.question), "chunks": len(rag_response.context_docs)},
    )

    return ChatResponse(
        answer=rag_response.answer,
        citations=citations,
        has_answer=rag_response.has_answer,
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        retrieval_time_ms=rag_response.retrieval_time_ms,
        llm_time_ms=rag_response.llm_time_ms,
        total_time_ms=rag_response.total_time_ms,
        model=rag_response.model,
        retrieval_debug=rag_response.retrieval_debug,
    )


# ---------------------------------------------------------------------------
# Conversations (Stage 11 stubs)
# ---------------------------------------------------------------------------

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

    async def rag_query(question: str, user: User, document_ids=None, all_authorized=True):
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
        )
        return await asyncio.to_thread(pipeline.query, question)

    result = await build_agent(rag_query).run(
        message=body.message,
        user=current_user,
        confirm_action=body.confirm_action,
        pending_action=body.pending_action,
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
