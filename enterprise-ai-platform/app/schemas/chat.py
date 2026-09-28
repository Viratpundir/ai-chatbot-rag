"""
app/schemas/chat.py
-------------------
Pydantic schemas for chat, conversation, and agent endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Chat / RAG
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[str] = None   # continue existing conversation
    document_ids: Optional[List[str]] = None
    all_authorized: bool = False


class CitationItem(BaseModel):
    index: int
    filename: str
    page: Optional[int] = None
    document_id: Optional[str] = None
    section: Optional[str] = None
    subsection: Optional[str] = None
    excerpt: str
    vector_score: Optional[float] = None
    bm25_score: Optional[float] = None
    hybrid_score: Optional[float] = None
    rerank_score: Optional[float] = None


class ChatResponse(BaseModel):
    answer: str
    citations: List[CitationItem] = []
    has_answer: bool
    conversation_id: str
    message_id: str
    retrieval_time_ms: float
    reranking_time_ms: float = 0.0
    embedding_time_ms: float = 0.0
    vector_search_time_ms: float = 0.0
    permission_filter_time_ms: float = 0.0
    lexical_search_time_ms: float = 0.0
    context_time_ms: float = 0.0
    prompt_time_ms: float = 0.0
    llm_time_ms: float
    llm_first_token_ms: Optional[float] = None
    time_to_first_token_ms: Optional[float] = None
    prompt_chars: int = 0
    approximate_prompt_tokens: int = 0
    total_time_ms: float
    model: str
    retrieval_debug: List[Dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

class ConversationCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)


class ConversationRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class MessageResponse(BaseModel):
    message_id: str
    role: str          # "user" | "assistant"
    content: str
    created_at: datetime
    citations: Optional[List[CitationItem]] = None

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    conversation_id: str
    title: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    message_count: int = 0

    model_config = {"from_attributes": True}


class ConversationDetailResponse(ConversationResponse):
    messages: List[MessageResponse] = []


class ConversationListResponse(BaseModel):
    conversations: List[ConversationResponse]
    total: int


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    all_authorized: bool = False
    confirm_action: Optional[bool] = None   # user confirming a pending action
    pending_action: Optional[Dict[str, Any]] = None

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter a question or task for the AI Guide.")
        return value


class AgentToolCall(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    execution_time_ms: Optional[float] = None


class AgentResponse(BaseModel):
    reply: str
    intent: Optional[str] = None
    tool_calls: List[AgentToolCall] = []
    pending_confirmation: Optional[Dict[str, Any]] = None  # action awaiting user OK
    conversation_id: str
    message_id: str
    total_time_ms: float
