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
            model=self._model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0,
            response_format={"type": "json_object"},
            **self._extra_params,
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
        # The default model only supports function calling in Chat Completions with
        # reasoning_effort="none" (OpenAI model docs).
        return OpenAIChatModel(client, settings.openai_model, {"reasoning_effort": "none"})

    missing = [
        name
        for name, value in (
            ("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key),
            ("AZURE_OPENAI_ENDPOINT", settings.azure_openai_endpoint),
            ("AZURE_OPENAI_DEPLOYMENT", settings.azure_openai_deployment),
            ("AZURE_OPENAI_API_VERSION", settings.azure_openai_api_version),
        )
        if not value
    ]
    if missing:
        raise LLMConfigError(f"LLM_PROVIDER=azure requires {', '.join(missing)}")
    client = openai.AsyncAzureOpenAI(
        api_key=settings.azure_openai_api_key.get_secret_value(),
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        max_retries=0,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return OpenAIChatModel(client, settings.azure_openai_deployment)
