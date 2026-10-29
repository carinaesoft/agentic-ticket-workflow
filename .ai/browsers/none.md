# Browser provider: none

This repository is a backend HTTP API with no user interface, so no browser
automation is configured. The config selects this descriptor with
`browser.provider: "none"`.

Every operation below is intentionally unavailable. Browser-capable skills
(`om-prepare-test-env`, `om-auto-qa-pr`, `om-integration-tests`) must not
install or improvise a browser here. Verify behavior through the API instead:
automated tests from the validation gate, and HTTP requests against a running
service (for example `curl` against the routes under test), with the request and
response captured as evidence.

To add a browser later (for example when a UI is introduced), re-run
`om-setup-agent-pipeline` and choose `agent-browser` or `playwright`.

## Contract

### ensure-installed

Install nothing. Output:

```text
BROWSER_PROVIDER=none
BROWSER_INSTALLED=0
BROWSER_COMMAND=
BROWSER_VERSION=unknown
BROWSER_NOTES=No browser provider: backend API without UI; verify through HTTP requests and tests
```

### doctor

Return non-zero with the note above. Callers treat this as "no browser
evidence possible", not as an environment failure.

### open / snapshot / interact / assert / screenshot

Not supported. Return non-zero with the note above.

### close

No-op; return zero.
