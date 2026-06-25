# Agent Skills

Personal, portable agent skills.

This repo declares a `.claude-plugin/plugin.json` manifest so compatible Skills
CLI views can group the installed skills under `DomoArigatoMrBurato Skills`.

## Skills

- `agents-roundtable` - Coordinate multiple headless coding or research agents
  through a disk blackboard, recover failed or dirty turns, and produce a
  traceable `final.md`.
- `simplify` - Simplify existing code while preserving exact behavior, using a
  fresh independent agent pass when supported, with a bias toward removing
  leftover shims, duplicate sources of truth, and unnecessary wrappers.
- `santommaso` - Prove behavior with vertical-slice TDD, or characterize
  existing behavior for cleanup work, then require a fresh independent simplify
  pass when supported.

## Install

Install all skills globally:

```bash
npx skills add domoarigatomrburato/agent-skills -g --all
```

Install only `agents-roundtable`:

```bash
npx skills add domoarigatomrburato/agent-skills -g --skill agents-roundtable --agent codex cursor gemini-cli
```

Install only `simplify`:

```bash
npx skills add domoarigatomrburato/agent-skills -g --skill simplify -y
```

Install only `santommaso`:

```bash
npx skills add domoarigatomrburato/agent-skills -g --skill santommaso -y
```

Install from a local checkout while developing:

```bash
npx skills add ./agent-skills -g --skill santommaso --copy -y
```
