# Handoff — 2026-10-29-ticket-workflow-service

**Last updated:** 2026-10-29T18:17:33Z
**Branch:** feat/ticket-workflow-service
**PR:** https://github.com/carinaesoft/agentic-ticket-workflow/pull/3 (ready for review)
**Current phase/step:** run complete — every Tasks row done
**Last commit:** 4191b50 — docs(readme): say the T-6 example needs a moment to reach completed

## Fix run — test isolation
- 5.16: tests/conftest.py autouse fixture sets `workflow_info_on_message` / `activity_info_on_message` to False per test and restores them; test_scenarios no longer depends on an earlier configure_logging() call. App code unchanged.
- 5.17: README T-6 example says a GET right after the POST usually shows `deciding`.
- Gate green (ruff, ruff format, pytest 246). Each tests/test_*.py run alone: green. Full suite with files in reverse order: 246 passed.

## Fix run — reference data
- 1.7, 2.5, 5.13–5.15. Step 1.2 had made up the reference data and sample tickets; they are now the source records 1:1, pinned by a golden test (tests/test_data.py). Amounts are JSON numbers, read as Decimal and kept in cents.
- Fake model rules fitted to the source tickets and KB: T-2 refunds the duplicate INV-1002, T-6 (no invoice named) proposes 5000.00 on INV-1001 and the rules escalate.
- Gate green after every commit (ruff, ruff format, pytest 246). Compose: demo T-1…T-7 + duplicate T-1 + T-2 approval matched the expectations; `docker compose run --rm tests` 246 passed; stack removed with `docker compose down -v`. README example run refreshed.
- Earlier artifacts in this run folder were recorded against the replaced data (see NOTIFY.md).

## Fix run — polish
- 5.10–5.12, 1.5, 1.6, 4.10. Gate green after every commit (ruff, ruff format, pytest 239).
- Compose: `docker compose up -d --build` + `scripts/demo.sh` gave the same T-1…T-7 results as the README; `docker compose run --rm tests` 239 passed. Worker started with `AGENT_MAX_TURNS=9`: 4 `worker_config_error` lines (start + 3 restarts), then exited with code 2. Stack removed with `docker compose down -v`.
- 1.6 keeps surrounding whitespace tolerated (an existing test expects `" 12 "` → `12.00`); `"4_9"`, `"+49"`, `"49."` and non-ASCII digits now escalate.

## Fix run — README accuracy
- Docs only (plus tests/test_readme.py: the AI section is now required to be written). Gate green (ruff, ruff format, pytest 230).
- 5.5–5.9: working host test commands (uv pip; venv + pip), statements checked against code, example run refreshed, limitations completed, AI assistants section added.
- Every README command block run as written in a fresh clone: Quick start, the three endpoints, both host test variants, `docker compose run --rm tests`; stack removed with `docker compose down -v`.

## Fix run — LLM adapter and layers
- Gate green after every commit (ruff, ruff format, pytest 230). No live model call: there is no API key; the adapter is tested with a fake client only.
- 3.6: requests carry model, messages, tools, reasoning_effort="none" (OpenAI and Azure); temperature, tool_choice and response_format dropped per the official docs (links in README). Azure uses the v1 API unless a dated AZURE_OPENAI_API_VERSION (>= 2024-12-01-preview) is set.
- 3.7: provider 400/401/403/404/409/422 → non-retryable `LLMRequestRejected` naming the status; 408/429/5xx/timeouts/connection errors retried.
- 3.8: DecideOutput/ActionRequest moved to app.domain.models; fresh-interpreter test: importing app.api.main loads no openai, app.activities, app.adapters or app.agent.
- 3.9: Settings validation error → one `worker_config_error` JSON line (no values echoed), exit 2.
- 5.4: README states the real model was not run live, how to enable it, and the official sources.

## Fix run — API, logs, Compose
- Gate green after every push (ruff, ruff format, pytest 212). Compose verified live with `HELPDESK_FAILURE_RATE=0.7` from the shell (worker logged 0.7); `docker compose logs api`: no uvicorn.access lines, every `http_request` line has ticket_id and workflow_id; stack removed with `docker compose down -v`.
- 4.6-fix: Live run showed a query right after the worker stops ends as CANCELLED ('Timeout expired', SDK timer), not DEADLINE_EXCEEDED. DEADLINE_EXCEEDED/CANCELLED now run a 2 s Temporal health check: healthy → 503 `no worker available to answer`, unreachable → 503 `workflow service unavailable`. Verified on Compose: worker stopped → no worker (both GETs); Temporal stopped → service unavailable (GET, POST, fresh API connect).
- 3.5: LLMConfigError at worker startup logs one `worker_config_error` JSON line (level ERROR, error + hint) and exits 2 instead of a traceback; Compose restart policy unchanged. Subprocess test checks exit code, empty stderr, single line.
- 4.9: tests service has pull_policy: build; verified: a failing probe test added to tests/ showed up in `docker compose run --rm tests` without --build, and disappeared after reverting; full container run 207 passed.
- 4.8: docker-compose.yml interpolates every setting (defaults = Settings defaults, keys empty); verified with docker compose config: no .env → fake/0.2, .env → its values, shell HELPDESK_FAILURE_RATE=0.7 wins over .env. tests/test_compose.py guards names and defaults; the tests image copies docker-compose.yml.
- 4.7: uvicorn runs with --no-access-log (and configure_logging disables uvicorn.access); a pure ASGI middleware logs `http_request` (method, path, status, duration_ms) for ticket routes and binds the ticket (path, or the POST body) so every API line of the request has ticket_id and workflow_id. Access-line parsing removed from app/logging.py.
- 4.6: API connects to Temporal on first use (any connect failure → 503 `workflow service unavailable`, retried next request); a status query failing with FAILED_PRECONDITION or DEADLINE_EXCEEDED → 503 `no worker available to answer`. No error-text matching.

## What just happened
- Correctness fixes after QA (3.3-qa-fix, 1.3-qa-fix, 3.3-qa-fix-2): an action applied in the last `execute_action` attempt is reconciled via `lookup_action_result` instead of failing; refunds only from `paid` invoices; the 24 h approval test proves the timer (still waiting at 23 h 59 min, ≥ 24 h workflow time to escalation). Gate green, pytest 195.
- All spec Steps 1.1–5.3 landed, plus fix-forward Steps 4.4, 4.5, 3.4-review-fix and review fixes 1.3/2.2/4.1/4.4-review-fix.
- Final gate green (ruff, ruff format, pytest 188), CI green, real Compose run of T-1…T-7 recorded in the README, offline tests container green.
- om-auto-review-pr --autofix: approve (comment review — the author account cannot approve its own PR).

## Next concrete action
- Manual QA per the "Manual QA instructions" PR comment (needs-qa; qaGate on), then human merge. Not merged by this run.

## Blockers / open questions
- README section "How AI coding assistants were used" is a TODO skeleton by design.
- Deferred nits: AGENT_MAX_TURNS upper bound, run ID in the idempotency key, OpenAI 409/422 retried, unlocked transitive deps.

## Environment caveats
- Dev runtime runnable: yes; Compose stack on ports 7233/8233/8000 (stopped with docker compose down after verification)
- Browser / UI checks: skipped — no UI
- Database/migration state: clean (no database)

## Worktree
- Path: agent-runner linked worktree (local branch pushed to `feat/ticket-workflow-service`)
- Created this run: no
