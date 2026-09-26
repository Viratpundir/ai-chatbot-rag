from __future__ import annotations

import pytest
from types import SimpleNamespace

from app.agent.guide import AIGuideAgent, build_agent, classify_intent
from app.agent.registry import ToolDefinition, ToolRegistry
from app.auth.permissions import can_user_upload_documents, restrict_document_ids
from app.database.models import User


def make_user(role: str) -> User:
    return User(id="user-1", name="Test User", email="user@example.com", role=role)


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("Where is the leave policy?", "leave_guidance"),
        ("Guide me through onboarding", "process_guidance"),
        ("I need a VPN support ticket", "create_ticket"),
        ("What can you help me with?", "clarification"),
    ],
)
def test_classify_intent(message: str, intent: str) -> None:
    assert classify_intent(message) == intent


@pytest.mark.asyncio
async def test_action_requires_confirmation() -> None:
    async def create_ticket(arguments, user):
        return "created"

    agent = AIGuideAgent(
        ToolRegistry(
            [
                ToolDefinition(
                    name="create_ticket",
                    description="Create a support ticket.",
                    handler=create_ticket,
                    allowed_roles={"EMPLOYEE"},
                    requires_confirmation=True,
                )
            ]
        )
    )

    pending = await agent.run("I need a support ticket", make_user("EMPLOYEE"))
    assert pending.pending_confirmation == {
        "tool_name": "create_ticket",
        "arguments": {"query": "I need a support ticket"},
    }

    confirmed = await agent.run(
        "Confirm",
        make_user("EMPLOYEE"),
        confirm_action=True,
        pending_action=pending.pending_confirmation,
    )
    assert confirmed.tool_calls[0]["result"] == "created"


@pytest.mark.asyncio
async def test_tool_role_is_enforced() -> None:
    async def admin_tool(arguments, user):
        return "admin result"

    agent = AIGuideAgent(
        ToolRegistry(
            [
                ToolDefinition(
                    name="admin_tool",
                    description="Admin-only action.",
                    handler=admin_tool,
                    allowed_roles={"ADMIN"},
                )
            ]
        )
    )

    with pytest.raises(Exception) as error:
        await agent.registry.execute("admin_tool", {}, make_user("STUDENT"))
    assert error.value.status_code == 403


def test_restrict_document_ids_keeps_only_authorized_selection() -> None:
    allowed = {"doc-1", "doc-2", "doc-3"}

    assert restrict_document_ids(allowed, ["doc-2", "doc-9"], all_authorized=False) == {"doc-2"}
    assert restrict_document_ids(allowed, ["doc-2", "doc-3"], all_authorized=True) == allowed


def test_upload_role_policy_is_configurable() -> None:
    assert can_user_upload_documents(make_user("SUPER_ADMIN")) is True
    assert can_user_upload_documents(make_user("ADMIN")) is True
    assert can_user_upload_documents(make_user("EMPLOYEE")) is True
    assert can_user_upload_documents(make_user("STUDENT")) is True


@pytest.mark.asyncio
async def test_guide_passes_selected_document_ids_to_rag() -> None:
    received = {}

    async def rag_query(question, user, document_ids=None, all_authorized=True):
        received.update({
            "question": question,
            "document_ids": document_ids,
            "all_authorized": all_authorized,
        })
        return SimpleNamespace(answer="Grounded result", citations=[])

    result = await build_agent(rag_query).run(
        "Summarize the selected policy",
        make_user("EMPLOYEE"),
        document_ids=["doc-1"],
        all_authorized=False,
    )

    assert received == {
        "question": "Summarize the selected policy",
        "document_ids": ["doc-1"],
        "all_authorized": False,
    }
    assert result.reply == "Grounded result"