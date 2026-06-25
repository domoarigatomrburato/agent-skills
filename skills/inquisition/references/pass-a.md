# Pass A — Architecture and Dependency Health

Account for every dimension: emit a finding (`file:line` + severity) or mark `N/A for scope` with reason.

At `depth=quick`, cover only dimensions marked **high-signal**.

| Dimension | Quick |
|-----------|-------|
| Module/package boundaries and layering violations | **high-signal** |
| Dependency direction (inward toward domain, no forbidden upward imports) | **high-signal** |
| Coupling hotspots (files/modules with disproportionate fan-in or fan-out) | **high-signal** |
| Dependency cycles | **high-signal** |
| Duplicated logic across modules | |
| Dead code (unreachable exports, unused modules) | |

Prefer `rg`, `rg --files`, and read-only project inspection over broad directory walks.
