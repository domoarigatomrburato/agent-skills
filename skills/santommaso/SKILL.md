---
name: santommaso
description: Self-contained test-first and simplify workflow. Use when the user asks for santommaso, usual mode, TDD plus simplify, careful behavior-changing work, bug fixes with tests, or existing-code cleanup that must preserve behavior. Requires a fresh independent simplify agent when the host supports agents.
---

# Santommaso

## Purpose

Prove the behavior, then doubt the implementation.

Use this skill to make changes with evidence and restraint: add or change
behavior through vertical test-driven slices, then run a behavior-preserving
simplification pass with a fresh independent agent when the host supports one.

This skill is self-contained. Do not rely on separate `tdd`, `simplify`, or
similarly named skills being installed.

## Entry Modes

Choose the mode from the user's request and the current worktree.

### Behavior Change Mode

Use this mode when adding behavior, changing behavior, or fixing a bug.

Work in vertical slices:

1. Write one public-behavior test that fails for the next desired behavior.
2. Implement the smallest useful change that makes it pass.
3. Repeat for the next behavior.
4. Refactor only while tests are green.
5. Run the independent simplify pass.

### Existing Code Mode

Use this mode when the behavior already exists and the user asks to simplify,
clean up, de-cruft, review, or refine an implementation or active diff.

Do not force artificial failing tests. Instead:

1. Inspect `git status`, the relevant diff, and any code area the user named.
2. Identify the behavior, public contracts, side effects, and ordering that
   must remain unchanged.
3. Use existing tests as the baseline when they cover the behavior.
4. Add characterization tests only when the behavior is risky, under-covered,
   and testable through a public interface.
5. Run the independent simplify pass.

## Hard Invariants

- Follow local project instructions first, including contribution docs, nearby
  package docs, validation guidance, and commit/push rules.
- Do not commit, push, open PRs, or run destructive git operations unless the
  user explicitly asks.
- Preserve exact behavior outside the requested change: features, public API,
  side effects, ordering, defaults, error semantics, persistence format, and
  user-visible output.
- Tests must verify behavior through public interfaces, not implementation
  details.
- Refactor only while the relevant tests are green.
- Do not add compatibility shims, broad defensive branches, suppressions,
  baselines, wrapper layers, or obsolete legacy paths to make progress look
  safe.
- Do not preserve obsolete invalid states unless there is a documented
  migration requirement.
- If a simplification might change behavior, skip it and report the
  opportunity instead.
- Keep the work focused on the requested behavior, active diff, named files, or
  one tightly related ownership boundary.

## TDD Philosophy

Good tests describe what the system does. They exercise real code paths through
public APIs or user-observable surfaces. They should survive internal refactors
because they do not care how the result is implemented.

Bad tests describe the shape of an implementation. They mock internal
collaborators unnecessarily, test private methods, assert incidental call
order, or verify state by bypassing the interface the product actually exposes.
If a test fails when behavior is unchanged, it was probably testing the wrong
thing.

Prefer integration-style tests when practical. Use smaller unit tests when the
public interface is already narrow and the behavior is meaningful at that
level.

## Anti-Pattern: Horizontal Slices

Do not write all tests first and then all implementation.

That is horizontal slicing. It tends to produce tests for imagined behavior,
locks in premature API shape, and outruns what the implementation is teaching
you.

Use vertical slices instead:

```text
RED:   write one failing behavior test
GREEN: implement enough to pass it
REPEAT: choose the next behavior from what you learned
```

Each test should confirm one behavior. Each implementation step should make
that test pass without speculating far beyond it.

## Behavior Change Workflow

1. Read the local instructions and the domain docs that govern the touched
   area.
2. Identify the public interface or user-observable behavior that should
   change.
3. Choose the smallest meaningful tracer-bullet behavior.
4. Write one failing test for that behavior.
5. Run the narrowest command that demonstrates the failure.
6. Implement the smallest useful change that makes the test pass.
7. Run the narrowest command that demonstrates the pass.
8. Repeat for the next behavior only after the previous slice is green.
9. Refactor while green when the new code reveals duplication, unclear names,
   poor boundaries, or a deeper module opportunity.
10. Run the independent simplify pass.
11. Integrate only high-confidence findings.
12. Run scope-appropriate validation and follow any additional local
    instructions required before handoff, commit, push, or release.

## Existing Code Workflow

1. Read the local instructions and the domain docs that govern the touched
   area.
2. Inspect `git status` and the relevant diff before editing.
3. If there is no meaningful code change and the user did not name a target,
   offer a few concrete focus areas rather than choosing silently.
4. Identify behavior that must remain unchanged, including side effects,
   persistence format, async ordering, nil/error handling, and public
   contracts.
5. Check whether existing tests cover that behavior.
6. Add characterization tests only when they reduce real risk and can be
   expressed through a public interface.
7. Run the independent simplify pass.
8. Integrate only high-confidence behavior-preserving findings.
9. Re-read the diff for semantic drift.
10. Run scope-appropriate validation and follow any additional local
    instructions required before handoff, commit, push, or release.

## Independent Simplify Pass

The simplify pass is mandatory in both entry modes.

When you are the main agent applying Santommaso and the host supports
subagents, delegated agents, or independent reviewer agents, run the simplify
pass by spawning a fresh independent reviewer with the host's default available
agent configuration. Treat an explicit invocation of this skill as permission
to spawn that reviewer for this pass. Do not specify or force a custom agent
name, agent type, model label, or role identifier; put the role only in the
task prompt. Do not reuse an agent with prior task history.

Default to a fresh reviewer that receives only a compact reviewer packet, not
the full parent conversation. Use any context-fork or thread-inheritance option
only when earlier user decisions or requirements cannot be reconstructed
compactly. Even then, include the reviewer packet and tell the reviewer that the
packet is the source of truth; inherited context is only supporting material.

When you are the spawned reviewer, this requirement is already satisfied. Do
not try to spawn another agent. Your independence comes from being freshly
spawned for this pass, so review and simplify directly within the assigned
scope.

Before delegating, distill the current context into a reviewer packet. Keep it
brief and factual; avoid leaking your intended answer or prior conclusions
unless the reviewer needs them to understand the task. Prefer file paths,
commands, and constraints over broad narrative. When the reviewer can inspect
the workspace, pass changed files and the exact diff command instead of pasting
a large diff. Use the bundled helper to draft the git-derived fields:

```text
python3 <skill-dir>/scripts/reviewer_packet.py [--base HEAD] [--scope path ...]
```

Use `--include-diff` only when the reviewer cannot inspect the workspace
directly.

The packet should include:

- scope
- changed files
- behavior that must be preserved
- local constraints and validation expectations
- diff summary or exact diff command
- tests or commands already run
- known risk areas
- desired reviewer output contract

When delegating, put the role in the prompt text, not in tool metadata:

```text
Your role for this task is the fresh independent reviewer for a Santommaso simplify pass.
Use the reviewer packet as the source of truth.
Do not apply Santommaso recursively.
Do not spawn another agent; review and simplify directly within the assigned scope.
```

Ask the reviewer to either apply high-confidence behavior-preserving cleanup
within the assigned scope, or report that no safe cleanup exists. It should look
for:

- semantic drift in mutation order, async ordering, defaults, nil/error
  handling, persistence, and public contracts
- compatibility shims, obsolete adapters, leftover legacy paths, and defensive
  branches made unnecessary by the current change
- duplicate sources of truth, duplicate validators/parsers, duplicated labels,
  and repeated calculations
- redundant wrappers, pass-through components, useless subcomponents, and
  one-use helpers
- custom code that the language, framework, standard library, or project
  utilities already solve cleanly
- vague names, unnecessary temporaries, obvious comments, and abstractions that
  hide rather than clarify
- split files or extensions that only disguise a do-it-all object without
  improving ownership

If no independent agent mechanism is available, say that this skill cannot be
fully applied in its required form before doing any local-only fallback.

## What To Simplify

Prefer fewer high-confidence changes over broad speculative cleanup.

Look for incidental complexity, especially:

- redundant wrappers, pass-through components, useless subcomponents, and
  one-use helpers
- duplicated labels, derived values, calculations, refreshes, effects,
  subscriptions, and state mirrors
- over-nested conditionals, nested ternaries, callback pyramids, and
  hard-to-follow control flow
- stale names and concepts left behind by the current change
- unnecessary abstraction around a single call site
- repeated orchestration that can become a deeper module without widening the
  public surface

Keep abstractions that name real domain concepts, isolate side effects,
simplify testing, or clarify ownership.

## Leftover Sweep

Before declaring done, search the changed area and directly adjacent
callers/callees for leftovers related to the current change:

- old concept names
- duplicated literals
- duplicate validators or parsers
- obsolete adapters
- compatibility shims
- unnecessary defensive branches
- duplicate sources of truth
- one-use wrappers
- comments that describe code that no longer exists

Prefer small follow-on edits when they remove leftovers within the same
ownership boundary or directly adjacent call sites. Report, rather than edit,
opportunities that cross a larger architectural boundary, change public
behavior, require a broad migration, or are not clearly covered by tests.

## Validation

Run the smallest validation that proves the changed behavior and preserves
confidence.

- In Behavior Change Mode, demonstrate the red failure before the green pass
  when practical.
- In Existing Code Mode, existing tests passing is often enough for pure
  refactors, unless the touched behavior is risky or under-covered.
- Follow local project instructions for any additional checks required before
  handoff, commit, push, or release.
- Do not invent repo-wide validation where the project does not define it.
- If automated coverage is missing, say what was checked manually and where
  residual risk remains.

## Reporting

Summarize only the useful facts:

- behavior added, changed, fixed, or preserved
- tests added or used as characterization
- meaningful simplifications integrated
- leftover searches performed
- validation run
- independent agent's final finding
- skipped risky opportunities, if any

Keep the report proportional to the work. Do not narrate every internal step.
