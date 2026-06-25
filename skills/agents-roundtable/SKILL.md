---
name: agents-roundtable
description: Coordinate multiple headless coding or research agents through a disk blackboard, then synthesize a final Markdown document. Use when the user asks for a roundtable, panel, adversarial multi-agent review, research document, architecture critique, or recovery from a prior roundtable run.
---

# Agents Roundtable

## Purpose

Use this skill to run a bounded, inspectable collaboration between agents. The
host agent remains the arbiter: it chooses the brief, preset, retries, recovery
steps, and final synthesis.

The runtime is a portable Python standard-library script. It creates a
blackboard under `<output-root>/runs/<timestamp>/` with prompts, raw logs,
normalized turn notes, transcript files, artifacts, and `final.md`.

## Use When

- The user asks for a roundtable, panel, debate, independent critique, or
  multi-agent research pass.
- The task benefits from writer/critic/synthesizer separation.
- The user wants a durable final document with traceable raw agent output.
- A prior run failed and needs a retry, manual turn, or final recovery.

## Avoid When

- A single direct answer is enough.
- The user asks for immediate code edits rather than discussion or research.
- The task requires automatic consensus. This skill reports unresolved
  disagreement instead of smoothing it away.

## Host Workflow

1. Interpret the human request and write a concise brief.
2. Pick a preset from `assets/presets/` or generate a small JSON config.
3. Invoke this skill's runtime by path and pass the target project as
   `--workdir`.
4. Inspect turn markdown plus raw stdout/stderr before trusting the transcript.
5. Retry or recover dirty/failed turns when useful.
6. Finalize the run, read `final.md`, and deliver its substance with caveats.

## Commands

Do not change into the skill directory. Keep the working project explicit:

```bash
ROUNDTABLE_SCRIPT="/path/to/agents-roundtable/scripts/roundtable.py"
PROJECT_ROOT="$(pwd)"
RUN_DIR="/tmp/roundtable/runs/<timestamp>"

python3 "$ROUNDTABLE_SCRIPT" run \
  --preset mock \
  --topic "test topic" \
  --workdir "$PROJECT_ROOT" \
  --out /tmp/roundtable
python3 "$ROUNDTABLE_SCRIPT" inspect --run-dir "$RUN_DIR"
python3 "$ROUNDTABLE_SCRIPT" turn --run-dir "$RUN_DIR" --agent cursor_opus --role critic --name retry-critic
python3 "$ROUNDTABLE_SCRIPT" turn --run-dir "$RUN_DIR" --agent cursor_opus --role critic --name retry-critic --prompt-file retry.md
python3 "$ROUNDTABLE_SCRIPT" finalize --run-dir "$RUN_DIR"
python3 "$ROUNDTABLE_SCRIPT" pack --run-dir "$RUN_DIR" --dest /tmp
```

## Safety Rules

- Discussion and final turns must not modify project files.
- Apply turns are disabled unless both the config uses `mode: "apply"` and the
  host passes `--allow-apply` after explicit human approval.
- Raw stdout and stderr are always preserved. Normalized markdown is a cleaned
  view, never the source of truth.
- Cursor-style preambles or follow-up offers should be removed only from the
  normalized transcript and marked dirty; raw logs stay intact.
- Max rounds and stop conditions are explicit. Do not infer consensus.

## Delivery

The canonical output is always `<run-dir>/final.md`. After finalization, read
that file and answer the user from it.

Do not copy, move, commit, publish, or otherwise promote the final document
outside the run directory unless the user asks or confirms. When the document is
likely to be reused, offer to save a copy to a durable location chosen by the
user, such as project documentation, a decision record, a ticket or issue, a
pull request description, or another user-selected knowledge base.

Keep the run directory intact as the audit trail.

## References

- `references/arbiter.md`: host-agent operating procedure.
- `references/providers.md`: config shape and provider guidance.
- `references/recovery.md`: retry, dirty-output, and finalization workflow.
