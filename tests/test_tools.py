import json

import pytest

from app.agent.tools import TOOL_NAMES, TOOL_SCHEMAS, ToolExecutor
from app.data.store import DataStore

STORE = DataStore()


@pytest.fixture
def executor() -> ToolExecutor:
    return ToolExecutor("C-101", STORE)


def test_three_tools_in_chat_completions_shape() -> None:
    assert {"get_customer", "get_invoices", "search_kb"} == TOOL_NAMES
    for schema in TOOL_SCHEMAS:
        assert schema["type"] == "function"
        assert schema["function"]["parameters"]["type"] == "object"
        json.dumps(schema)


def test_no_tool_takes_a_customer_argument() -> None:
    for schema in TOOL_SCHEMAS:
        params = schema["function"]["parameters"]
        assert params["additionalProperties"] is False
        assert not any("customer" in p for p in params["properties"])


def test_get_customer_returns_scoped_customer(executor: ToolExecutor) -> None:
    assert executor.run("get_customer", "{}") == {
        "customer_id": "C-101",
        "plan": "pro",
        "status": "active",
    }


def test_get_invoices_returns_only_scoped_invoices(executor: ToolExecutor) -> None:
    invoices = executor.run("get_invoices", "")
    assert [i["invoice_id"] for i in invoices] == ["INV-1001", "INV-1002"]
    assert invoices[0]["amount_eur"] == "49.00"


def test_customer_cannot_be_overridden_by_arguments(executor: ToolExecutor) -> None:
    result = executor.run("get_invoices", '{"customer_id": "C-103"}')
    assert result == {"error": "get_invoices takes no arguments"}


def test_search_kb_returns_up_to_three_articles(executor: ToolExecutor) -> None:
    results = executor.run("search_kb", '{"query": "forgot password"}')
    assert results[0]["article_id"] == "KB-1"
    assert set(results[0]) == {"article_id", "title", "text"}
    assert len(executor.run("search_kb", '{"query": "the a and plan invoice account"}')) <= 3


def test_unknown_tool_returns_error_object(executor: ToolExecutor) -> None:
    assert "unknown tool 'issue_refund'" in executor.run("issue_refund", "{}")["error"]


@pytest.mark.parametrize(
    ("name", "arguments", "fragment"),
    [
        ("search_kb", "{not json", "not valid JSON"),
        ("search_kb", "[1, 2]", "must be a JSON object"),
        ("search_kb", "{}", "non-empty 'query'"),
        ("search_kb", '{"query": 5}', "non-empty 'query'"),
        ("search_kb", '{"query": "x", "customer_id": "C-103"}', "exactly one argument"),
    ],
)
def test_invalid_arguments_return_error_object(executor, name, arguments, fragment) -> None:
    assert fragment in executor.run(name, arguments)["error"]


def test_unknown_customer_gets_error_and_no_invoices() -> None:
    executor = ToolExecutor("C-999", STORE)
    assert executor.run("get_customer", "{}") == {"error": "customer not found"}
    assert executor.run("get_invoices", "{}") == []
