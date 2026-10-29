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
| 2 | 2.2 | Agent loop | inline | done | pending |
| 2 | 2.3 | Fake model | inline | todo | — |
| 2 | 2.4 | Real adapter | inline | todo | — |
| 3 | 3.1 | Fake Helpdesk | inline | todo | — |
| 3 | 3.2 | Activities | inline | todo | — |
| 3 | 3.3 | Workflow | inline | todo | — |
| 3 | 3.4 | Worker and sample scenarios | inline | todo | — |
| 4 | 4.1 | API | inline | todo | — |
| 4 | 4.2 | Containers | inline | todo | — |
| 4 | 4.3 | Demo script | inline | todo | — |
| 5 | 5.1 | README | dispatch | todo | — |
| 5 | 5.2 | CI | dispatch:cheap | todo | — |
| 5 | 5.3 | End-to-end verification | inline | todo | — |

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

### Phase 5 — Documentation and CI

- **5.1 README** — all sections the spec requires; the section on AI coding assistants stays a skeleton with TODO markers; AGENTS.md routing rows updated; README heading test.
- **5.2 CI** — `.github/workflows/ci.yml` running the gate on every push and PR.
- **5.3 End-to-end verification** — real `docker compose up -d --build`, demo run, per-ticket check against the expectations table, JSON log inspection, offline `docker compose run --rm tests`; results recorded in the README "Example run" subsection.

## Deviations from the spec

Recorded as they are decided; each is minimal.

1. **Default OpenAI model.** The spec names `gpt-4o-mini`. OpenAI's deprecations page (checked 2026-10-29) lists `gpt-4o-mini-2024-07-18` for removal on 2027-01-14 with `gpt-6-luna` as the replacement; the `gpt-6-luna` model page lists Chat Completions, function calling and structured outputs. Default `OPENAI_MODEL` is therefore `gpt-6-luna`. The same model page states that Chat Completions supports function calling for this model only with `reasoning_effort` set to `none`, so the OpenAI (non-Azure) request also sends `reasoning_effort="none"`. Azure keeps the spec's request shape because the deployment's model is unknown. Not verified against the live API (no key in this run).
2. **`.gitignore`** also ignores `.ai/cezar/` (local tooling state of the agent runner that must never be committed).
3. **`WorkflowStatus.failure_reason`.** The spec's pseudocode sets `result = failure reason` on a failed act step, but `result` is typed `ActionResult`. A separate optional `failure_reason: str` field carries the reason instead, so `result` keeps one type.

## Versions (checked 2026-10-29)

PyPI: `temporalio 1.35.0`, `fastapi 0.162.0`, `uvicorn 0.54.0`, `pydantic 2.14.1`, `pydantic-settings 2.16.2`, `openai 3.41.0`, `pytest 9.2.0`, `pytest-asyncio 1.4.1`, `httpx 0.28.1`, `ruff 0.17.3` — identical to the spec. Docker Hub `temporalio/temporal`: newest version tag `1.9.1` — identical to the spec.

## Risks

- Temporal SDK details (time-skipping download parameter, Pydantic converter, query/signal behaviour in the test server) are verified against the pinned SDK while implementing; any adaptation is recorded under Deviations.
- The real-model path is only tested against a fake client object.

## External References

None (`--skill-url` not passed).
