# Agent instructions

This repository is public and MIT licensed. Every skill in it is installed as is on other
people's machines, so its content must hold anywhere.

## Content rules

- No machine-specific paths: never `/Users/<name>/...` or a path to one person's checkout.
  Refer to locations by their portable form (`~/.claude/projects`, `$XDG_CACHE_HOME`, a path
  relative to the skill folder).
- Cite official sources only: the model maker's own documentation, code and license-compatible
  files. A prompting skill keeps what it quotes in its `references` folder, and the README's
  Attribution section names each source with its license.
- Never write an API key or token into a skill, a reference, a test fixture or a log; skills
  read them from the environment (`IDEOGRAM_API_KEY`, `KREA_API_TOKEN`).

## Skill layout

Each skill is a folder under `skills/` with:

- `SKILL.md`, in uppercase, whose frontmatter `description` ends by limiting the skill to
  explicit requests ("Use only when the user explicitly requests ...");
- `agents/openai.yaml` with `policy: allow_implicit_invocation: false`;
- optional `references/`, `scripts/` (standard-library Python where possible) and `tests/`;
- a `LICENSE` file when the skill adapts someone else's licensed work.

When adding, renaming or removing a skill, update `.claude-plugin/plugin.json`, the README's
skill table and the install commands in the README's Install section in the same change.

## Checks

- After changing `skills/token-audit/scripts/` or its tests, run
  `cd skills/token-audit && python3 -m unittest discover -s tests`.
- After changing `skills/drawthings/scripts/` or its tests, run
  `cd skills/drawthings && ~/.cache/drawthings-skill/venv/bin/python -m unittest discover -s tests`;
  the tests need the skill's virtualenv, created once with `bash scripts/setup.sh`.
- After changing a linter or validator in another skill, run it on one of the skill's own
  examples.
- Before a commit, check that no machine-specific path slipped in:
  `grep -rn '/Users/' skills README.md` must print nothing.

## Publishing

Installed copies are refreshed from GitHub: commit and push the change, then rerun the README's
install command. Never edit an installed copy (`~/.agents/skills`, `~/.claude/skills`): the next
install overwrites it.
