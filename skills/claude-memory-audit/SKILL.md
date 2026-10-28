---
name: claude-memory-audit
description: Audit Claude Code's memory files for scope, duplicates, obsolete facts, weak wording, and index integrity, fix the real defects, and report what changed. Built to run unattended as a daily local scheduled task. Claude Code only. Use only when the user explicitly requests Claude Memory Audit.
compatibility: Claude Code only. Reads and edits the memory files under ~/.claude, so it needs a local session; a cloud session cannot see them.
---

# Claude Memory Audit

Keep Claude Code's memories accurate, in the right store, and useful to a
future session. The audit usually runs unattended as a scheduled task: ask
nothing, decide, act, and report.

Most days nothing needs to change, and "no changes needed" is a correct
result. Never change a memory for its own sake, and never reword one for style
alone.

## Find the stores

- **Project stores:** every `~/.claude/projects/*/memory/` directory, Claude
  Code's standard per-project auto-memory. Each holds one file per memory and
  a `MEMORY.md` index.
- **Global store (optional):** Claude Code has no standard global memory
  store. Audit one only when the user's `~/.claude/CLAUDE.md`, or a file it
  imports with `@path`, points to a memory directory or its index. Without
  such a pointer there is no global store: audit project stores only, and
  never create one.

A memory file has YAML frontmatter with `name`, `description`, and
`metadata.type` (`user`, `feedback`, `project`, or `reference`), then the
fact. Each store's `MEMORY.md` has one line per memory file:
`- [Title](file.md) — hook`. `[[name]]` in a body links to the memory whose
`name` is `name`, in either store.

## Check every memory

1. **Scope.** Ask: would this still be true and useful in a different
   repository?
   - Yes: it belongs in the global store, when there is one; otherwise leave
     it where it is.
   - No: it belongs in the store of the project it is about.
   - Mixed: split it, the general part global and the project part in the
     project store, and link the two halves with `[[name]]`.
2. **Duplicates.** Two memories stating the same fact, or a memory restating
   what a `CLAUDE.md`, an `AGENTS.md`, a rule file, or the code already says:
   merge the two memories, or delete the one that only restates.
3. **Obsolescence.** Fixed bugs, finished migrations, bumped version pins,
   and files, flags, or commands that no longer exist. Before acting, verify
   with one cheap, direct check, such as `ls`, `grep`, `git log`, or
   `<tool> --version`. A date alone does not make a memory stale. When you
   cannot verify, leave the memory and report it.
4. **Effectiveness.** The index line alone must tell a future session when
   the memory matters. `feedback` and `project` memories carry a `**Why:**`
   and a `**How to apply:**` line. Fix only real defects: a vague or
   misleading hook, a missing why, a relative date (make it absolute from the
   file's history or context; leave it if you cannot), a contradiction
   between memories, or a bloated body.
5. **Index integrity.** One `MEMORY.md` line per memory file, no line
   pointing to a missing file, valid frontmatter (`name`, `description`,
   `metadata.type`), and every `[[name]]` link resolving to a memory.

## Orphaned project stores

A `~/.claude/projects/<encoded-path>/` directory whose working folder no
longer exists, such as a removed scratch workspace or worktree, is orphaned.
The directory name is the folder's absolute path with `/` and other
non-alphanumeric characters replaced by `-`. Decode it by checking which
existing path it matches; when the name cannot be decoded unambiguously, leave
the directory and report it.

For an orphaned store, move each memory that is still useful elsewhere to the
global store, when there is one, and delete the rest of the memory directory.

## Limits

- Edit only memory files and their `MEMORY.md` indexes. Never edit
  `CLAUDE.md`, `AGENTS.md`, rule files, or repositories: propose such changes
  in the report.
- Keep verification light: one direct check per doubt, no builds, test runs,
  or network calls beyond what the check needs.
- If a memory stores a token, password, or other secret, remove the value,
  report which memory held it, and never repeat the value anywhere.

## Report

When nothing changed, report exactly one line:

```text
Memory audit: no changes needed.
```

Otherwise report, per store, a short list of the changes with the evidence for
each (the check you ran and what it showed). Then list the items you could not
verify, and the changes you propose outside the memory files.
