# External Seats

Use external seats when the confirmed plan needs real model or harness
diversity beyond the chair's Codex harness. Codex remains the chair and records
the run; Cursor, Copilot, or another CLI acts as one council seat.

## Safety Contract

- Keep external seats read-only by default.
- Do not silently replace a missing external CLI with an internal Codex seat.
- Record degraded mode in `council-plan.md` before continuing without the
  external seat.
- Do not pass secrets in prompts, config, model names, or command arguments.

## Providers

`run-shell-seat` supports three shell-backed providers:

- `cursor`: invokes Cursor Agent as `agent --print --output-format text --mode
  ask [--model <model>] "{prompt}"`. `--mode ask` is the default read-only
  posture; the helper does not add `--force` or `--yolo`.
- `copilot`: invokes GitHub Copilot CLI as `copilot --no-color
  --no-auto-update --no-remote --stream off --silent --plan [--model <model>]
  --prompt "{prompt}"`. The helper does not add `--allow-all`, `--allow-all-tools`,
  or `--yolo`.
- `shell`: invokes a caller-provided command. If the command contains
  `{prompt}`, that argument is replaced with the prompt. If it contains
  `{prompt_file}`, that argument is replaced with the materialized prompt path
  in the run directory. Otherwise the prompt is sent on stdin.

Verify current local CLI help before relying on a provider in a high-impact run:

```bash
agent --help
copilot --help
```

## Model Discovery

Treat `provider` and `model` as separate choices. The user may ask for the same
model family through different harnesses, such as `provider=copilot,
model=claude-opus-4.8` or `provider=cursor,
model=claude-opus-4-8-thinking-high`.

### Cursor

Cursor has a script-friendly model discovery command:

```bash
agent models
```

Use the exact model id from that output with `--model`. The local Cursor CLI
also documents parameterized model overrides, for example:

```bash
agent --print --output-format text --mode ask \
  --model 'claude-opus-4-8[context=1m,effort=high,fast=false]' \
  "Reply exactly: OK"
```

For a high-impact council, still probe the chosen id with a tiny read-only
prompt before assigning the real seat.

For budget-constrained Cursor seats, use `composer-2.5`. Do not use
`composer-2.5-fast` for council work; it costs more and is not worth the trade.

### Copilot

Copilot model discovery is less script-friendly:

- `copilot -i /model` opens the interactive picker and is the best human
  discovery surface.
- In automation, a natural prompt such as `List all available model IDs exposed
  by this local Copilot CLI session` may return the session's injected model
  list. Treat that as a candidate list, not a live registry guarantee.
- `/model list` can be useful but may be incomplete.
- The decisive check is a probe with the requested slug:

```bash
copilot --no-color --no-auto-update --no-remote \
  --no-custom-instructions --disable-builtin-mcps \
  --stream off --silent --plan \
  --model "claude-opus-4.8" \
  --prompt "Reply exactly: OK"
```

If the probe exits non-zero, mark the external seat unavailable. Do not silently
fall back to another model or to Codex.

Model ids observed locally on 2026-06-26 included `claude-sonnet-4.6`,
`claude-opus-4.8`, `claude-opus-4.7`, `claude-opus-4.6`, `gpt-5.5`,
`gpt-5.4`, `gpt-5.3-codex`, `gpt-5.4-mini`, `gpt-4.1`, and
`gemini-3.1-pro-preview`. Rediscover before each serious run.

## Command Shape

Build and save the prompt first. Then run the external seat:

```bash
python3 "$COUNCIL_SCRIPT" run-shell-seat \
  --run-dir "<run-dir>" \
  --turn evidence-matrix \
  --provider cursor \
  --prompt-file evidence-matrix.prompt.md \
  --model "sonnet-4-thinking"
```

For Copilot:

```bash
python3 "$COUNCIL_SCRIPT" run-shell-seat \
  --run-dir "<run-dir>" \
  --turn adoption-risk \
  --provider copilot \
  --prompt-file adoption-risk.prompt.md \
  --model "claude-opus-4.8"
```

For a generic shell command:

```bash
python3 "$COUNCIL_SCRIPT" run-shell-seat \
  --run-dir "<run-dir>" \
  --turn evidence-matrix \
  --provider shell \
  --prompt-file evidence-matrix.prompt.md \
  --command 'my-seat-cli --prompt-file {prompt_file}'
```

On success, the helper records the turn into `turns/` and rebuilds
`transcript.md`. It also writes external audit artifacts under
`external/<turn>/`:

- `prompt.md`
- `stdout.txt`
- `stderr.txt`
- `response.md`
- `metadata.json`

`metadata.json` includes provider, mode, read-only strategy, cwd, timeout,
redacted argv, version preflight output, prompt hash, stdout/stderr/response
paths, exit code, duration, and error text when present.

## Preset Fields

Seat definitions may include external defaults:

```json
"evidence_cursor": {
  "model_slot": "balanced",
  "provider": "cursor",
  "model": "sonnet-4-thinking",
  "mode": "read-only",
  "timeout_seconds": 1800
}
```

Turns or seats may include `prompt_file`; explicit `--prompt-file` still wins.
