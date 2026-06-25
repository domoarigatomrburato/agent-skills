# Roundtable Arbiter Workflow

The host agent is the arbiter. The script only handles deterministic filesystem
and subprocess work.

## Standard Run

1. Convert the user request into a brief with topic, desired output, constraints,
   audience, and any known sources or project paths.
2. Choose a preset:
   - `mock`: validate the blackboard without external CLIs.
   - `research`: produce a research document.
   - `research-dossier`: produce source-backed research with an evidence matrix.
   - `code-review`: review code or active changes.
   - `architecture-review`: critique a design or technical plan.
3. Run the installed skill runtime by path. Do not change into the skill
   directory; keep the target project explicit with `--workdir`:

```bash
ROUNDTABLE_SCRIPT="/path/to/agents-roundtable/scripts/roundtable.py"
PROJECT_ROOT="<project-root>"

python3 "$ROUNDTABLE_SCRIPT" run \
  --preset research \
  --topic "<topic>" \
  --workdir "$PROJECT_ROOT" \
  --out "<output-root>"
```

While `run` executes, the runtime streams progress to stderr: a `start`/`done`
line per turn plus a heartbeat every `budget.heartbeat_seconds` (default 30) for
long command turns. Use this to confirm a turn is alive rather than hung.

4. Inspect:

```bash
python3 "$ROUNDTABLE_SCRIPT" inspect --run-dir "<run-dir>"
```

5. Read the turn markdown and raw logs for failures, dirty output, weak claims,
   or unresolved disagreement.
6. Retry specific turns or finalize manually when needed.
7. Read `final.md` and deliver its substance, naming caveats and unresolved
   disagreement.

For source-backed runs (`research-dossier`), also confirm the citation-integrity
verdict and the repair pass: read the `source-auditor` turn for
`CITATION_INTEGRITY: PASS`/`FAIL`, check that the `source-repair` turn applied
corrections on `FAIL`, and confirm `final.md` keeps the contamination visible in
its Citation Integrity & Corrections section. See `references/research-dossier.md`.

## Blackboard Contract

Each run directory contains:

```text
brief.md
config.json
transcript.md
transcript.completed.md   # only when recovery/finalization extends the run
final.md
RECOVERY.md               # only when recovery occurs
turns/
  001-r01-agent-role.prompt.md
  001-r01-agent-role.stdout
  001-r01-agent-role.stderr
  001-r01-agent-role.md
artifacts/
  manifest.md
  files/
```

The normalized transcript is a convenience layer. Raw stdout/stderr are the
audit trail.

## Delivery

`<run-dir>/final.md` is the canonical final output. Keep it in the run
directory with the transcript, recovery notes, turns, prompts, stdout, stderr,
and artifacts.

Do not copy, move, commit, publish, or otherwise promote the final document
outside the run directory unless the user asks or confirms. If the result is
likely to become durable project or organizational knowledge, offer to save a
copy to a destination the user chooses.

## Arbiter Decisions

The host should decide:

- whether a failed turn should be retried, skipped, or summarized;
- whether dirty output is still usable after cleanup;
- whether a final synthesis has enough support;
- whether unresolved disagreements belong in `final.md`;
- whether any apply turn is worth requesting explicit human approval.

Do not let the runtime hide uncertainty. A good final document says where the
agents disagree and what would change the recommendation.
