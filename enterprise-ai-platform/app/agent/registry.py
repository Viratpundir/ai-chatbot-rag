"""Explicit registry for role-aware AI Guide tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, Set

from fastapi import HTTPException, status

from app.database.models import User


ToolHandler = Callable[[Dict[str, Any], User], Awaitable[Any]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    handler: ToolHandler
    allowed_roles: Set[str]
    required_permissions: Set[str] = frozenset()
    requires_confirmation: bool = False


class ToolRegistry:
    """Register and execute only explicitly approved tools."""

    def __init__(self, tools: Optional[Iterable[ToolDefinition]] = None) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        for tool in tools or ():
            self.register(tool)

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The requested agent tool is not available.",
            ) from exc

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def can_use(self, tool: ToolDefinition, user: User) -> bool:
        if user.role == "SUPER_ADMIN":
            return True
        return user.role in tool.allowed_roles

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        user: User,
        confirm_action: bool = False,
    ) -> tuple[Any, bool]:
        tool = self.get(name)
        if not self.can_use(tool, user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to use this agent tool.",
            )
        if tool.requires_confirmation and not confirm_action:
            return None, True
        return await tool.handler(arguments, user), False