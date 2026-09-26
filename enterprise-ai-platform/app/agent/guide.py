"""Role-aware orchestration for the AI Guide Agent.

The first implementation intentionally keeps planning deterministic. The LLM
may later improve intent classification, but it must not decide which Python
functions are callable or bypass the registry's authorization checks.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.agent.registry import ToolDefinition, ToolRegistry
from app.core.logging import AgentTrace, get_logger
from app.database.models import User

logger = get_logger(__name__)


@dataclass(frozen=True)
class AgentResult:
    reply: str
    intent: str
    tool_calls: list[Dict[str, Any]]
    pending_confirmation: Optional[Dict[str, Any]]
    total_time_ms: float


def classify_intent(message: str) -> str:
    text = message.casefold()
    if any(word in text for word in ("leave", "vacation", "holiday")):
        return "leave_guidance"
    if any(word in text for word in ("onboarding", "on-boarding")):
        return "process_guidance"
    if any(word in text for word in ("ticket", "support request", "incident")):
        return "create_ticket"
    if any(word in text for word in ("summarize", "summary", "summarise")):
        return "summarize_documents"
    if any(word in text for word in ("policy", "document", "handbook", "procedure")):
        return "search_documents"
    return "clarification"


class AIGuideAgent:
    """Plan and execute approved tools for one authenticated user."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def run(
        self,
        message: str,
        user: User,
        confirm_action: Optional[bool] = None,
        pending_action: Optional[Dict[str, Any]] = None,
        document_ids: Optional[list[str]] = None,
        all_authorized: bool = True,
    ) -> AgentResult:
        started = time.perf_counter()
        intent = classify_intent(message)
        tool_name = pending_action["tool_name"] if pending_action and confirm_action else {
            "leave_guidance": "search_policies",
            "process_guidance": "search_documents",
            "create_ticket": "create_ticket",
            "summarize_documents": "search_documents",
            "search_documents": "search_documents",
        }.get(intent)

        with AgentTrace(user_id=user.id, intent=intent) as trace:
            if tool_name is None:
                reply = (
                    "Could you clarify what you need help with? For example, "
                    "I can find a policy, explain a process, summarize an "
                    "authorized document, or help troubleshoot an issue."
                )
                trace.set_extra(status="clarification")
                return self._result(reply, intent, [], None, started)

            if pending_action and confirm_action:
                arguments = pending_action.get("arguments", {})
            else:
                arguments = {"query": message}
                if document_ids is not None:
                    arguments["document_ids"] = document_ids
                    arguments["all_authorized"] = all_authorized
            tool = self.registry.get(tool_name)
            trace.set_tool(tool.name)
            result, needs_confirmation = await self.registry.execute(
                tool.name,
                arguments,
                user,
                confirm_action=confirm_action is True,
            )
            if needs_confirmation:
                pending = {"tool_name": tool.name, "arguments": arguments}
                reply = f"I am ready to run {tool.name.replace('_', ' ')}. Please confirm before I proceed."
                return self._result(reply, intent, [], pending, started)

            call = {"tool_name": tool.name, "arguments": arguments, "result": result}
            reply = self._format_result(intent, result)
            return self._result(reply, intent, [call], None, started)

    @staticmethod
    def _format_result(intent: str, result: Any) -> str:
        if isinstance(result, dict) and result.get("answer"):
            return result["answer"]
        if result:
            return str(result)
        return "I could not find enough authorized information to answer that."

    @staticmethod
    def _result(
        reply: str,
        intent: str,
        tool_calls: list[Dict[str, Any]],
        pending_confirmation: Optional[Dict[str, Any]],
        started: float,
    ) -> AgentResult:
        return AgentResult(
            reply=reply,
            intent=intent,
            tool_calls=tool_calls,
            pending_confirmation=pending_confirmation,
            total_time_ms=round((time.perf_counter() - started) * 1000, 1),
        )


def build_agent(rag_query: Any) -> AIGuideAgent:
    """Build the default registry with authorization-preserving tools."""

    async def search_documents(arguments: Dict[str, Any], user: User) -> Dict[str, Any]:
        response = await rag_query(
            arguments["query"],
            user,
            document_ids=arguments.get("document_ids"),
            all_authorized=arguments.get("all_authorized", True),
        )
        return {"answer": response.answer, "citations": response.citations}

    async def search_policies(arguments: Dict[str, Any], user: User) -> Dict[str, Any]:
        return await search_documents(arguments, user)

    async def create_ticket(arguments: Dict[str, Any], user: User) -> str:
        return "Ticket creation is not connected to an enterprise service yet."

    return AIGuideAgent(
        ToolRegistry(
            [
                ToolDefinition(
                    name="search_documents",
                    description="Search documents the authenticated user may access.",
                    handler=search_documents,
                    allowed_roles={"STUDENT", "EMPLOYEE", "ADMIN", "SUPER_ADMIN"},
                ),
                ToolDefinition(
                    name="search_policies",
                    description="Find an authorized policy or procedure.",
                    handler=search_policies,
                    allowed_roles={"STUDENT", "EMPLOYEE", "ADMIN", "SUPER_ADMIN"},
                ),
                ToolDefinition(
                    name="create_ticket",
                    description="Create an IT support ticket after confirmation.",
                    handler=create_ticket,
                    allowed_roles={"EMPLOYEE", "ADMIN", "SUPER_ADMIN"},
                    requires_confirmation=True,
                ),
            ]
        )
    )