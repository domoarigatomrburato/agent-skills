# Agent Skills

Personal, portable agent skills.

## Skills

- `simplify` - Simplify existing code while preserving exact behavior, using a
  fresh independent agent pass when supported, with a bias toward removing
  leftover shims, duplicate sources of truth, and unnecessary wrappers.

## Install

Install all skills globally:

```bash
npx skills add domoarigatomrburato/agent-skills -g --all
```

Install only `simplify`:

```bash
npx skills add domoarigatomrburato/agent-skills -g --skill simplify -y
```

Install from a local checkout while developing:

```bash
npx skills add ./agent-skills -g --skill simplify --copy -y
```
