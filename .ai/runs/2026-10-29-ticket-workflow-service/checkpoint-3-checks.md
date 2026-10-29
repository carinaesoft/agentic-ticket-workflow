# Checkpoint 3 — Phase 3 (Durable processing)

**Timestamp:** 2026-10-29T15:26:08Z
**Steps covered:** 3.1 – 3.4 (f6957ae..08c3039)
**Touched areas:** fake Helpdesk, activities, TicketWorkflow, worker entrypoint, test-server warm-up, conftest

| Check | Result |
|---|---|
| `ruff check .` | ✅ pass |
| `ruff format --check .` | ✅ pass |
| `pytest` | ✅ pass — 142 tests (time-skipping test server cached in `.temporal-test-server/`) |
| Workflow scenarios (answered, approved, 24 h timeout, retry-then-success, rejected, rule violation, unknown customer, retries exhausted, act always failing, late and repeated approvals) | ✅ pass |
| End to end T-1 … T-7 with real activities, fake model and scripted Helpdesk failures (incl. lost response on T-2's refund → exactly one refund) | ✅ pass |
| Log lines per ticket carry ticket_id + workflow_id | ✅ pass |
| `python scripts/warm_test_server.py` | ✅ pass |
| UI verification | ⏭️ skipped — no UI |
