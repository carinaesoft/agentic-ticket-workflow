from types import SimpleNamespace

import openai
import pytest

from app.adapters.fake_llm import FakeChatModel
from app.adapters.llm import (
    REQUEST_TIMEOUT_SECONDS,
    LLMConfigError,
    OpenAIChatModel,
    build_chat_model,
)
from app.agent.tools import TOOL_SCHEMAS
from app.config import Settings


class FakeCompletions:
    def __init__(self, message) -> None:
        self.message = message
        self.requests: list[dict] = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.message)])


def fake_client(message) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(message)))


def tool_call(call_id: str, name: str, arguments: str):
    return SimpleNamespace(
        id=call_id, type="function", function=SimpleNamespace(name=name, arguments=arguments)
    )


MESSAGES = [{"role": "system", "content": "json please"}, {"role": "user", "content": "hi"}]


async def test_tool_calls_are_mapped_into_model_reply() -> None:
    message = SimpleNamespace(
        content=None,
        tool_calls=[
            tool_call("call_a", "get_customer", "{}"),
            tool_call("call_b", "search_kb", '{"query": "refund"}'),
        ],
    )
    reply = await OpenAIChatModel(fake_client(message), "m").complete(MESSAGES, TOOL_SCHEMAS)
    assert reply.content is None
    assert [(c.id, c.name, c.arguments_json) for c in reply.tool_calls] == [
        ("call_a", "get_customer", "{}"),
        ("call_b", "search_kb", '{"query": "refund"}'),
    ]


async def test_text_answer_is_mapped_into_content() -> None:
    message = SimpleNamespace(content='{"category": "other"}', tool_calls=[])
    reply = await OpenAIChatModel(fake_client(message), "m").complete(MESSAGES, TOOL_SCHEMAS)
    assert reply.content == '{"category": "other"}'
    assert reply.tool_calls == []


@pytest.fixture(autouse=True)
def no_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for name in list(os.environ):
        if name.startswith(("OPENAI_", "AZURE_OPENAI_", "LLM_")):
            monkeypatch.delenv(name)


def settings(**values) -> Settings:
    return Settings.model_validate(values)


OPENAI_SETTINGS = {"llm_provider": "openai", "openai_api_key": "test-key"}
AZURE_SETTINGS = {
    "llm_provider": "azure",
    "azure_openai_api_key": "test-key",
    "azure_openai_endpoint": "https://example.openai.azure.com/",
    "azure_openai_deployment": "tickets-deployment",
}


async def sent_request(**values) -> dict:
    """The exact keyword arguments the built model passes to ``chat.completions.create``."""
    model = build_chat_model(settings(**values))
    client = fake_client(SimpleNamespace(content='{"a": 1}', tool_calls=None))
    model._client = client
    await model.complete(MESSAGES, TOOL_SCHEMAS)
    (request,) = client.chat.completions.requests
    return request


async def test_openai_request_parameters() -> None:
    assert await sent_request(**OPENAI_SETTINGS) == {
        "model": "gpt-6-luna",
        "messages": MESSAGES,
        "tools": TOOL_SCHEMAS,
        "reasoning_effort": "none",
    }


async def test_azure_request_parameters() -> None:
    assert await sent_request(**AZURE_SETTINGS) == {
        "model": "tickets-deployment",
        "messages": MESSAGES,
        "tools": TOOL_SCHEMAS,
        "reasoning_effort": "none",
    }


def test_fake_provider_builds_fake_model() -> None:
    assert isinstance(build_chat_model(settings(llm_provider="fake")), FakeChatModel)


def test_openai_without_key_is_a_config_error() -> None:
    with pytest.raises(LLMConfigError, match="OPENAI_API_KEY"):
        build_chat_model(settings(llm_provider="openai"))


def test_azure_names_every_missing_setting() -> None:
    with pytest.raises(LLMConfigError) as excinfo:
        build_chat_model(settings(llm_provider="azure", azure_openai_api_key="k"))
    message = str(excinfo.value)
    for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"):
        assert name in message
    for name in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_API_VERSION"):
        assert name not in message


def test_openai_client_has_no_sdk_retries_and_a_timeout() -> None:
    model = build_chat_model(settings(llm_provider="openai", openai_api_key="test-key"))
    assert isinstance(model, OpenAIChatModel)
    assert isinstance(model._client, openai.AsyncOpenAI)
    assert model._client.max_retries == 0
    assert model._client.timeout == REQUEST_TIMEOUT_SECONDS
    assert model._model == "gpt-6-luna"


def test_azure_uses_the_v1_api_by_default() -> None:
    model = build_chat_model(settings(**AZURE_SETTINGS))
    assert type(model._client) is openai.AsyncOpenAI
    assert str(model._client.base_url) == "https://example.openai.azure.com/openai/v1/"
    assert model._client.max_retries == 0
    assert model._client.timeout == REQUEST_TIMEOUT_SECONDS
    assert model._model == "tickets-deployment"


def test_azure_with_a_dated_api_version_uses_the_azure_client() -> None:
    model = build_chat_model(
        settings(**AZURE_SETTINGS, azure_openai_api_version="2024-12-01-preview")
    )
    assert isinstance(model._client, openai.AsyncAzureOpenAI)
    assert model._client._api_version == "2024-12-01-preview"
    assert model._client.max_retries == 0
    assert model._client.timeout == REQUEST_TIMEOUT_SECONDS
    assert model._model == "tickets-deployment"
