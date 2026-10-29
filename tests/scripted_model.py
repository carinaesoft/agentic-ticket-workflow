"""A ChatModel that replays a fixed script of replies and records what it was sent."""

from __future__ import annotations

import copy
import json
from typing import Any

from app.adapters.llm import Message, ModelReply, ToolCall


def tool_call(name: str, arguments: dict[str, Any] | None = None, call_id: str | None = None):
    return ModelReply(
        tool_calls=[
            ToolCall(
                id=call_id or f"call_{name}", name=name, arguments_json=json.dumps(arguments or {})
            )
        ]
    )


def answer(decision: dict[str, Any] | str) -> ModelReply:
    return ModelReply(content=decision if isinstance(decision, str) else json.dumps(decision))


class ScriptedModel:
    def __init__(self, replies: list[ModelReply], repeat_last: bool = False) -> None:
        self._replies = list(replies)
        self._repeat_last = repeat_last
        self.calls: list[list[Message]] = []

    async def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelReply:
        self.calls.append(copy.deepcopy(messages))
        if len(self._replies) == 1 and self._repeat_last:
            return self._replies[0]
        return self._replies.pop(0)
