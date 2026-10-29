# Checkpoint 4 — Phase 4 (HTTP API and containers)

**Timestamp:** 2026-10-29T15:42:42Z
**Steps covered:** 4.1 – 4.4 (ea80d6c..92fa153)
**Touched areas:** FastAPI app and schemas, Dockerfile, docker-compose.yml, .env.example, .dockerignore, demo script, logging

| Check | Result |
|---|---|
| `ruff check .` | ✅ pass |
| `ruff format --check .` | ✅ pass |
| `pytest` | ✅ pass — 162 tests |
| `docker compose config -q` (default and `tests` profile) | ✅ pass |
| `docker compose --profile tests build` + `docker compose run --rm tests` (`network_mode: none`) | ✅ pass — 158 tests at Step 4.2 |
| Smoke: `docker compose up -d --build` + `scripts/demo.sh` | ✅ all of T-1 … T-7 matched the spec table; duplicate T-1 → 200 `duplicate: true`; T-2 approved → one refund |
| Smoke: `docker compose logs worker api \| grep '"T-2"'` | ✅ 15 lines, all JSON, all with `ticket_id` + `workflow_id` |
| UI verification | ⏭️ skipped — no UI |

## Problem found and fixed forward

- The smoke run showed two plain-text uvicorn startup lines in the API log: JSON logging was configured in the lifespan, which runs after uvicorn prints them. Fixed in Step 4.4 (92fa153): logging is configured when the production app is created; re-checked on the running stack (0 non-JSON lines).

The stack was stopped with `docker compose down` (this project only). The recorded end-to-end run is Step 5.3.
