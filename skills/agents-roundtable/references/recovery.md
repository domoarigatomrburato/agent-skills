# Recovery Workflow

Recovery is expected. A useful roundtable preserves enough disk state for the
host agent to retry a failed turn, clean a dirty turn, and run a final synthesis.
Examples assume `ROUNDTABLE_SCRIPT` points to the installed
`agents-roundtable/scripts/roundtable.py`.

## Failed Turn

1. Run `inspect` and identify the failed turn, raw stdout, and raw stderr.
2. Read the failed prompt and the current transcript.
3. Build a shorter retry prompt when the failure is context or quota related.
4. Save that prompt as a Markdown file and run a manual turn with
   `--prompt-file`:

```bash
python3 "$ROUNDTABLE_SCRIPT" turn \
  --run-dir "<run-dir>" \
  --agent cursor_opus \
  --role critic \
  --name retry-critic \
  --prompt-file "<short-retry-prompt.md>" \
  --reason "Retry after provider quota/resource failure"
```

If you omit `--prompt-file`, the script rebuilds the standard prompt from
`brief.md`, the completed transcript, and the artifact manifest.

5. The script creates or extends `transcript.completed.md` and writes
   `RECOVERY.md`.
6. Finalize:

```bash
python3 "$ROUNDTABLE_SCRIPT" finalize --run-dir "<run-dir>" --force
```

## Dirty Output

Cursor and similar CLIs may emit preambles, process narration, or save-file
offers. Typical dirty phrases include:

```text
I'll look at...
Now let me...
I have everything I need...
dimmi se vuoi che lo salvo
tell me if you want me to save it
```

The normalized turn can remove standalone dirty lines, but raw stdout/stderr
must stay unchanged. If markers were configured and missing, treat the turn as
dirty even when the answer is usable.

## Final Recovery Files

When recovery extends the original run:

- leave `transcript.md` as the original automated transcript;
- write `transcript.completed.md` with manual retry/final turns appended;
- write `RECOVERY.md` with failure and recovery actions;
- write `final.md` from the recovered final synthesis.

Do not pretend the run completed cleanly. Say in the final answer that recovery
was used and what evidence was incorporated.
