# Pass B — Standards and Compliance

Account for every dimension: emit a finding (`file:line` + severity) or mark `N/A for scope` with reason.

At `depth=quick`, cover only dimensions marked **high-signal**.

Run non-destructive checks when relevant and not blocked by `constraints`.

| Dimension | Quick |
|-----------|-------|
| Tests (failures, missing coverage on critical paths) | **high-signal** |
| Lint and typecheck (when configured in the project) | **high-signal** |
| Security basics (secrets, injection surfaces, unsafe defaults) | **high-signal** |
| Error handling and failure modes | |
| Naming consistency and public API clarity | |
| Logging and observability gaps | |
| Configuration hygiene (env vars, secrets handling, defaults) | |
| Documentation and test gaps for public surfaces | |

Prefer actionable remediation over cosmetic style notes unless the user requested strict style compliance.
