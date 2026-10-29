# Final gate — ticket-workflow-service

**Timestamp:** 2026-10-29T15:51:00Z
**Range:** 16338e2..3e06eb5 (all Tasks rows done)

## Full validation gate (`validation.commands`, in order)

| Command | Result | Log |
|---|---|---|
| `ruff check .` | ✅ exit 0 | `final-gate-artifacts/ruff-check.log` |
| `ruff format --check .` | ✅ exit 0 (59 files) | `final-gate-artifacts/ruff-format.log` |
| `pytest` | ✅ exit 0 — 173 passed | `final-gate-artifacts/pytest.log` |

GitHub Actions (`.github/workflows/ci.yml`) ran the same gate green on push and pull_request for earlier heads of this branch.

## Integration suite

The repository has no separate integration runner and no UI (browser provider `none`), so `om-integration-tests` has nothing to drive; recorded as skipped with that reason. Integration coverage is:

- inside `pytest`: workflow tests in the Temporal time-skipping server, API tests against a worker running the real workflow, end-to-end T-1 … T-7 with the real activities, and the adversarial scripted model through loop + workflow;
- Step 5.3, a real Compose run on this host (`final-gate-artifacts/e2e-*`): demo output for T-1 … T-7 matched the spec table, duplicate T-1 → `200 duplicate: true`, T-2 approved → one refund despite a transient Helpdesk error, all 121 worker/API log lines JSON, the 21 T-2 lines all carry `ticket_id` + `workflow_id`, `temporal workflow list` shows 7 completed workflows, web UI answered 200;
- `docker compose run --rm tests` with `network_mode: none`: 173 passed; a connection attempt to pypi.org from that container fails (`e2e-tests-network-proof.log`).

## Design-system / style pass

Skipped: no UI and no design-system tooling in this repository. Style is enforced by ruff (above).
