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

## 2026-10-29T15:51:00Z — final gate
- Steps 5.1–5.3 plus fix-forward Steps 3.4-review-fix and 4.5 landed (09f8a46..3e06eb5). Final gate: ruff check, ruff format --check, pytest (173 passed) — all green; CI green on GitHub.
- Delegation: Step 5.2 (CI) dispatched to an executor subagent (tier cheap → haiku); verified commit efc7135 and its CI run.
- Problem: the README written in 5.1 described an adversarial-model test that did not exist yet (spec defence 7) → added as Step 3.4-review-fix.
- Problem: the first Step 5.3 run showed uvicorn access lines about T-2 without ticket/workflow IDs → fixed as Step 4.5, then the whole 5.3 run was repeated on rebuilt images.
- Integration suite via om-integration-tests skipped: no UI, no browser provider, no separate runner (coverage listed in final-gate-checks.md). Design-system pass skipped: no such tooling.

## 2026-10-29T15:58:48Z — checkpoint 5 (review fixes)
- Delegation: code review by a fresh reviewer subagent (tier capable → opus), read-only, following om-code-review; re-review by the same subagent.
- Review: approve, 4 minors (sub-cent refund amounts, case-sensitive envelope escaping, 404 instead of 409 on approval race, query failures as 500) → fixed in 1.3/2.2/4.1-review-fix. Re-review: approve, 1 new minor (log line without IDs) → fixed in 4.4-review-fix. Gate: 188 passed.
- Deferred nits and the overdue-invoice product question recorded in checkpoint-5-checks.md.

## 2026-10-29T16:00:29Z — run finished
- PR: https://github.com/carinaesoft/agentic-ticket-workflow/pull/3 — ready for review, Status: complete, labels merge-queue/feature/needs-qa/priority-medium/risk-high. CI green on 6227bbc. Not merged (left to a human after QA).

## 2026-10-29T18:10:00Z — README accuracy run
- Steps 5.5–5.9 done; every README command block verified in a fresh clone; gate green (pytest 230). The README AI section skeleton test now requires the written section.

## 2026-10-29T18:01:13Z — reference data run
- Step 1.2 had made up the reference data and sample tickets (other customers, invoices, KB articles and ticket texts). Replaced 1:1 with the source records (1.7), fake model rules fitted to them (2.5), tests, spec table and README examples updated (5.13).
- Note: the earlier checkpoint and final-gate artifacts in this run folder (checks files, logs, test counts, example outputs) were recorded against the replaced data. They are kept as history; they do not describe the current data.
