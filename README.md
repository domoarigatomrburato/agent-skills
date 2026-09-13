# Agent Skills

Three personal workflows, invoked explicitly. Their instructions are maintained
here; no other skill collection is required.

| Skill | Purpose |
|---|---|
| `grilling` | Challenge a plan through focused, consequential questions. |
| `domain-modeling` | Clarify domain concepts and record concise, durable decisions. |
| `inquisition` | Independently review correctness, test evidence, and design; fix supported issues. |

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

## Install

Install from the published GitHub repository for local Cursor, Codex, and Claude:

```bash
npx skills@latest add domoarigatomrburato/agent-skills -g --skill grilling domain-modeling inquisition --agent universal claude-code -y
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

The `.claude-plugin/plugin.json` manifest groups the skills under
`DomoArigatoMrBurato-skills` in compatible hosts.
