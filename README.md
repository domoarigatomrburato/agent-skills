# Agent Skills

Personal agent skills.

This repo declares a `.claude-plugin/plugin.json` manifest so compatible Skills
CLI views can group the installed skills under `DomoArigatoMrBurato Skills`.

## Skills

- `agent-council` - Chair a harness-agnostic, read-only council of subagents
  with preflight, profiles, durable transcript, and a traceable `final.md`.
- `inquisition` - Run an isolated three-pass codebase audit (architecture,
  compliance, judge synthesis) and deliver a severity-ranked remediation
  report with cross-referenced findings.
- `simplify` - Simplify existing code while preserving exact behavior, using a
  fresh independent agent pass when supported, with a bias toward removing
  leftover shims, duplicate sources of truth, and unnecessary wrappers.
- `santommaso` - Deliberately prove behavior with vertical-slice TDD, or
  characterize existing behavior, then require a fresh adversarial review that
  challenges correctness before simplifying.

## Install

Install all skills for Universal + Claude Code:

```bash
npx skills add domoarigatomrburato/agent-skills -g --skill '*' --agent universal claude-code -y
```

Install only `agent-council` for Universal + Claude Code:

```bash
npx skills add domoarigatomrburato/agent-skills -g --skill agent-council --agent universal claude-code -y
```

Install only `inquisition`:

```bash
npx skills add domoarigatomrburato/agent-skills -g --skill inquisition --agent universal claude-code -y
```

Install only `simplify`:

```bash
npx skills add domoarigatomrburato/agent-skills -g --skill simplify --agent universal claude-code -y
```

Install only `santommaso`:

```bash
npx skills add domoarigatomrburato/agent-skills -g --skill santommaso --agent universal claude-code -y
```

Install from a local checkout while developing:

```bash
npx skills add . -g --skill agent-council --agent universal claude-code --copy -y
```

List skills without installing:

```bash
npx skills add . --list
```

Remove a globally installed skill:

```bash
npx skills remove -g --skill agent-council -y
```
