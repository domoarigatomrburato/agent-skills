---
name: agent-council
description: Runs a preflighted council with read-only subagents, durable transcript, model-resolution disclosure, and a final Markdown deliverable. Use when the user asks for a council, adversarial review, independent multi-model review, or source-backed research dossier.
---

# Agent Council

Use this skill to chair a bounded read-only council in any harness that can spawn
subagents. The chair owns the brief, preflight, prompts, transcript, final
editing, and delivery to the user.

## Use When

- The user wants a council, panel, debate, or adversarial review.
- Independent seats can improve research, design critique, or review quality.
- The user wants a durable Markdown output plus an auditable run directory.

## Avoid When

- A direct answer is enough.
- The user wants immediate code changes instead of deliberation.
- The harness cannot spawn read-only subagents.

## Chair Loop

1. Frame the brief and choose a preset/profile. Read
   [references/presets.md](references/presets.md) and
   [references/profiles.md](references/profiles.md). For source-backed
   investigations, also read
   [references/research-dossier.md](references/research-dossier.md).
2. Run preflight before spawning subagents. Resolve the seats to concrete
   models or harness defaults, present the plan and meaningful alternatives to
   the user, and wait for confirmation unless the user already gave an explicit
   preset/profile/proceed instruction. Completion criterion: the confirmed plan
   states preset, profile, seats, resolved models, model diversity, limitations,
   and decision grade. Use
   [references/council-plan-template.md](references/council-plan-template.md)
   when drafting the plan.
3. Save the confirmed plan, then start the run:

   ```bash
   COUNCIL_SCRIPT="/path/to/agent-council/scripts/council.py"
   PROJECT_ROOT="$(pwd)"

   python3 "$COUNCIL_SCRIPT" start \
     --preset research-dossier-budget \
     --profile budget \
     --plan-file council-plan.md \
     --topic "<topic>" \
     --workdir "$PROJECT_ROOT"

   # Equivalent shorthand for the budget profile.
   python3 "$COUNCIL_SCRIPT" start \
     --preset research-dossier-budget \
     --budget \
     --plan-file council-plan.md \
     --topic "<topic>" \
     --workdir "$PROJECT_ROOT"
   ```

4. For each planned turn, build a fresh prompt from `brief.md`, relevant
   repository or user context, transcript/turn file paths, and the turn
   instruction. Give the subagent only that prompt, launch independent same-round
   turns in parallel, save the prompt and final response verbatim, then record.
   Use [references/prompt-template.md](references/prompt-template.md) for
   non-smoke prompts:

   ```bash
   python3 "$COUNCIL_SCRIPT" record \
     --run-dir "<run-dir>" \
     --turn evidence-matrix \
     --from-file evidence-matrix.md \
     --prompt-file evidence-matrix.prompt.md \
     --model "<resolved-model>"
   ```

5. If a turn is weak or fails, rerun that same turn and record it again. The
   helper archives the old current attempt and invalidates any old `final.md`.
6. The chair writes `final.md` by default. Use a final subagent only when the
   confirmed plan calls for one, then disclose that choice.
7. Finalize, inspect, read `final.md`, and answer the user from it:

   ```bash
   python3 "$COUNCIL_SCRIPT" finalize \
     --run-dir "<run-dir>" \
     --from-file final.md \
     --model "<chair-or-final-model>" \
     --decision-grade "first-pass, not procurement-ready" \
     --model-diversity "absent, same-model council"

   python3 "$COUNCIL_SCRIPT" inspect --run-dir "<run-dir>"
   ```

## Council Rules

- Seats are read-only: they deliberate and synthesize; they do not edit project
  files.
- Fidelity is mandatory outside smoke runs: record full prompts and full seat
  outputs, not summaries.
- Same-round seats read the same starting transcript snapshot; they do not see
  each other's in-flight work.
- Preserve material disagreement. The chair may correct, merge, reject, or
  elevate seat outputs, but must explain major overrides.
- `final.md` is the canonical output and stays in the run directory unless the
  user asks to promote it elsewhere.

## References

- [references/profiles.md](references/profiles.md): profiles, preflight, model
  resolution, diversity labels, and final grade.
- [references/presets.md](references/presets.md): preset schema and built-in
  workflows.
- [references/council-plan-template.md](references/council-plan-template.md):
  non-smoke plan format and confirmation phrase.
- [references/prompt-template.md](references/prompt-template.md): non-smoke
  turn prompt shape.
- [references/research-dossier.md](references/research-dossier.md): citation
  integrity and repaired-matrix doctrine.
