# Provider And Config Notes

Presets are JSON so they remain portable and standard-library friendly.

## Config Shape

```json
{
  "name": "example-roundtable",
  "max_rounds": 1,
  "stop_condition": "Stop after one round and a final synthesis.",
  "budget": {
    "turn_timeout_seconds": 900,
    "max_prompt_chars": 120000
  },
  "agents": {
    "codex": {
      "provider": "command",
      "command": ["codex", "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--cd", "{run_dir}", "-"],
      "input": "stdin",
      "output_format": "text"
    }
  },
  "artifacts": {
    "include": ["README.md", "src/**/*.py"]
  },
  "turns": [
    {
      "name": "draft",
      "agent": "codex",
      "role": "writer",
      "mode": "discuss",
      "instruction": "Draft the proposal."
    }
  ],
  "final": {
    "name": "final",
    "agent": "codex",
    "role": "synthesizer",
    "mode": "final",
    "instruction": "Produce the final answer."
  }
}
```

## Agent Fields

- `provider`: `command` or `mock`. Defaults to `command`.
- `command`: argv tokens for command providers.
- `input`: `stdin`, `argument`, `file`, or `none`.
- `output_format`: `text`, `json`, `stream-json`, or `auto`.
- `extract_paths`: optional JSON text paths such as `result`, `text`,
  `message.content`, or `content.0.text`.
- `markers`: optional `{ "start": "...", "end": "..." }` used to extract only
  the substantive response.
- `dirty_patterns`: optional phrases that indicate preambles or process
  narration in normalized output.
- `env`: optional string environment overrides.

Supported command tokens:

- `{run_dir}`
- `{workdir}`
- `{prompt}`
- `{prompt_file}`
- `{transcript_file}`
- `{skill_dir}`
- `{script_dir}`
- `{python}`
- `{env:NAME}`

## Cursor Guidance

Prefer:

```text
cursor-agent --print --output-format json --mode ask
```

The base presets rely on Cursor's default model so a host agent can run them
without setting extra environment variables. If you need an explicit model, add
`--model <model>` to a copied preset or generated config. Use `--mode plan`
only for operational planning turns. Ask Cursor to put the substantive answer
between:

```text
<roundtable-output>
...
</roundtable-output>
```

If markers are absent and the output includes process narration, mark the turn
dirty and clean only the normalized transcript. Keep raw JSON/stdout/stderr.

## Codex Guidance

Prefer read-only final and discussion turns:

```text
codex exec --sandbox read-only --skip-git-repo-check --cd <run-dir> -
```

Pass the prompt on stdin. Treat stdout as the answer and stderr as progress or
logs.

## Other Providers

Use `output_format: "json"` or `output_format: "stream-json"` plus
`extract_paths` when a provider emits structured responses. Avoid hardcoding
vendor schemas into the host workflow; preserve raw logs and adjust JSON paths
in the preset.
