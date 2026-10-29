"""Chat model protocol and the OpenAI / Azure OpenAI adapter.

Messages and tool calls use the Chat Completions shape, so the fake model and the real
adapter are interchangeable behind ``ChatModel``.
"""

from __future__ import annotations

from typing import Any, Protocol

import openai
from pydantic import BaseModel, Field

from app.config import Settings

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


# --- Real model: OpenAI and Azure OpenAI ------------------------------------------------

REQUEST_TIMEOUT_SECONDS = 20.0

# Request parameters per provider, besides model, messages and tools. Only parameters the
# official docs allow for the default model (gpt-6-luna) are sent:
# - reasoning_effort="none": Chat Completions function calling works only with "none"
#   (OpenAI gpt-6-luna model page; Azure reasoning models how-to). The default is "medium".
# - no temperature: allowed only with effort "none" and not confirmed for 0 (OpenAI), and
#   listed as unsupported for reasoning models (Azure); the default is used.
# - no tool_choice: "auto" is already the default when tools are present.
# - no response_format: JSON mode is not documented for gpt-6-luna; the prompt asks for
#   JSON and the agent loop re-prompts on an unreadable answer.
OPENAI_REQUEST_PARAMS: dict[str, Any] = {"reasoning_effort": "none"}
# Assumes the deployment runs the default model (or another one that accepts "none").
AZURE_REQUEST_PARAMS: dict[str, Any] = {"reasoning_effort": "none"}


class LLMConfigError(Exception):
    """Provider settings are missing or invalid; retrying cannot fix it."""


class OpenAIChatModel:
    """Chat Completions adapter for ``AsyncOpenAI`` and ``AsyncAzureOpenAI`` clients.

    The client is created with ``max_retries=0``: Temporal's activity retry policy is the
    only retry layer.
    """

    def __init__(self, client: Any, model: str, extra_params: dict[str, Any] | None = None):
        self._client = client
        self._model = model
        self._extra_params = extra_params or {}

    async def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelReply:
        response = await self._client.chat.completions.create(
            model=self._model, messages=messages, tools=tools, **self._extra_params
        )
        message = response.choices[0].message
        return ModelReply(
            content=message.content,
            tool_calls=[
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments_json=call.function.arguments or "",
                )
                for call in message.tool_calls or []
                if call.type == "function"
            ],
        )


def build_chat_model(settings: Settings) -> ChatModel:
    """The chat model selected by ``LLM_PROVIDER``; fails fast on missing settings."""
    if settings.llm_provider == "fake":
        from app.adapters.fake_llm import FakeChatModel

        return FakeChatModel()

    if settings.llm_provider == "openai":
        if settings.openai_api_key is None:
            raise LLMConfigError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
        client = openai.AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            max_retries=0,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        return OpenAIChatModel(client, settings.openai_model, OPENAI_REQUEST_PARAMS)

    missing = [
        name
        for name, value in (
            ("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key),
            ("AZURE_OPENAI_ENDPOINT", settings.azure_openai_endpoint),
            ("AZURE_OPENAI_DEPLOYMENT", settings.azure_openai_deployment),
        )
        if not value
    ]
    if missing:
        raise LLMConfigError(f"LLM_PROVIDER=azure requires {', '.join(missing)}")
    return OpenAIChatModel(
        _azure_client(settings), settings.azure_openai_deployment, AZURE_REQUEST_PARAMS
    )


def _azure_client(settings: Settings) -> Any:
    """The v1 API (``/openai/v1/``, no api-version) unless a dated version is set.

    A dated ``AZURE_OPENAI_API_VERSION`` must be 2024-12-01-preview or later, the first
    version with ``reasoning_effort``.
    """
    api_key = settings.azure_openai_api_key.get_secret_value()
    if settings.azure_openai_api_version is None:
        return openai.AsyncOpenAI(
            api_key=api_key,
            base_url=f"{settings.azure_openai_endpoint.rstrip('/')}/openai/v1/",
            max_retries=0,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    return openai.AsyncAzureOpenAI(
        api_key=api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        max_retries=0,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
