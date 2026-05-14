---
name: simplify
description: Simplify and refine existing code for clarity, consistency, and maintainability while preserving exact behavior. Use when the user asks to simplify, de-cruft, reduce complexity, remove cargo-cult code, clean up recently changed code, or run a behavior-preserving final cleanup pass. Requires a fresh independent agent pass when the host supports agents.
---

# Simplify

## Purpose

Make existing code easier to read, debug, and extend without changing what it
does.

## Scope

- Prefer recently modified code, staged or unstaged changes, the active branch
  diff, or the area the user names.
- If there is no meaningful code change to anchor on, offer a few concrete
  focus areas instead of silently choosing a broad target.
- Treat documentation-only, comment-only, whitespace-only, changelog, and
  version-bump diffs as trivial unless the user explicitly asks to simplify
  them.
- Keep the pass focused: one file, one module, or one tightly related change
  set by default.

## Hard Invariants

- Preserve exact behavior: features, public API, side effects, ordering,
  defaults, error semantics, persistence format, and user-visible output stay
  the same.
- Run this skill through a fresh independent agent when the host supports
  subagents, delegated agents, or independent reviewer agents. Treat an
  explicit invocation of this skill as permission to spawn that agent for the
  simplify pass. Do not reuse an existing agent with task history.
- If no independent agent mechanism is available, say that the skill cannot be
  fully applied in its required form before doing any local-only fallback.
- Follow local instructions first: read project agent instructions,
  contribution docs, nearby package docs, and linter/type-checker config when
  they apply.
- Do not commit, push, open PRs, or run destructive git operations unless the
  user explicitly asks.
- Do not add compatibility shims, broad defensive branches, suppressions,
  baselines, or wrapper layers to make a cleanup look safe.
- Do not preserve obsolete invalid states or legacy paths unless there is a
  documented migration requirement.
- If a simplification might change behavior, skip it and report the opportunity
  instead.

## Effectiveness Bias

Bias toward fewer high-confidence behavior-preserving changes. The best
simplify pass removes leftovers from the current change without widening into a
speculative refactor.

After the first cleanup pass, run a leftover sweep before declaring done:

- Search the changed area and directly adjacent callers/callees for old concept
  names, duplicated literals, duplicate validators/parsers, obsolete adapters,
  compatibility shims, defensive branches, duplicate sources of truth, and
  one-use wrappers made unnecessary by the current diff.
- Prefer small follow-on edits when they remove leftovers within the same
  ownership boundary or directly adjacent call sites.
- Report, rather than edit, opportunities that cross a larger architectural
  boundary, change public behavior, require a broad migration, or are not
  clearly covered by tests.

## What To Simplify

Look for incidental complexity, especially:

- redundant wrappers, pass-through components, useless subcomponents, and
  one-use helpers
- duplicated labels, derived values, calculations, refreshes, effects,
  subscriptions, and state mirrors
- custom code that the language, framework, standard library, or project
  utilities already solve cleanly
- over-nested conditionals, nested ternaries, callback pyramids, and
  hard-to-follow control flow
- vague names, unnecessary temporaries, obvious comments, and abstractions that
  hide rather than clarify
- split files or extensions that only disguise a do-it-all object without
  improving ownership

Keep abstractions that name real domain concepts, isolate side effects,
simplify testing, or clarify ownership.

## Workflow

1. Inspect `git status` and the relevant diff before editing.
2. Spawn a fresh independent agent for the simplify pass when the host supports
   it. Give it only the relevant files, diff, constraints, and validation
   expectations. Ask it to apply high-confidence behavior-preserving cleanup or
   report that no safe cleanup exists.
3. Read the local conventions that govern the touched files.
4. Identify behavior that must remain unchanged and any tests/checks that cover
   it.
5. Apply small, readable simplifications; prefer explicit control flow over
   clever compression.
6. Re-read the diff for semantic drift, especially mutation order, async
   ordering, defaults, nil/error handling, and public contracts.
7. Run targeted searches for leftovers related to the changed concept: old
   names, duplicated literals, duplicate validators/parsers, obsolete adapters,
   compatibility shims, defensive branches, and one-use wrappers.
8. Run the smallest relevant validation: targeted tests first, then
   lint/type/build checks as appropriate for the repo.
9. Summarize only meaningful simplifications, validation run, leftover searches
   performed, any intentionally skipped risky opportunities, and the independent
   agent's final finding.

## Style Preferences

- Choose clarity over fewer lines.
- Use framework/project idioms instead of hand-rolled equivalents.
- Inline shallow one-use helpers when the call site becomes clearer.
- Extract helpers only when they remove real duplication or name a meaningful
  concept.
- Prefer `if`/`else` or `switch` over nested ternaries.
- Remove obvious comments; keep comments that explain non-obvious constraints.

## Verification

For pure refactors, existing tests passing is usually enough. The independent
agent pass is mandatory when agent spawning is available; ask it to look for
semantic drift, leftovers, shims, unnecessary wrappers, duplicated sources of
truth, and risky cleanup opportunities it intentionally declines. If automated
coverage is missing, say what was checked manually and where residual risk
remains.
