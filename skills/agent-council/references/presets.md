# Presets

Presets declare the epistemic seats, turn order, and final contract. They do not
bind universal model names. The chair resolves each `model_slot` at runtime and
records the actual model used for every turn.

## Schema

```json
{
  "name": "council",
  "rounds": 2,
  "stop_condition": "Build one proposal, gather critiques, then synthesize.",
  "seats": {
    "proposal_builder": { "model_slot": "balanced" },
    "risk_critic": { "model_slot": "balanced" },
    "chair_editor": { "model_slot": "chair" }
  },
  "turns": [
    {
      "name": "proposal",
      "seat": "proposal_builder",
      "role": "proposal_builder",
      "round": 1,
      "instruction": "Draft the first answer."
    }
  ],
  "final": {
    "name": "chair-synthesis",
    "seat": "chair_editor",
    "role": "final_editor",
    "instruction": "The chair normally writes the final Markdown answer."
  }
}
```

## Field Rules

- `name`: preset name shown in run metadata.
- `rounds`: highest numbered discussion round. Same-round turns are independent
  and may be launched in parallel from the same transcript snapshot.
- `stop_condition`: concise description of when the council is done.
- `seats`: epistemic seat names to capability-oriented `model_slot` values.
- `turns`: planned discussion turns. Each `name` must be unique.
- `final`: final editing contract. Its `name` must not duplicate a discussion
  turn.

`record --turn <name>` looks up the planned turn, writes its note into `turns/`,
archives any previous current attempt, and rebuilds `transcript.md`.

## Model Slots

`model_slot` is a capability request, not a model slug:

- `smoke`: lightest acceptable plumbing-test model.
- `balanced`: serious reasoning floor for substantive seats.
- `frontier`: strongest available model for high-impact seats.
- `chair`: the chair's own model or an explicitly chosen final editor.

The chair may use Cursor, Codex, Claude, Copilot, or another harness-specific
resolver. If model selection is unavailable, record `harness default` and
disclose the limitation in the plan and final.

## Profile Fit

- `smoke` -> `selftest`
- `budget` -> `research-dossier-budget` for source-backed dossier work
- `standard` or `premium` -> `research-dossier` for fuller source-backed
  dossier work

The helper warns, but does not block, if a built-in profile/preset pair looks
mismatched.

## Prompt Construction

The script does not build prompts. The chair does.

For each turn, construct a prompt from:

1. `brief.md`
2. relevant repository or user context
3. `transcript.md` and current turn file paths
4. the turn's `instruction`

For long runs, point subagents at files on disk instead of replacing the
transcript with a lossy summary. Use
[prompt-template.md](prompt-template.md) for non-smoke turns. Save each prompt
and response verbatim before calling `record`.

## Built-in Presets

- `selftest`: smoke-only plumbing workflow.
- `council`: proposal -> parallel risk/pragmatic critiques -> chair synthesis.
- `review`: target map -> correctness/maintainability critiques -> chair review.
- `research-dossier-budget`: first-pass dossier with one combined decision
  critique.
- `research-dossier`: fuller dossier with re-audit plus separate adoption-risk
  and clarity-calibration critiques.
