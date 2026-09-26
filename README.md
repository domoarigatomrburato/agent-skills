# Agent Skills

Personal skills for Claude Code, Cursor and Codex, kept in one repository. Each skill is
invoked explicitly; its instructions are maintained here and no other skill collection is
required.

| Skill | Purpose |
|---|---|
| `grilling` | Challenge a plan through focused, consequential questions. |
| `domain-modeling` | Clarify domain concepts and record concise, durable decisions. |
| `inquisition` | Independently review correctness, test evidence, and design; fix supported issues. |
| `ideogram-prompt` | Ideogram 4 captions: structured JSON with magic prompt off, or plain text with magic prompt on. Ships a validator that ports Ideogram's `CaptionVerifier`. |
| `krea-prompt` | Krea 2 and Krea 2 Turbo prompts. Ships a linter that counts tokens against the 507-token prompt budget and a size calculator for 1K and 2K. |
| `drawthings` | Render prompts through the Draw Things app's API server: model recipes (Krea 2 Turbo and Ideogram 4 on Draw Things+ cloud compute, or local models), seed sets, retries, PNGs with a run log and a contact sheet. |

## Development workflow

Use Grilling when important choices are unresolved and Domain Modeling when
concepts or durable decisions need clarification. Implement normally, following
the repository's testing and validation rules. At a meaningful completion point,
request Inquisition on the changes:

> Implement feature X, then use Inquisition on the complete changes.

Inquisition uses two fresh reviewers and one coordinating editor: one reviewer
covers correctness and test evidence, the other design and efficiency. See the
[skill's model and reasoning defaults](skills/inquisition/SKILL.md#model-and-reasoning-defaults)
for model selection across hosts. It handles commits, revision ranges, branch
changes, uncommitted work, or an explicitly combined scope.
A bare invocation selects staged, unstaged, and untracked changes. Ask for
review-only to receive findings without edits. Fixes stay within the requested
behavior; commits, pushes, and publication require the user's authorization.

There is no separate implementation skill. Inquisition requires a failing regression
test for a testable bug it fixes, without imposing TDD on every feature or
refactor. It reports incomplete coverage or unavailable independent review.

Use `$skill-name` in Codex or `/skill-name` in Cursor and Claude Code. Codex
invocation policy and Cursor/Claude frontmatter disable implicit activation.
Repository rules govern ordinary development even when no skill is invoked.
Reading a skill for review does not invoke it.

## Image prompting

Both prompting skills are reconstructed from the model maker's own documentation and code.
They pick the mode or the length from the brief, write the prompt, lint it, and hand over the
settings for the delivery target: the Ideogram MCP, REST API, web app or open weights; the Krea
app, API, MCP server, ComfyUI, fal, Draw Things or the reference CLI. API keys are read from
`IDEOGRAM_API_KEY` and `KREA_API_TOKEN` and never written into a prompt or a log.

The Krea linter counts tokens exactly when it has the tokenizer files of Krea 2's text encoder,
Qwen3-VL. Fetch them once (about 4.4 MB, Apache-2.0, from Hugging Face):

```bash
python3 skills/krea-prompt/scripts/lint_prompt.py --fetch-tokenizer
```

They land in `~/.cache/krea-prompt/tokenizer` (or under `XDG_CACHE_HOME`), where the linter
finds them on every run; `--tokenizer DIR` or `KREA_TOKENIZER_DIR` point at another folder.
Without them the linter falls back to a word-based estimate calibrated on Krea's example
prompts, within about 7% of the true count. The scripts are standard-library Python 3.8+.

## Rendering with Draw Things

The `drawthings` skill sends prompts to the Draw Things app's API server (gRPC, TLS) and, with
Bridge Mode on, to Draw Things+ cloud compute, so cloud-only models such as Krea 2 Turbo and
Ideogram 4 render without local downloads. It builds on the `drawthings-py` SDK and adds the
model spec override those models need. One-time setup creates a private virtualenv:

```bash
bash skills/drawthings/scripts/setup.sh
python3 skills/drawthings/scripts/dt_render.py --check
```

Each run writes the PNGs, the exact prompt, a `run.json` and a contact sheet to its folder and
can append a line per image to a project's `runs.jsonl`; the cloud's random aborts are retried. Before
sending, it estimates the request's compute units with the app's own formula and refuses jobs
over the tier limit, so a 48-step 2K Ideogram job is stopped locally instead of by the cloud.

## Install

Install from the published GitHub repository for local Cursor, Codex, and Claude:

```bash
npx skills@latest add domoarigatomrburato/agent-skills -g --skill grilling domain-modeling inquisition ideogram-prompt krea-prompt drawthings --agent universal claude-code -y
```

Universal installs to the shared global directory used by Cursor and Codex;
Claude Code receives links to the same files. Remote agents need their own
installation. After publishing skill changes, rerun the command to refresh them.
Removing a skill from this repo does not uninstall an existing global copy;
remove retired skills explicitly with the CLI.

Inspect installations with `npx skills@latest list -g`; remove a named skill with
`npx skills@latest remove <skill-name> -g -y`.

For development, inspect a working copy without changing global installs:

```bash
npx skills@latest add . --list
```

Normal installations should track GitHub. If intentionally switching an existing
remote installation to a local source, remove the old named installation first:
Skills CLI 1.5.25 can retain its upstream tracking record during a local overwrite.

## Attribution

Grilling and Domain Modeling are locally maintained adaptations of Matt Pocock's
MIT-licensed [skills](https://github.com/mattpocock/skills), based on the installed
versions updated on 2026-08-21. Their folders preserve the upstream license.
They retain focused questioning, domain vocabulary, and ADR practices while
removing cross-skill dependencies and narrowing activation and scope.

The prompting skills quote their official sources in their `references` folders:

- [krea-ai/krea-2](https://github.com/krea-ai/krea-2) (Apache-2.0): `docs/prompting.md`,
  `docs/expansion.txt`, `encoder.py`, `sampling.py`, `README.md`, plus Krea's public docs.
- [ideogram-oss/ideogram4](https://github.com/ideogram-oss/ideogram4) (Apache-2.0):
  `docs/prompting.md`, the magic-prompt system prompt and `CaptionVerifier`, plus Ideogram's
  public docs and API reference.
- [Qwen/Qwen3-VL-4B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct) (Apache-2.0):
  tokenizer files, downloaded on demand and not included here.

The Draw Things skill depends at run time on [kcjerrell/drawthings-py](https://github.com/kcjerrell/drawthings-py)
(GPL-3.0, installed from PyPI into its own virtualenv, no code copied here) and documents the
protocol of [drawthingsai/draw-things-community](https://github.com/drawthingsai/draw-things-community)
(GPL-3.0) in its references.

The `.claude-plugin/plugin.json` manifest groups the skills under
`DomoArigatoMrBurato-skills` in compatible hosts.
