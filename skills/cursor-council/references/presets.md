# Presets

`cursor-council` presets are native-only JSON files. They declare the seats, the
turn order, and the final synthesizer. The helper script validates the shape and
uses it to decide which turns are still missing.

## Schema

```json
{
  "name": "council",
  "rounds": 2,
  "stop_condition": "One drafting round, one critique round, then synthesis.",
  "seats": {
    "gpt": { "model": "gpt-5.4-xhigh" },
    "opus": { "model": "claude-opus-4-8-thinking-xhigh" }
  },
  "turns": [
    {
      "name": "draft",
      "seat": "gpt",
      "role": "writer",
      "round": 1,
      "instruction": "Draft the first answer."
    }
  ],
  "final": {
    "name": "synthesis",
    "seat": "opus",
    "role": "synthesizer",
    "instruction": "Produce the final Markdown answer."
  }
}
```

## Field Rules

- `name`: preset name shown in the run metadata.
- `rounds`: highest numbered discussion round. Same-round turns are independent
  and may be launched in parallel.
- `stop_condition`: brief human description of when the council is done.
- `seats`: seat name to Cursor model slug.
- `turns`: planned discussion turns. Each `name` must be unique.
- `final`: the final synthesis turn. Its `name` must not duplicate a discussion
  turn.

`record --turn <name>` looks up the planned turn by `name`, writes its note into
`turns/`, and rebuilds `transcript.md` in preset order.

## Model Binding

Model binding is first-class. Each seat declares the exact Cursor model slug the
chair should pass to the Task subagent. Reasoning level is part of that slug.

Known slugs at authoring time:

- `claude-4.6-sonnet-medium-thinking`
- `claude-opus-4-8-thinking-xhigh`
- `composer-2.5`
- `composer-2.5-fast`
- `gpt-5.4-xhigh`
- `gpt-5.5-extra-high`

The Task tool's own allowed-model list is the source of truth if Cursor changes.
Keep the presets aligned with that list instead of inventing slugs.

## Prompt Construction

The script does not build prompts. The chair does.

For each turn, construct a prompt from:

1. `brief.md`
2. the relevant repository or user context
3. the current `transcript.md`
4. the turn's `instruction`

Give the subagent only that constructed prompt. Do not leak the chair's private
session history into a seat.

## Built-in Presets

- `council`: general writer -> parallel critics -> synthesis.
- `research-dossier`: evidence matrix -> source audit -> mandatory source repair
  -> parallel critiques -> dossier synthesis.
- `review`: target map -> parallel review critiques -> summarized findings.
- `selftest`: tiny plumbing-only workflow for `start`/`record`/`finalize`/
  `inspect`.
