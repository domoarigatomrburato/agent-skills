# Turn Prompt Template

Use this shape for every non-smoke seat prompt. Keep large context as file
paths; do not replace it with a chair summary.

```markdown
# Agent Council Seat Prompt

You are the `[seat]` seat for an `agent-council` run.

## Role

[role-specific instruction from the preset]

## Read These Files

- Brief: `[run-dir]/brief.md`
- Transcript: `[run-dir]/transcript.md`
- Council plan: `[run-dir]/council-plan.md`
- Prior turn files:
  - `[run-dir]/turns/[prior-turn].md`

## Constraints

- Read-only: do not modify project files.
- Work from the files listed above, not from private chair context.
- Preserve material uncertainty and disagreement.
- Cite file paths or source URLs for claims that depend on evidence.

## Output Contract

[turn-specific output requirements]
```
