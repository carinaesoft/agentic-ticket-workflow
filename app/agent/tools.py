"""Tool schemas and the tool executor.

The executor is bound to the ticket's customer when it is created. No tool takes a
customer argument, so the model cannot read or act on another customer's data. Bad calls
(unknown tool, invalid arguments) come back to the model as an error object instead of
raising.
"""

from __future__ import annotations

import json
from typing import Any

from app.data.store import DataStore

MAX_QUERY_CHARS = 200

_NO_ARGS = {"type": "object", "properties": {}, "additionalProperties": False}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_customer",
            "description": "Plan and account status of the customer who wrote the ticket.",
            "parameters": _NO_ARGS,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_invoices",
            "description": "Invoices of the customer who wrote the ticket.",
            "parameters": _NO_ARGS,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "Search the knowledge base. Returns up to 3 matching articles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords to search for."}
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]

TOOL_NAMES = frozenset(schema["function"]["name"] for schema in TOOL_SCHEMAS)


class ToolExecutor:
    def __init__(self, customer_id: str, store: DataStore) -> None:
        self._customer_id = customer_id
        self._store = store

    def run(self, name: str, arguments_json: str) -> Any:
        """Execute one tool call and return a JSON-serialisable result or error object."""
        if name not in TOOL_NAMES:
            return {"error": f"unknown tool {name!r}; available: {sorted(TOOL_NAMES)}"}
        try:
            arguments = json.loads(arguments_json) if arguments_json.strip() else {}
        except json.JSONDecodeError as exc:
            return {"error": f"arguments are not valid JSON: {exc.msg}"}
        if not isinstance(arguments, dict):
            return {"error": "arguments must be a JSON object"}

        if name == "search_kb":
            query = arguments.get("query")
            if set(arguments) != {"query"} or not isinstance(query, str) or not query.strip():
                return {"error": "search_kb takes exactly one argument: a non-empty 'query'"}
            return self._search_kb(query[:MAX_QUERY_CHARS])
        if arguments:
            return {"error": f"{name} takes no arguments"}
        if name == "get_customer":
            return self._get_customer()
        return self._get_invoices()

    def _get_customer(self) -> dict[str, Any]:
        customer = self._store.get_customer(self._customer_id)
        if customer is None:
            return {"error": "customer not found"}
        return {
            "customer_id": customer.customer_id,
            "plan": customer.plan,
            "status": customer.status,
        }

    def _get_invoices(self) -> list[dict[str, Any]]:
        return [
            {
                "invoice_id": i.invoice_id,
                "month": i.month,
                "amount_eur": str(i.amount_eur),
                "status": i.status,
            }
            for i in self._store.invoices_for(self._customer_id)
        ]

    def _search_kb(self, query: str) -> list[dict[str, Any]]:
        return [a.model_dump() for a in self._store.search_kb(query)]
