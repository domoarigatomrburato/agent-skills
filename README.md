# Agent Skills

Four personal workflows, invoked explicitly. Their instructions are maintained
here; no other skill collection is required.

| Skill | Purpose |
|---|---|
| `grilling` | Challenge a plan through focused, consequential questions. |
| `domain-modeling` | Clarify domain concepts and record concise, durable decisions. |
| `polish` | Apply behavior-preserving improvements after three independent reviews. |
| `santommaso` | Make test-first changes or assess existing code, with a fresh adversarial review. |

Use `$skill-name` in Codex or `/skill-name` in Cursor and Claude Code. Codex
invocation policy and Cursor/Claude frontmatter disable implicit activation.
Repository rules continue to govern ordinary testing, documentation, and
validation without requiring one of these workflows. Reading a skill for review does not invoke it.

Polish and Santommaso retain their deliberate review overhead. Use them when you
want that workflow; ordinary edits do not require either. Spec writing, issue
creation, commits, and pushes follow the user's request, not a skill pipeline.

## Install

Install the working copy while developing:

```bash
npx skills@latest add . -g --skill grilling domain-modeling polish santommaso --agent universal claude-code -y
```

The CLI installs from the local checkout into the shared global skills directory
for Cursor and Codex, and links Claude Code to it. This covers local use;
remote agents need their own installation. Run the command again after editing
the source. Local-source installations do not need upstream updates from another
collection.

When replacing a remotely installed version with a local checkout, remove the
old named installations first, then run the local install command. Skills CLI
1.5.25 can retain the previous upstream tracking records when a local install
overwrites them; removing first prevents later updates from restoring the old
upstream version.

After changes have been published to this repository, install the published version:

```bash
npx skills@latest add domoarigatomrburato/agent-skills -g --skill grilling domain-modeling polish santommaso --agent universal claude-code -y
```

Inspect or remove named installations with `npx skills@latest list -g` and
`npx skills@latest remove <skill-name> -g -y`.

## Attribution

Grilling and Domain Modeling are locally maintained adaptations of Matt Pocock's
MIT-licensed [skills](https://github.com/mattpocock/skills), based on the installed
versions updated on 2026-08-21. Their folders preserve the upstream license.
They retain focused questioning, domain vocabulary, and ADR practices while
removing cross-skill dependencies and narrowing activation and scope.

The `.claude-plugin/plugin.json` manifest groups the skills under
`DomoArigatoMrBurato-skills` in compatible hosts.
