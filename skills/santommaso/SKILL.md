---
name: santommaso
description: Santommaso red-green plus independent simplify pass. Use for requested santommaso/usual mode, behavior changes, bug fixes needing public-behavior tests, and behavior-preserving cleanup of existing code or active diffs. Requires a fresh independent simplify reviewer when subagents exist.
---

# Santommaso

## Purpose

Prove behavior, then doubt implementation.

Use this self-contained workflow to change code through vertical red-green
slices, then simplify only what can be proven behavior-preserving. Do not rely
on separate `tdd`, `simplify`, or similarly named skills being installed.

## Mode Choice

- **Behavior Change Mode**: use when adding behavior, changing behavior, or
  fixing a bug.
- **Existing Code Mode**: use when the behavior already exists and the user
  asks to simplify, clean up, de-cruft, review, or refine an implementation or
  active diff.

Before editing, name the mode, the public surface in scope, and the behavior
that must either change or remain unchanged. If Existing Code Mode has no
meaningful code change and the user named no target, offer a few concrete focus
areas instead of choosing silently.

## Hard Rules

- Follow local project instructions first, including contribution docs, nearby
  package docs, validation guidance, and commit/push rules.
- Do not commit, push, open PRs, or run destructive git operations unless the
  user explicitly asks.
- Preserve exact behavior outside the requested change: features, public API,
  side effects, ordering, defaults, error semantics, persistence format, and
  user-visible output.
- Verify behavior through public interfaces or user-observable surfaces, not
  private methods or incidental implementation shape.
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

## Behavior Change Mode

Work in vertical red-green slices. Do not write all tests first and then all
implementation.

1. Read the local instructions and the domain docs that govern the touched
   area. Continue only after the relevant local rules and validation
   expectations are known.
2. Identify the smallest meaningful tracer-bullet behavior through a public
   interface or user-observable surface. Continue only when the next slice can
   be stated as one behavior.
3. Write one failing test for that behavior and run the narrowest command that
   demonstrates the failure. Continue only when the test is red for the
   expected reason, or when the behavior is not automatable and the manual
   verification reason is recorded before implementation.
4. Implement the smallest useful change that makes that test pass. Continue
   only when the same narrow command is green and no speculative behavior has
   been added.
5. Repeat steps 2-4 for each remaining behavior. Continue only when every
   requested behavior has automated evidence or documented manual verification.
6. Refactor while green when the new code reveals duplication, unclear names,
   poor boundaries, or a deeper module opportunity. Continue only after the
   relevant tests still pass.
7. Run the independent simplify pass, integrate only high-confidence findings,
   then perform the leftover sweep.
8. Run scope-appropriate validation and any additional local checks required
   before handoff, commit, push, or release.

## Existing Code Mode

Use Existing Code Mode to preserve behavior while simplifying or reviewing
code. Do not force artificial failing tests.

1. Read the local instructions and the domain docs that govern the touched
   area, then inspect `git status`, the relevant diff, and any code area the
   user named. Continue only when the review boundary and current changes are
   known.
2. Identify the behavior that must remain unchanged, including public
   contracts, side effects, persistence format, async ordering, nil/error
   handling, and defaults. Continue only when those invariants cover the
   changed area.
3. Check whether existing tests cover those invariants. Add characterization
   tests only when the behavior is risky, under-covered, and testable through a
   public interface. Continue only when the coverage decision is explicit.
4. Run the independent simplify pass and integrate only high-confidence
   behavior-preserving findings.
5. Re-read the diff for semantic drift, then perform the leftover sweep.
6. Run scope-appropriate validation and any additional local checks required
   before handoff, commit, push, or release.

## Test Standards

Good tests describe what the system does. They exercise real code paths through
public APIs or user-observable surfaces and should survive internal refactors.

Bad tests describe implementation shape: unnecessary internal mocks, private
method assertions, incidental call order, or state checks that bypass the
product surface. If a test fails when behavior is unchanged, it was probably
testing the wrong thing.

Prefer integration-style tests when practical. Use smaller unit tests when the
public interface is already narrow and the behavior is meaningful at that
level.

## Independent Simplify Pass

The simplify pass is mandatory in both modes.

When you are the main agent applying Santommaso and the host supports
subagents, delegated agents, or independent reviewer agents, spawn a fresh
independent reviewer with the host's default available agent configuration.
Treat explicit Santommaso invocation as permission to spawn that reviewer for
this pass. Do not specify or force a custom agent name, agent type, model
label, or role identifier; put the role only in the task prompt. Do not reuse
an agent with prior task history.

If no independent agent mechanism is available, say that Santommaso cannot be
fully applied in its required form before doing any local-only fallback.

When you are the spawned reviewer, do not spawn another agent. Review and
simplify directly within the assigned scope.

Before delegating, build a compact reviewer packet. Prefer file paths,
commands, constraints, and an exact diff command over pasted diffs when the
reviewer can inspect the workspace. Use the bundled helper to draft the
git-derived fields:

```text
python3 <skill-dir>/scripts/reviewer_packet.py [--base HEAD] [--scope path ...]
```

Use `--include-diff` only when the reviewer cannot inspect the workspace
directly.

The packet must include:

- scope
- changed files
- behavior that must be preserved
- local constraints and validation expectations
- diff summary or exact diff command
- tests or commands already run
- known risk areas
- desired reviewer output contract

Delegate with the role in the prompt text:

```text
Your role for this task is the fresh independent reviewer for a Santommaso simplify pass.
Use the reviewer packet as the source of truth.
Do not apply Santommaso recursively.
Do not spawn another agent; review and simplify directly within the assigned scope.
```

Ask the reviewer to apply high-confidence behavior-preserving cleanup within
the assigned scope, or report that no safe cleanup exists. The simplify pass is
complete only after the reviewer returns one of those outcomes, any accepted
edits are revalidated, and skipped opportunities are recorded with their risk.

## Simplify And Sweep Checklist

Prefer fewer high-confidence changes over broad speculative cleanup. Search the
changed area and directly adjacent callers/callees for:

- semantic drift in mutation order, async ordering, defaults, nil/error
  handling, persistence, and public contracts
- compatibility shims, obsolete adapters, leftover legacy paths, and
  unnecessary defensive branches
- duplicate sources of truth, duplicate validators/parsers, duplicated labels,
  repeated calculations, subscriptions, refreshes, effects, and state mirrors
- redundant wrappers, pass-through components, useless subcomponents,
  one-use helpers, and abstractions that hide rather than clarify
- custom code that the language, framework, standard library, or project
  utilities already solve cleanly
- over-nested conditionals, nested ternaries, callback pyramids, vague names,
  unnecessary temporaries, and obvious comments
- stale concept names, literals, comments, and split files or extensions left
  behind by the current change

Keep abstractions that name real domain concepts, isolate side effects,
simplify testing, or clarify ownership. Apply small follow-on edits within the
same ownership boundary or directly adjacent call sites. Report opportunities
that cross a larger architectural boundary, change public behavior, require a
broad migration, or are not clearly covered by tests.

## Validation

Run the smallest validation that proves the changed behavior and preserves
confidence.

- In Behavior Change Mode, demonstrate the red failure before the green pass
  when practical.
- In Existing Code Mode, existing tests passing is often enough for pure
  refactors unless the touched behavior is risky or under-covered.
- Follow local project instructions for any additional checks required before
  handoff, commit, push, or release.
- Do not invent repo-wide validation where the project does not define it.
- If automated coverage is missing, say what was checked manually and where
  residual risk remains.

## Reporting

Report only the useful facts:

- behavior added, changed, fixed, or preserved
- tests added or used as characterization
- meaningful simplifications integrated
- leftover searches performed
- validation run
- independent reviewer's final finding
- skipped risky opportunities, if any

Keep the report proportional to the work. Do not narrate every internal step.
