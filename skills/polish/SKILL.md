---
name: polish
description: Polish changed code through parallel reviews for reuse, clarity, correctness, and efficiency, then apply only behavior-identical improvements and run one final verification. Use when the user asks to polish, simplify, de-cruft, refine, clean up, or perform a final quality pass on existing or recently changed code.
---

# Polish

Refine code without changing its behavior. Preserve features, public API,
side effects, ordering, concurrency semantics, defaults, error behavior,
persistence formats, and user-visible output exactly.

## Scope

- Use the area named by the user. Otherwise use all current working-tree
  changes—staged, unstaged, and untracked—including directly affected callers
  and callees.
- Give all reviewers the same complete scope and relevant diff.
- If that scope cannot be inspected exhaustively in one pass, ask the user to
  narrow it rather than sampling it.
- If no meaningful code change anchors the pass, ask the user to choose a
  target instead of selecting a broad area silently.
- Treat documentation-only, comment-only, formatting-only, changelog, and
  version-bump changes as out of scope unless the user includes them.
- Preserve unrelated working-tree changes and existing repository state.

## Roles

The invoking agent is the **final reviewer and editor**. It owns scope,
synthesis, all file changes, and final verification.

Spawn exactly three fresh agents in parallel as read-only **reviewers**. An
explicit invocation of this skill grants permission to spawn them. Reviewers
must inspect the code and report findings; they must not edit files, run
validation or formatters, or mutate repository state. Do not reuse agents
carrying task history.

If the host cannot run three independent agents, state that `polish` cannot be
applied in its required form and stop.

## Review Lenses

Assign one lens to each reviewer. Each reviewer must inspect every changed area
in scope and return only high-confidence findings with the affected location,
the concrete issue, the proposed improvement, and why behavior remains
identical. End with a compact coverage note naming every inspected area and any
area that could not be inspected fully. A clean report is valid; incomplete
coverage is not.

### 1. Reuse and reduction

Look for:

- existing language, standard-library, framework, or project facilities that
  replace hand-rolled code
- duplicated logic, literals, calculations, validators, parsers, refreshes,
  effects, subscriptions, or sources of truth
- redundant wrappers, pass-through layers, one-use helpers, unnecessary
  temporaries, mirrored state, obsolete adapters, and demonstrably dead paths
- leftovers in adjacent callers and callees: old names, compatibility shims,
  defensive branches, and abstractions made unnecessary by the current change

Keep abstractions that name domain concepts, isolate side effects, improve
testability, or clarify ownership.

### 2. Clarity and design

Look for:

- vague names, obvious comments, parameter sprawl, stringly typed state, and
  representations that permit invalid combinations
- nested conditionals, callback pyramids, indirect control flow, and clever
  compression that obscures intent
- leaky or misleading abstractions, do-it-all components, split files that
  disguise mixed responsibilities, and ownership that is difficult to follow
- copy-paste structure and inconsistent patterns that a smaller, clearer
  design can express without widening the public surface

Prefer explicit readable control flow and the smallest abstraction that names
a real concept.

### 3. Correctness and efficiency

Look for:

- proposed cleanups that could alter mutation order, asynchronous ordering,
  defaults, nil handling, error semantics, side effects, public contracts,
  persistence, or output
- repeated or unnecessary work, recurring no-op updates, overly broad
  operations, avoidable hot-path allocation, and missed batching
- unsafe check-then-act patterns, resource lifetime mistakes, leaks, and
  unbounded data structures
- efficiency improvements that retain the same execution and concurrency
  semantics

Treat semantic risk as a veto, not a tradeoff.

## Workflow

1. Inspect repository status and establish the complete scope and diff. Record
   the starting file inventory and staging state, plus the observable behavior
   that must remain unchanged.
2. Dispatch all three reviewers in one parallel batch with the same scope,
   diff, behavior invariant, and their assigned lens. The batch is complete
   when all three reports account for every changed area.
3. Re-read the affected code and synthesize the reports. Deduplicate overlaps,
   reject false positives, and reject every proposal whose equivalence cannot
   be established from code, contracts, and existing tests.
4. As the sole editor, apply the remaining improvements in coherent edits.
   Favor deletion and directness over new layers. Report broader or
   behavior-sensitive opportunities instead of implementing them.
5. Review the resulting full diff once as a whole. Check semantic equivalence,
   sweep adjacent code for leftovers introduced or exposed by the edits, and
   compare against the starting inventory. Confirm that the polish changed only
   intentional files and preserved the original staging state.
6. Run one final verification stage after all editing is complete: use the
   smallest relevant existing tests, then the repository's applicable static,
   lint, type, or build checks. If it fails because of the polish edits, fix
   them and repeat this final stage until it passes.
7. Summarize meaningful changes, the final verification, clean reviewer
   reports, and intentionally skipped findings with residual risk.

## Guardrails

- Make fewer high-confidence changes when certainty is limited. Tests support
  equivalence; they do not replace reasoning about it.
- Keep execution order and concurrency behavior stable. Preserve reachable
  legacy behavior unless the user separately authorizes changing it.
- Avoid compatibility layers, suppressions, baselines, broad defensive
  branches, and speculative abstractions as cleanup devices.
- Do not commit, push, open pull requests, or perform destructive repository
  operations unless the user explicitly asks.
