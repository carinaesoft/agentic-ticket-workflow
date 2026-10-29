"""The agent loop.

The model chooses which tools to call; this code executes them and feeds the results back
until the model answers with a decision. Turn and re-prompt limits live here, not in the
prompt. The result is only *shape*-checked (``ProposedDecision``); the business rules run
later, in the workflow.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.adapters.llm import ChatModel, Message, ModelReply
from app.agent.prompts import SYSTEM_PROMPT, reprompt_invalid_output, ticket_envelope
from app.agent.tools import TOOL_SCHEMAS, ToolExecutor
from app.domain.models import ProposedDecision, Ticket

MAX_ERROR_CHARS = 500

_log = logging.getLogger(__name__)


class AgentOutputInvalid(Exception):
    """The model's answer stayed unreadable after the allowed re-prompts."""


class AgentTurnLimit(Exception):
    """The model did not produce a decision within the turn limit."""


@dataclass(frozen=True)
class AgentLimits:
    max_turns: int = 6
    max_parse_retries: int = 2


async def run_agent(
    ticket: Ticket,
    model: ChatModel,
    tools: ToolExecutor,
    limits: AgentLimits | None = None,
    logger: logging.Logger | logging.LoggerAdapter = _log,
    log_extra: dict[str, Any] | None = None,
) -> ProposedDecision:
    limits = limits or AgentLimits()
    extra = log_extra or {}
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": ticket_envelope(ticket)},
    ]
    parse_failures = 0
    for turn in range(1, limits.max_turns + 1):
        reply = await model.complete(messages, TOOL_SCHEMAS)
        if reply.tool_calls:
            messages.append(_assistant_tool_calls(reply))
            for call in reply.tool_calls:
                logger.info(
                    "tool_called",
                    extra={
                        **extra,
                        "turn": turn,
                        "tool": call.name,
                        "arguments": call.arguments_json,
                    },
                )
                result = tools.run(call.name, call.arguments_json)
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)}
                )
            continue

        try:
            decision = ProposedDecision.model_validate_json(reply.content or "")
        except ValidationError as exc:
            parse_failures += 1
            error = _short_error(exc)
            logger.warning(
                "agent_output_invalid",
                extra={**extra, "turn": turn, "parse_failures": parse_failures, "error": error},
            )
            if parse_failures > limits.max_parse_retries:
                raise AgentOutputInvalid(
                    f"model output unreadable after {limits.max_parse_retries} re-prompts: {error}"
                ) from None
            messages.append({"role": "assistant", "content": reply.content or ""})
            messages.append({"role": "user", "content": reprompt_invalid_output(error)})
            continue

        logger.info(
            "agent_decided",
            extra={**extra, "turn": turn, "action_kind": decision.action.kind},
        )
        return decision

    raise AgentTurnLimit(f"no decision after {limits.max_turns} turns")


def _assistant_tool_calls(reply: ModelReply) -> Message:
    return {
        "role": "assistant",
        "content": reply.content,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments_json},
            }
            for call in reply.tool_calls
        ],
    }


def _short_error(exc: ValidationError) -> str:
    parts = [f"{'.'.join(map(str, e['loc'])) or 'root'}: {e['msg']}" for e in exc.errors()]
    return "; ".join(parts)[:MAX_ERROR_CHARS]
