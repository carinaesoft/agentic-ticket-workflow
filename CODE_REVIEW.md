# Code review rules

These rules apply to every PR in this repository, in addition to the built-in checklist of `om-code-review`, which applies this file automatically. The stack is Python with FastAPI for the HTTP API and Temporal for durable workflows.

## Review priorities

1. **Correctness** — the change does what the issue or spec asks, including failure paths.
2. **Security** — no secrets or personal data in code, tests, fixtures, or logs; untrusted input is validated.
3. **Contracts** — HTTP request/response shapes and Temporal workflow/activity signatures do not change silently.
4. **Quality** — readable, tested, consistent with the surrounding code.

## Repository-specific checks

### Validation gate

- `ruff check .`, `ruff format --check .`, and `pytest` pass.
- New behavior has tests; bug fixes include a regression test.

### FastAPI

- Request bodies and responses are typed with Pydantic models; handlers do not accept or return untyped dicts.
- Input is validated at the boundary; errors return explicit status codes (`4xx` for client errors) rather than unhandled exceptions.
- Handlers stay thin: business logic lives outside the route function, so it can be tested without HTTP.
- Blocking I/O is not called from `async` handlers.
- Configuration and credentials come from environment or settings objects, never hard-coded.

### Temporal

- Workflow code is deterministic: no direct I/O, network calls, `datetime.now()`, `random`, or threads inside workflows. Use activities and Temporal's workflow-safe APIs.
- Activities are idempotent or safe to retry, and declare timeouts and retry policies explicitly.
- Changing a workflow that may have running executions uses versioning (patching) instead of editing logic in place.
- Workflow and activity inputs and outputs are serializable, explicitly typed data classes or models.
- Long-running or human-in-the-loop steps use signals, queries, or updates rather than polling.
- Workflow tests use Temporal's testing environment (time skipping) instead of real sleeps.

### Agentic behavior

- Calls to language models or other external agents happen in activities, never in workflow code.
- Model output is treated as untrusted input: parsed and validated before it drives a decision or a state change.
- Prompts, responses, and logs contain no secrets or personal data.

## Severity guidance

- **Blocker** — incorrect behavior, nondeterministic workflow code, security issue, leaked secret or personal data, breaking an API or workflow contract without a migration path, failing validation gate.
- **Major** — missing tests for new behavior, missing timeouts or retry policy on an activity, unvalidated external input.
- **Minor** — naming, structure, or readability issues that do not affect behavior.
- **Nit** — style preferences not enforced by `ruff`.

Blockers and majors result in `changes-requested`; minors and nits do not block approval and may be turned into follow-up issues.
