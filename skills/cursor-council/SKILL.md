---
name: cursor-council
description: Runs council-style multi-model synthesis in Cursor with read-only Task subagents and a deterministic run directory. Use when the user wants a roundtable, council, panel, debate, adversarial or independent multi-model review, or a source-backed research dossier.
---

# Cursor Council

Use this skill to run a bounded read-only council inside Cursor. The chair stays
responsible for the brief, the preset, the prompts, the final synthesis, and
what gets delivered to the user.

## Use When

- The user wants a roundtable, council, panel, debate, or adversarial review.
- The task benefits from independent seats with different models.
- The user wants a durable Markdown deliverable plus a traceable run directory.
- The task is research, design critique, or review, not direct code editing.

## Avoid When

- A direct answer is enough.
- The user wants immediate code changes instead of deliberation.
- You cannot or should not spawn Task subagents.

## Chair Loop

1. Write a concise brief or use the user's brief verbatim.
2. Pick a preset from `assets/presets/`. Read
   [references/presets.md](references/presets.md) first; for source-backed
   investigations, also read
   [references/research-dossier.md](references/research-dossier.md).
   Add `--cheap` to `start` when the user wants every seat on `composer-2.5`
   instead of the preset's premium models.
3. Run the helper script:

   ```bash
   COUNCIL_SCRIPT="/path/to/cursor-council/scripts/council.py"
   PROJECT_ROOT="$(pwd)"

   python3 "$COUNCIL_SCRIPT" start \
     --preset council \
     --topic "<topic>" \
     --workdir "$PROJECT_ROOT"

   # lower-cost run: all seats use composer-2.5
   python3 "$COUNCIL_SCRIPT" start \
     --preset council \
     --cheap \
     --topic "<topic>" \
     --workdir "$PROJECT_ROOT"
   ```

4. Read the printed plan. For each planned turn in a round:
   - build a prompt from `brief.md`, the relevant repository context, and the
     current `transcript.md`;
   - spawn one read-only Task subagent per turn;
   - pass the seat's bound model exactly as declared in the run config;
   - give the subagent only that constructed prompt, not your own session
     history;
   - launch same-round turns in parallel when they are independent;
   - save each final subagent message to a file and `record` it.
5. After the last round, synthesize the final yourself or with a final
   read-only Task subagent, then `finalize --from-file`.
6. Run `inspect`, read `final.md`, and answer from it.
7. If a turn is weak or fails, run that same turn again and `record` it again.
   There is no separate recovery mode.

## Commands

```bash
python3 "$COUNCIL_SCRIPT" start \
  --preset council \
  --topic "<topic>" \
  --workdir "$PROJECT_ROOT"

python3 "$COUNCIL_SCRIPT" record \
  --run-dir "<run-dir>" \
  --turn draft \
  --from-file draft.md \
  --prompt-file draft.prompt.md

python3 "$COUNCIL_SCRIPT" finalize \
  --run-dir "<run-dir>" \
  --from-file final.md

python3 "$COUNCIL_SCRIPT" inspect --run-dir "<run-dir>"
```

## Council Rules

- Seats are read-only. They deliberate and synthesize; they do not edit project
  files.
- Different seats should use different models when the preset says so. If two
  seats must share one model, say that explicitly in `final.md`. Cheap runs
  (`--cheap`) always share `composer-2.5`; disclose that in `final.md`.
- Preserve disagreement. Do not smooth it away just to sound decisive.
- `final.md` is the canonical output and stays in the run directory unless the
  user asks to promote it elsewhere.
- Re-recording a turn replaces that seat's current note and invalidates any old
  `final.md`; finalize again after rerunning turns.

## References

- [references/presets.md](references/presets.md): preset schema, model bindings,
  and built-in workflows.
- [references/research-dossier.md](references/research-dossier.md):
  citation-integrity doctrine for source-backed investigations.
