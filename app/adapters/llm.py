"""Chat model protocol and the OpenAI / Azure OpenAI adapter.

Messages and tool calls use the Chat Completions shape, so the fake model and the real
adapter are interchangeable behind ``ChatModel``.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

Message = dict[str, Any]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments_json: str


class ModelReply(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class ChatModel(Protocol):
    async def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelReply:
        """Return the model's next message: tool calls, or a final text answer."""
        ...
