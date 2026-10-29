# Notify — 2026-10-29-ticket-workflow-service

> Append-only log. Every entry is UTC-timestamped. Never rewrite prior entries.

## 2026-10-29T15:09:14Z — run started
- Brief: implement `.ai/specs/2026-10-29-ticket-workflow-service.md`, Steps 1.1–5.3, one commit per Step.
- External skill URLs: none
- Decision: default `OPENAI_MODEL` is `gpt-6-luna` instead of the deprecated `gpt-4o-mini` (PLAN.md Deviations 1).
- Decision: the linked worktree keeps its local branch name; commits are pushed to `origin/feat/ticket-workflow-service`.

## 2026-10-29T15:14:29Z — checkpoint 1
- Steps 1.1–1.4 (3051f7a..914f457) verified: ruff check, ruff format --check, pytest (76 passed).
- Decision: `WorkflowStatus.failure_reason` added (PLAN.md Deviations 3).
- UI pass skipped: the service has no UI.

## 2026-10-29T15:18:09Z — checkpoint 2
- Steps 2.1–2.4 (b3b2a09..82deb65) verified: ruff check, ruff format --check, pytest (113 passed).
- Decision: OpenAI requests send `reasoning_effort="none"` (needed for function calling with the default model); Azure requests keep the spec shape.

## 2026-10-29T15:26:08Z — checkpoint 3
- Steps 3.1–3.4 (f6957ae..08c3039) verified: ruff check, ruff format --check, pytest (142 passed).
- Decision: `tests/conftest.py` landed in 3.3 (PLAN.md Deviations 4).
- Decision: the JSON formatter derives `ticket_id` from a `ticket-…` workflow ID, so SDK-emitted lines (activity retry warnings) also carry both IDs.

## 2026-10-29T15:42:42Z — checkpoint 4
- Steps 4.1–4.4 (ea80d6c..92fa153) verified: ruff, pytest (162 passed), compose config, offline tests container, Compose smoke run of the demo.
- Problem: plain-text uvicorn startup lines in the API log (found by the smoke run) → fixed forward as Step 4.4.
- Decision: host ports stay fixed at 7233/8233/8000 — they are free on this host, so the compose file was not made port-configurable.

## 2026-10-29T15:43:02Z — delegation
- Step 5.1 (README) dispatched to one executor subagent (tier: standard → sonnet), per the plan's Exec column. Main session verifies the commit before continuing.
