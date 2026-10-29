# Plan — ticket-workflow-service

**Source spec:** `.ai/specs/2026-10-29-ticket-workflow-service.md`
**Branch:** `feat/ticket-workflow-service`
**Base:** `main`
**Run mode:** Spec-implementation run
**Started:** 2026-10-29T15:09:14Z

## Tasks

> Authoritative status table. `Status` is one of `todo` or `done`. On landing a Step, flip `Status` to `done` and fill the `Commit` column with the short SHA. The first row whose `Status` is not `done` is the resume point for `om-auto-continue-pr-loop`. Step ids and `Exec` cells are immutable once the plan is committed — per-Step commits touch only `Status` and `Commit`.
>
> A commit cannot contain its own SHA, so each Step commit flips its own `Status` to `done` with `Commit` = `pending`, and the next commit on the branch backfills the real short SHA.

| Phase | Step | Title | Exec | Status | Commit |
|-------|------|-------|------|--------|--------|
| 1 | 1.1 | Project skeleton | inline | done | 3051f7a |
| 1 | 1.2 | Domain models and data files | inline | done | 956ad32 |
| 1 | 1.3 | Business rules | inline | done | 2535557 |
| 1 | 1.4 | Settings and JSON logging | inline | done | 914f457 |
| 2 | 2.1 | Tools | inline | done | b3b2a09 |
| 2 | 2.2 | Agent loop | inline | done | cc2812c |
| 2 | 2.3 | Fake model | inline | done | 5898b76 |
| 2 | 2.4 | Real adapter | inline | done | 82deb65 |
| 3 | 3.1 | Fake Helpdesk | inline | done | f6957ae |
| 3 | 3.2 | Activities | inline | done | 6546eba |
| 3 | 3.3 | Workflow | inline | done | 2523651 |
| 3 | 3.4 | Worker and sample scenarios | inline | done | 08c3039 |
| 4 | 4.1 | API | inline | done | ea80d6c |
| 4 | 4.2 | Containers | inline | done | 1fa05f8 |
| 4 | 4.3 | Demo script | inline | done | 0dadd1e |
| 4 | 4.4 | JSON logs from uvicorn startup | inline | done | 92fa153 |
| 5 | 5.1 | README | dispatch | done | 09f8a46 |
| 3 | 3.4-review-fix | Adversarial scripted model through loop and workflow | inline | done | 35668e6 |
| 5 | 5.2 | CI | dispatch:cheap | done | efc7135 |
| 4 | 4.5 | Ticket IDs on access-log lines | inline | done | 07ef3cb |
| 5 | 5.3 | End-to-end verification | inline | done | 3e06eb5 |
| 1 | 1.3-review-fix | Refund amounts limited to whole cents | inline | done | 307c1ca |
| 2 | 2.2-review-fix | Case-insensitive envelope escaping | inline | done | d9e8d6e |
| 4 | 4.1-review-fix | Approval race and query failures map to 409/503 | inline | done | aaa22f0 |
| 4 | 4.4-review-fix | Ticket IDs on the query-failure log line | inline | done | 20febe6 |
| 3 | 3.3-qa-fix | Reconcile a lost response after the last execute_action attempt | inline | done | f3450b7 |
| 1 | 1.3-qa-fix | Refunds only from paid invoices | inline | done | 2274371 |
| 3 | 3.3-qa-fix-2 | 24 h approval test asserts elapsed workflow time | inline | done | 0dba9b1 |
| 4 | 4.6 | Explicit 503 mapping: Temporal connect failure and no worker for a query | inline | done | 6104277 |
| 4 | 4.7 | API logs one http_request line per ticket request; uvicorn access log off | inline | done | e0a445d |
| 4 | 4.8 | Compose passes settings from the shell and .env via ${NAME:-default} | inline | done | e3969b7 |
| 4 | 4.9 | Tests container always rebuilds (pull_policy: build) | inline | done | 849fb85 |
| 3 | 3.5 | Worker config error as one JSON error line, exit code 2 | inline | done | 2035f6a |
| 4 | 4.6-fix | Query timeout tells no worker from Temporal down via a health check | inline | done | eeae1b6 |
| 3 | 3.6 | LLM request sends only documented parameters per provider; Azure v1 API by default | inline | done | b337881 |
| 3 | 3.7 | Provider 400/401/403/404/409/422 not retried; 408/429/5xx/timeout/network retried | inline | done | c983b21 |
| 3 | 3.8 | DecideOutput and ActionRequest in app.domain.models; API process does not load openai | inline | done | 30166f0 |
| 3 | 3.9 | Invalid worker settings as one JSON error line, exit code 2 | inline | done | 63852c7 |
| 5 | 5.4 | README: real model not run live, documented parameters with links, how to enable | inline | done | 16ea666 |
| 5 | 5.5 | README: host test commands that work (uv pip; venv + pip) | inline | done | ffb3bf2 |
| 5 | 5.6 | README: statements aligned with code (received, AGENT_MAX_*, KB check, worker restart, pull_policy) | inline | done | b7e576a |
| 5 | 5.7 | README: example run refreshed, hard test count removed | inline | done | 770cc96 |
| 5 | 5.8 | README: limitations completed | inline | done | fd6b8bc |
| 5 | 5.9 | README: how AI coding assistants were used | inline | done | ef8237f |
| 5 | 5.10 | README: AI assistants section facts corrected (error handling, money validation, log IDs) | inline | done | f0b96ad |
| 5 | 5.11 | README: what the rules check, lookup_action_result in the architecture, timer/approval race | inline | done | 5bacdbf |
| 5 | 5.12 | Spec: default model gpt-6-luna, change noted | inline | done | fb90bbb |
| 1 | 1.5 | AGENT_MAX_TURNS capped at 8 (8 x 20 s fits the 180 s decide timeout) | inline | done | 99b054b |
| 1 | 1.6 | Refund amounts as strings: plain decimal notation only ("4_9" escalates) | inline | done | 012627d |
| 4 | 4.10 | Compose: worker restart: on-failure:3 instead of an endless restart loop | inline | done | 4953f06 |
| 1 | 1.7 | Reference data and sample tickets replaced 1:1 with the source records; golden test | inline | done | da8cede |
| 2 | 2.5 | Fake model keyword rules fitted to the source tickets and KB | inline | done | 635dfed |
| 5 | 5.13 | Spec expectations table, README examples and run notes on the source data | inline | done | fb3819e |
| 5 | 5.14 | README example run refreshed from a Compose run on the source data | inline | done | 4d7e000 |
| 5 | 5.15 | README AI section: invented reference data case | inline | done | b921ad2 |

## Goal

Build the support-ticket service described in the source spec: a FastAPI API that starts one Temporal workflow per ticket, a worker that runs an LLM agent with three read-only tools, validates the agent's decision with pure-Python rules inside the workflow, holds refunds for a human approval (24 h timeout), and executes the final action against an in-memory, deliberately unreliable Helpdesk with an idempotency store. Everything runs locally with `docker compose up` in fake-LLM mode, and the whole test suite runs offline.

## Scope

- Python package `app/` with the layout from the spec (domain, data, agent, adapters, activities, workflow, API, worker).
- Reference data and sample tickets as JSON files in the repository.
- Tests for every step (unit, Temporal time-skipping workflow tests, API tests, end-to-end scenarios for T-1 … T-7).
- Dockerfile (`app` and `tests` targets), `docker-compose.yml`, `.env.example`, demo script.
- README covering the sections the spec lists; AGENTS.md routing rows filled in.
- GitHub Actions workflow running the validation gate.
- A real Compose run of the demo on this machine, recorded in the README.

## Non-goals

Taken from the spec's *Out of scope* list and kept out: tracing (OpenTelemetry), infrastructure-as-code for Azure, a real-vs-fake model comparison, per-tool activities, persistent idempotency, API authentication, Temporal persistence in Compose, any database or queue, any agent framework. No real LLM calls are made during this run (no key is available and none is needed).

## Implementation Plan

Step titles match the spec's Implementation Plan; each Step is one commit and leaves `ruff check .`, `ruff format --check .` and `pytest` green.

### Phase 1 — Foundation

- **1.1 Project skeleton** — `pyproject.toml` (Python 3.12, pinned runtime and dev dependencies, ruff and pytest config with `asyncio_mode = "auto"`), the `app/` package with empty modules from the spec layout, `.gitignore` additions (`.temporal-test-server/`, `.env`, `.ai/cezar/`), `tests/test_smoke.py`.
- **1.2 Domain models and data files** — `app/domain/models.py`, `app/data/*.json`, `samples/tickets.json`, `app/data/store.py` with `DataStore`; tests for parsing, enum/allowed-values parity, customer scoping of invoices, KB ranking, unknown customer.
- **1.3 Business rules** — `app/domain/rules.py` (`validate_decision`), full unit-test matrix from the spec, import-guard test for `app.domain`.
- **1.4 Settings and JSON logging** — `app/config.py`, `app/logging.py`; tests for defaults and the JSON formatter (including lifting `workflow_id` from the `temporal_workflow` extra).

### Phase 2 — Agent

- **2.1 Tools** — tool schemas and `ToolExecutor` scoped to one customer; tests for scoping, no customer argument, error objects.
- **2.2 Agent loop** — `loop.py`, `prompts.py`, `ChatModel` protocol and reply types; scripted-model tests (tool-call round trip, re-prompt, `AgentOutputInvalid`, `AgentTurnLimit`, untrusted envelope).
- **2.3 Fake model** — deterministic keyword-rule model going through the same loop; tests against the expectations table for T-1 … T-6.
- **2.4 Real adapter** — `OpenAIChatModel` for OpenAI and Azure OpenAI, `build_chat_model` factory; tests with a fake client object (no network).

### Phase 3 — Durable processing

- **3.1 Fake Helpdesk** — failure injection, lost-response mode, idempotency store, seeded RNG; tests.
- **3.2 Activities** — `decide_ticket`, `execute_action`, error classification into `ApplicationError`; `ActivityEnvironment` tests.
- **3.3 Workflow** — `TicketWorkflow` with status query, approval signal, 24 h timer, retry policies; time-skipping tests for all nine listed scenarios.
- **3.4 Worker and sample scenarios** — worker entrypoint, `scripts/warm_test_server.py`, `tests/conftest.py` fixture with cached test-server dir; end-to-end T-1 … T-7 scenario test with real activities and injected Helpdesk failures; log-field test.

### Phase 4 — HTTP API and containers

- **4.1 API** — schemas, routes, lifespan Temporal client, 404/409/503 mapping; API tests against a time-skipping env.
- **4.2 Containers** — Dockerfile, Compose (temporal, api, worker, offline `tests` profile), `.env.example`, `.dockerignore`; `.env.example` parity test.
- **4.3 Demo script** — `scripts/demo.sh`; `bash -n` test.

- **4.4 JSON logs from uvicorn startup** — fix forward found by the checkpoint-4 Compose smoke run: the API configured JSON logging in the lifespan, after uvicorn had already printed its plain-text startup lines. Configure logging when the production app is created instead; test it.

- **3.4-review-fix Adversarial scripted model through loop and workflow** — found while verifying the README written in Step 5.1: the spec's prompt-injection defence 7 asks for an adversarial scripted model (refund on another customer's invoice, unknown action, over-limit amount) run through the real loop and workflow, and Step 3.4 had only covered those cases as rule unit tests plus T-6. Adds `tests/test_adversarial.py`.

- **4.5 Ticket IDs on access-log lines** — found by the first Step 5.3 run: uvicorn access lines such as `"GET /tickets/T-2 HTTP/1.1" 200` are about a ticket but carried no `ticket_id`/`workflow_id` (FR-19). The JSON formatter now takes the ticket ID from the request path of `uvicorn.access` records.

### Phase 5 — Documentation and CI

- **5.1 README** — all sections the spec requires; the section on AI coding assistants stays a skeleton with TODO markers; AGENTS.md routing rows updated; README heading test.
- **5.2 CI** — `.github/workflows/ci.yml` running the gate on every push and PR.
- **5.3 End-to-end verification** — real `docker compose up -d --build`, demo run, per-ticket check against the expectations table, JSON log inspection, offline `docker compose run --rm tests`; results recorded in the README "Example run" subsection.

### Review fixes (from `om-auto-review-pr 3 --autofix`)

- **1.3-review-fix Refund amounts limited to whole cents** — the rules accepted amounts such as `0.0000001` or `1E+1`; amounts with more than two decimal places now escalate, valid ones are normalised to cents, and amounts too large to express in cents escalate.
- **2.2-review-fix Case-insensitive envelope escaping** — `</UNTRUSTED_TICKET>` (or with spaces) reached the model unescaped although the README says the ticket cannot close the envelope.
- **4.1-review-fix Approval race and query failures map to 409/503** — a workflow that closes between the status query and the approval signal answered 404; it now answers 409 with the current step. Query failures (`WorkflowQueryFailedError`/`WorkflowQueryRejectedError`) answered 500; they now answer 503 with a detail.
- **4.4-review-fix Ticket IDs on the query-failure log line** — found by the re-review: the new `workflow_query_failed` line carried no ticket/workflow ID (FR-19); it is now logged where the workflow handle is known.

## Deviations from the spec

Recorded as they are decided; each is minimal.

1. **Default OpenAI model.** The spec names `gpt-4o-mini`. OpenAI's deprecations page (checked 2026-10-29) lists `gpt-4o-mini-2024-07-18` for removal on 2027-01-14 with `gpt-6-luna` as the replacement; the `gpt-6-luna` model page lists Chat Completions, function calling and structured outputs. Default `OPENAI_MODEL` is therefore `gpt-6-luna`. The same model page states that Chat Completions supports function calling for this model only with `reasoning_effort` set to `none`, so the OpenAI (non-Azure) request also sends `reasoning_effort="none"`. Azure keeps the spec's request shape because the deployment's model is unknown. Not verified against the live API (no key in this run).
2. **`.gitignore`** also ignores `.ai/cezar/` (local tooling state of the agent runner that must never be committed).
3. **`WorkflowStatus.failure_reason`.** The spec's pseudocode sets `result = failure reason` on a failed act step, but `result` is typed `ActionResult`. A separate optional `failure_reason: str` field carries the reason instead, so `result` keeps one type.
4. **`tests/conftest.py` lands in Step 3.3, not 3.4.** The workflow tests of Step 3.3 already need the shared time-skipping environment fixture (with the cached test-server directory). Step 3.4 adds the warm-up script and the end-to-end scenarios as planned.

## Versions (checked 2026-10-29)

PyPI: `temporalio 1.35.0`, `fastapi 0.162.0`, `uvicorn 0.54.0`, `pydantic 2.14.1`, `pydantic-settings 2.16.2`, `openai 3.41.0`, `pytest 9.2.0`, `pytest-asyncio 1.4.1`, `httpx 0.28.1`, `ruff 0.17.3` — identical to the spec. Docker Hub `temporalio/temporal`: newest version tag `1.9.1` — identical to the spec.

## Risks

- Temporal SDK details (time-skipping download parameter, Pydantic converter, query/signal behaviour in the test server) are verified against the pinned SDK while implementing; any adaptation is recorded under Deviations.
- The real-model path is only tested against a fake client object.

## External References

None (`--skill-url` not passed).
