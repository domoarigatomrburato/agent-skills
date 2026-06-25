---
name: inquisition
description: Inquisition — isolated three-pass codebase audit with judge synthesis into one prioritized report. Use when the user asks for a comprehensive health check, cross-referenced architecture and compliance review, or a severity-ranked remediation plan.
---

# Inquisition

Isolated three-pass audit: Pass A and B emit findings; Pass C judges from those outputs only.

## Inputs

- `scope`: Optional path, module, feature, or `recent changes`; default full repository.
- `depth`: `quick` or `full`; default `full`.
  - `quick`: cover only dimensions marked **high-signal** in the pass references; skip command runs unless the user requests them.
  - `full`: every dimension in the pass references must be accounted for.
- `output_mode`: `chat` or `file`; default `chat`.
- `mode`: `isolated` or `inline`; default `isolated`.
  - `isolated`: Pass A/B write intermediate files; Pass C loads only those files plus metadata.
  - `inline`: Pass A/B findings stay in context; Pass C synthesizes from inline pass outputs (no intermediate files).
- `constraints`: User limits (for example no test runs or no network).
- **Report paths** (`<ts>` = `YYYY-MM-DD_HHMMSS`):
  - Pass A: `reports/inquisition-pass-a-<ts>.md`
  - Pass B: `reports/inquisition-pass-b-<ts>.md`
  - Final: `reports/inquisition-report-<ts>.md`
- **Severity:** [`references/severity.md`](references/severity.md)

## Workflow

1. **Frame scope**
   - Resolve scope; state assumptions explicitly.
   - If scope is `recent changes`, inspect changed files before widening.
   - **Done when:** scope, depth, mode, constraints, and assumptions are stated.

2. **Pass A — architecture**
   - Inspect every applicable dimension in [`references/pass-a.md`](references/pass-a.md).
   - Prefer fast discovery (`rg`, `rg --files`) and read-only inspection.
   - Each dimension: a finding (`file:line` + severity) or `N/A for scope` with reason.
   - If `mode=isolated`, write only this pass to the Pass A path.
   - **Done when:** every Pass A dimension is accounted for and the pass output exists (file in isolated mode, listed findings in inline mode).

3. **Pass B — compliance**
   - Same pattern with [`references/pass-b.md`](references/pass-b.md).
   - Run non-destructive checks when relevant and not blocked by constraints.
   - If `mode=isolated`, write only this pass to the Pass B path.
   - **Done when:** every Pass B dimension is accounted for and the pass output exists (file in isolated mode, listed findings in inline mode).

4. **Pass C — judge**
   - If `mode=isolated`, load only the two pass files plus metadata (scope, depth, constraints). Do not re-scan the codebase unless evidence is missing and the user requested re-validation.
   - If `mode=inline`, synthesize from Pass A/B outputs already in context.
   - Build a cross-reference matrix: link findings that share files, modules, or root causes.
   - Classify each finding as `Cross-Referenced`, `Architecture-Only`, or `Compliance-Only`.
   - If Pass A and Pass B conflict, prefer the claim with stronger evidence; mark unresolved conflicts explicitly.
   - **Done when:** every finding from Pass A and Pass B appears in the matrix.

5. **Prioritize**
   - Rank by: severity (`Blocking > Advisory > Observation`), then `Cross-Referenced > Single-source`, then blast radius.
   - For each item include: Source, Category, Location (`file:line`), Why it matters, Suggested fix direction.
   - **Done when:** every matrix finding has a rank and action-item fields.

6. **Deliver**
   - Follow [`references/report-template.md`](references/report-template.md).
   - If `output_mode=file`, write the Final path; create `reports/` if missing.
   - If `mode=isolated`, mention all three file paths in the response.
   - **Done when:** output matches the template and paths are disclosed when applicable.

## Guardrails

- Do not claim failures that were not verified.
- In `isolated` mode, intermediate files are the source of truth for Pass C.
- Prefer actionable remediation over cosmetic style notes unless strict style compliance is requested.
- If no findings are discovered, state that explicitly and include residual risk and missing-test caveats.
