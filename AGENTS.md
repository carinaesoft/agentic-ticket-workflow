# AGENTS.md

## Project overview

`agentic-ticket-workflow` is a small Python service for agentic ticket handling, built with FastAPI (HTTP API) and Temporal (durable workflows and activities). The repository currently contains only the agent pipeline configuration; application code has not been written yet. Update this file as the code takes shape.

## Task routing

| When the task involves… | Read first | Key rules |
|---|---|---|
| Process, labels, QA gate, claims | `SDLC.md`, `.ai/agentic.config.json` | Follow the label state machine and claim protocol in `SDLC.md`; PRs target `main`. |
| Code review | `CODE_REVIEW.md` | Applied automatically by `om-code-review`. |
| HTTP API (FastAPI routes, request/response models) | TODO — no API code yet | TODO — record the router layout and validation conventions once the first endpoint lands. |
| Temporal workflows and activities | TODO — no workflow code yet | Workflow code must stay deterministic; I/O, clocks, randomness, and external calls belong in activities. See `CODE_REVIEW.md`. |
| Tests | TODO — no tests yet | Every behavior change ships with tests; `pytest` is part of the validation gate. |
| Dependencies and tooling | TODO — no `pyproject.toml` yet | Lint and format with `ruff`. |
| CI | TODO — no workflows yet | CI should run the same commands as the validation gate below. |
| Specs and plans | `.ai/specs/`, `.ai/runs/` | Specs use `{YYYY-MM-DD}-{kebab-case-title}.md`. |
| Tracker and browser operations | `.ai/trackers/github.md`, `.ai/browsers/none.md` | GitHub through `gh`. No UI, so no browser automation: verify through tests and HTTP requests. |

## Validation gate

Run in order; any non-zero exit fails the gate:

1. `ruff check .`
2. `ruff format --check .`
3. `pytest`

These commands start passing once the Python project and its dev dependencies are added.

## Repository rules

- Never commit secrets, tokens, `.env` files, or personal data. The repository is public.
- Configuration comes from environment variables; document new ones without real values.
- Pipeline configuration: `.ai/agentic.config.json`. Per-skill overrides: `.ai/skills/<skill-name>/SKILL.md`.
