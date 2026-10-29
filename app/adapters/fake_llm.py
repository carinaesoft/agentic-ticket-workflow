"""Deterministic fake chat model.

A keyword-rule stand-in for a real model that goes through the same agent loop: it first
calls tools (one per turn), reads their results back from the message history, and only
then answers with a decision JSON. It needs no key and no network.

Its keyword rules are written for the sample tickets in ``samples/tickets.json`` and the KB
in ``app/data/kb.json``; anything else falls through to "close".

It is deliberately naive: a refund amount and invoice stated in the ticket are taken at face
value, and a refund without a stated invoice goes to the customer's first paid invoice.
Stopping a manipulative ticket is the job of the rules, not of the model.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from app.adapters.llm import Message, ModelReply, ToolCall
from app.agent.prompts import ENVELOPE_TAG

_PASSWORD = ("password", "log in", "login", "sign in", "get into my account")
_REFUND = ("refund", "charged twice", "double charge")
_DUPLICATE = ("charged twice", "double charge")
_OUTAGE = ("outage", " down", "returned errors", "503")
_INVOICE_ID = re.compile(r"\bINV-\d+\b")
_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:EUR|€)", re.IGNORECASE)


class FakeChatModel:
    async def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelReply:
        text = _ticket_text(messages)
        lowered = text.lower()
        results = _tool_results(messages)

        if "get_customer" not in results:
            return _call("get_customer", {}, results)
        customer = results["get_customer"]

        refund = _has(lowered, _REFUND)
        stated_invoice = _INVOICE_ID.search(text)
        stated_amount = _AMOUNT.search(text)
        explicit_refund = refund and stated_invoice and stated_amount
        suspended = customer.get("status") == "suspended"

        if (refund or suspended) and "get_invoices" not in results:
            return _call("get_invoices", {}, results)

        query = _kb_query(lowered, refund, suspended)
        if query and not explicit_refund and "search_kb" not in results:
            return _call("search_kb", {"query": query}, results)

        decision = _decide(
            lowered,
            customer,
            results.get("get_invoices", []),
            results.get("search_kb", []),
            refund=refund,
            stated_invoice=stated_invoice.group(0) if stated_invoice else None,
            stated_amount=stated_amount.group(1) if stated_amount else None,
        )
        return ModelReply(content=json.dumps(decision))


def _decide(
    text: str,
    customer: dict[str, Any],
    invoices: list[dict[str, Any]],
    articles: list[dict[str, Any]],
    *,
    refund: bool,
    stated_invoice: str | None,
    stated_amount: str | None,
) -> dict[str, Any]:
    article_ids = [a["article_id"] for a in articles[:1]]
    if refund:
        paid = [i for i in invoices if i["status"] == "paid"]
        invoice_id = stated_invoice or _duplicate_charge(paid, text)
        invoice_id = invoice_id or (paid[0]["invoice_id"] if paid else None)
        amount = stated_amount or next(
            (i["amount_eur"] for i in invoices if i["invoice_id"] == invoice_id), None
        )
        action = {
            "kind": "refund",
            "invoice_id": invoice_id,
            "amount_eur": f"{Decimal(amount):.2f}" if amount else None,
        }
        return {"category": "billing", "priority": "high", "action": action}
    if _has(text, _OUTAGE):
        if customer.get("plan") == "enterprise":
            reason = "outage reported by enterprise customer"
            return _decision("technical", "urgent", {"kind": "escalate", "reason": reason})
        message = "We are looking into the problem; current outages are on the status page."
        return _decision("technical", "high", _reply(message, article_ids))
    if customer.get("status") == "suspended":
        overdue = [i["invoice_id"] for i in invoices if i["status"] == "overdue"]
        message = (
            f"Your account is suspended because invoice {', '.join(overdue)} is overdue. "
            "Pay the invoice to unlock the account."
        )
        return _decision("account", "high", _reply(message, article_ids))
    if _has(text, _PASSWORD):
        message = (
            "Open the sign-in page, choose 'Forgot password' and follow the link we email "
            "you. The link works for 30 minutes."
        )
        return _decision("account", "normal", _reply(message, article_ids))
    return _decision("other", "low", {"kind": "close", "reason": "not a support request"})


def _duplicate_charge(paid: list[dict[str, Any]], text: str) -> str | None:
    """The extra charge: the later of two paid invoices for the same month and amount."""
    if not _has(text, _DUPLICATE):
        return None
    seen: set[tuple[str, str]] = set()
    for invoice in sorted(paid, key=lambda i: (i["month"], i["invoice_id"])):
        key = (invoice["month"], invoice["amount_eur"])
        if key in seen:
            return invoice["invoice_id"]
        seen.add(key)
    return None


def _decision(category: str, priority: str, action: dict[str, Any]) -> dict[str, Any]:
    return {"category": category, "priority": priority, "action": action}


def _reply(message: str, article_ids: list[str]) -> dict[str, Any]:
    return {"kind": "reply", "message": message, "article_ids": article_ids}


def _kb_query(text: str, refund: bool, suspended: bool) -> str | None:
    if refund:
        return "refund"
    if _has(text, _OUTAGE):
        return "outages"
    if suspended:
        return "suspended"
    if _has(text, _PASSWORD):
        return "password"
    return None


def _has(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def _ticket_text(messages: list[Message]) -> str:
    user = next(m["content"] for m in messages if m["role"] == "user")
    return user.split(f"<{ENVELOPE_TAG}>", 1)[-1].split(f"</{ENVELOPE_TAG}>", 1)[0]


def _tool_results(messages: list[Message]) -> dict[str, Any]:
    """Tool name -> parsed result, read back from the conversation."""
    names: dict[str, str] = {}
    results: dict[str, Any] = {}
    for message in messages:
        for call in message.get("tool_calls") or []:
            names[call["id"]] = call["function"]["name"]
        if message["role"] == "tool":
            results[names[message["tool_call_id"]]] = json.loads(message["content"])
    return results


def _call(name: str, arguments: dict[str, Any], results: dict[str, Any]) -> ModelReply:
    call_id = f"call_{len(results) + 1}_{name}"
    return ModelReply(
        tool_calls=[ToolCall(id=call_id, name=name, arguments_json=json.dumps(arguments))]
    )
