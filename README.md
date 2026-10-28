# Agent Skills

Personal skills for Claude Code, Cursor and Codex, kept in one repository. Each skill is
invoked explicitly; its instructions are maintained here and no other skill collection is
required.

| Skill | Purpose |
|---|---|
| `grilling` | Challenge a plan through focused, consequential questions. |
| `domain-modeling` | Clarify domain concepts and record concise, durable decisions. |
| `inquisition` | Clean up a set of changes with parallel reviewers, then review the result for bugs at a review level you name, high by default, with independent verifiers at the max level; fix supported issues. |
| `ideogram-prompt` | Ideogram 4 captions: structured JSON with magic prompt off, or plain text with magic prompt on. Ships a validator that ports Ideogram's `CaptionVerifier`. |
| `krea-prompt` | Krea 2 and Krea 2 Turbo prompts. Ships a linter that counts tokens against the 507-token prompt budget and a size calculator for 1K and 2K. |
| `z-image-prompt` | Z-Image Turbo prompts in English or Chinese, built on Tongyi-MAI's own prompt enhancer rules. Ships a linter that counts tokens against the 504-token window. |
| `drawthings` | Render prompts through the Draw Things app's API server: model recipes (Krea 2 Turbo, Ideogram 4, Qwen Image 2512 and Z Image Turbo on Draw Things+ cloud compute, SeedVR2 upscaling, or local models), seed sets, retries, PNGs with a run log and a contact sheet. |
| `token-audit` | Measure Claude Code token spend from local transcripts: spend by source, session, agent type and context size, review runs, compactions and re-reads, a compaction-threshold replay, agent prefix probes, and comparisons between saved reports. |
| `claude-memory-audit` | Audit Claude Code's memory files for scope, duplicates, obsolete facts, weak wording and index integrity; fix the real defects and report. Claude Code only, built to run unattended as a daily scheduled task. |

## Development workflow

Use Grilling when important choices are unresolved and Domain Modeling when
concepts or durable decisions need clarification. Implement normally, following
the repository's testing and validation rules. At a meaningful completion point,
request Inquisition on the changes:

> Implement feature X, then use Inquisition on the complete changes.

Inquisition works in two phases with one coordinating editor. First, four fresh
reviewers look for reuse, simplification, efficiency, and fix-depth issues, and
the coordinator applies the behavior-preserving cleanups. Then it reviews the
cleaned-up result for bugs at a review level, `low`, `medium`, `high`, `xhigh`,
or `max`: the one you name, otherwise `high`, never the agent's effort. At
`low` the coordinator makes one pass over the diff itself. At `medium` and
`high`, one read-only reviewer subagent runs nine angles, including tests and
the cleanup angles again; at `xhigh` it adds language pitfalls and wrappers,
and a final gap sweep. The subagent keeps the coordinator's context small and
the review independent. Only `max` starts a parallel finder per angle, a fresh
verifier for every candidate, and a sweep agent; name a level, such as max,
for a deeper review than the default. The coordinator then fixes the supported
defects. Reviewers and verifiers run on a full-capability model and inherit
the session's reasoning effort.

It handles commits, revision ranges, branch changes, paths, or uncommitted work.
A bare invocation selects the current branch's changes since its merge base with
the remote default branch, together with staged, unstaged, and untracked changes.
Ask for review-only to receive findings without edits. Fixes stay within the
requested behavior; commits, pushes, and publication require the user's
authorization.

There is no separate implementation skill. Inquisition requires a failing regression
test for a testable bug it fixes, without imposing TDD on every feature or
refactor. It reports incomplete coverage or a single-pass review when the host
cannot run subagents.

Use `$skill-name` in Codex or `/skill-name` in Cursor and Claude Code. Codex
invocation policy disables implicit activation, and every description limits its
skill to explicit requests. No skill sets `disable-model-invocation`, so in
Cursor and Claude Code a request in words ("start the inquisition") also loads
it.
Repository rules govern ordinary development even when no skill is invoked.
Reading a skill for review does not invoke it.

## Image prompting

The prompting skills are reconstructed from the model maker's own documentation and code.
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

The Z-Image linter works the same way with Z-Image-Turbo's own tokenizer files (Qwen3), fetched
with `python3 skills/z-image-prompt/scripts/lint_prompt.py --fetch-tokenizer` into
`~/.cache/z-image-prompt/tokenizer` (`ZIMAGE_TOKENIZER_DIR` overrides it).

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
`png_config.py` reads the settings and prompt out of any Draw Things PNG, the app's own exports
included, and prints the command that reproduces the image.

## Token audit

The `token-audit` skill reads Claude Code's transcripts in `~/.claude/projects` and reports
where tokens go: spend by source, session, agent type and context size, review runs,
compactions and the files re-read after them, a replay of the compaction threshold, and
spend per commit, per closed issue or per ticket touched, optionally for one author. Its
script is standard-library Python 3.8+. Reports, agent prefix probes and a log of
configuration changes are saved in `~/.claude/token-audit/`, outside any repository, because
they contain session titles and paths.

## Memory audit

The `claude-memory-audit` skill checks Claude Code's memories: every project store under
`~/.claude/projects/*/memory/`, plus a global store when `~/.claude/CLAUDE.md` or a file it
imports points to one. It moves memories to the right store, merges duplicates, removes
obsolete facts after one direct check, fixes weak index lines and broken links, and deletes the
memory folders of working folders that no longer exist. It edits only memory files and their
`MEMORY.md` indexes and reports anything else as a proposal. Schedule it as a daily local task
in the Claude desktop app with the prompt "Run Claude Memory Audit"; most days it reports no
changes. It works only in Claude Code, so install it for Claude Code alone (see Install).

## Install

Install from the published GitHub repository for local Cursor, Codex, and Claude:

```bash
npx skills@latest add domoarigatomrburato/agent-skills -g --skill grilling domain-modeling inquisition ideogram-prompt krea-prompt z-image-prompt drawthings token-audit --agent universal claude-code -y
```

The memory audit works only in Claude Code, so it is installed for Claude Code alone:

```bash
npx skills@latest add domoarigatomrburato/agent-skills -g --skill claude-memory-audit --agent claude-code -y
```

On a machine that needs only the token audit:

```bash
npx skills@latest add domoarigatomrburato/agent-skills -g --skill token-audit --agent universal claude-code -y
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
