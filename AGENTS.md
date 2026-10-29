# AGENTS.md

## Project overview

`agentic-ticket-workflow` is a small Python service for agentic ticket handling, built with FastAPI (HTTP API) and Temporal (durable workflows and activities). The code lives in `app/` (API, workflow, activities, agent loop, domain rules, adapters); `README.md` documents the architecture, configuration and Azure design. Update this file as the code takes shape.

## Task routing

| When the task involves… | Read first | Key rules |
|---|---|---|
| Process, labels, QA gate, claims | `SDLC.md`, `.ai/agentic.config.json` | Follow the label state machine and claim protocol in `SDLC.md`; PRs target `main`. |
| Code review | `CODE_REVIEW.md` | Applied automatically by `om-code-review`. |
| HTTP API (FastAPI routes, request/response models) | `app/api/main.py`, `app/api/schemas.py` | Handlers stay thin: start, query or signal the workflow and map Temporal errors to HTTP (404, 503). Request models reuse `app/domain/models.py`; workflow ID is `ticket-{ticket_id}`. |
| Temporal workflows and activities | `app/workflows/ticket.py`, `app/activities.py`, `app/worker.py` | Workflow code must stay deterministic; I/O, clocks, randomness, and external calls belong in activities (`decide_ticket`, `execute_action`). Timeouts and retry policies are constants, not env settings. Business rules (`app/domain/rules.py`) import no FastAPI, Temporal or OpenAI code. See `CODE_REVIEW.md`. |
| Tests | `tests/conftest.py`, `tests/scripted_model.py` | Every behavior change ships with tests; `pytest` is part of the validation gate. Workflow tests use the Temporal time-skipping server (downloaded once into `.temporal-test-server/`); no network or API key afterwards. |
| Dependencies and tooling | `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `.env.example` | Dependencies are pinned in `pyproject.toml`; lint and format with `ruff`. New environment variables go in `app/config.py` and `.env.example` (no real values). |
| CI | `.github/workflows/ci.yml` | `.github/workflows/ci.yml` runs the validation gate below. |
| Specs and plans | `.ai/specs/`, `.ai/runs/` | Specs use `{YYYY-MM-DD}-{kebab-case-title}.md`. |
| Tracker and browser operations | `.ai/trackers/github.md`, `.ai/browsers/none.md` | GitHub through `gh`. No UI, so no browser automation: verify through tests and HTTP requests. |

## Validation gate

Run in order; any non-zero exit fails the gate:

1. `ruff check .`
2. `ruff format --check .`
3. `pytest`

Install the dev dependencies first: `pip install -e ".[dev]"`.

## Repository rules

- Never commit secrets, tokens, `.env` files, or personal data. The repository is public.
- Configuration comes from environment variables; document new ones without real values.
- Pipeline configuration: `.ai/agentic.config.json`. Per-skill overrides: `.ai/skills/<skill-name>/SKILL.md`.
