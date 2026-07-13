---
name: santommaso
description: Santommaso deliberate red-green plus fresh adversarial review. Use only when the user explicitly asks for Santommaso or their usual Santommaso mode.
---

# Santommaso

## Purpose

Prove behavior, then doubt implementation.

Use this self-contained workflow for deliberate, high-confidence code changes.
It combines vertical red-green slices with a fresh adversarial review. Do not
rely on separate `tdd`, `simplify`, or similarly named skills being installed.

## Choose Mode And Authority

- **Behavior Change Mode**: add or change behavior, or fix a bug.
- **Existing Code Mode**: preserve behavior while reviewing or simplifying
  existing code or an active diff.

Also identify the user's authority:

- **Review-only**: inspect and report; make no changes.
- **Implementation-authorized**: implement the requested behavior and directly
  related high-confidence cleanup within its ownership boundary.
- **Cleanup-authorized**: apply high-confidence behavior-preserving changes.

Before editing, state the mode, authority, public surface in scope, and behavior
that must change or remain unchanged. If Existing Code Mode has no meaningful
change and no named target, offer a few concrete focus areas instead of
choosing silently.

## Hard Rules

- Follow local project instructions first, including contribution docs, nearby
  package docs, validation guidance, and commit/push rules.
- Commit, push, open PRs, and destructive git operations require explicit user
  authority.
- Preserve exact behavior outside the requested change: public API, side
  effects, ordering, defaults, error semantics, persistence format, and
  user-visible output.
- Verify behavior through public interfaces or user-observable surfaces.
- Keep relevant tests green during cleanup.
- Prefer the smallest complete change within the requested behavior, active
  diff, named files, or one tightly related ownership boundary.
- Add no compatibility shims, broad defensive branches, suppressions,
  baselines, wrapper layers, or obsolete legacy paths merely to reduce apparent
  risk.
- Preserve obsolete invalid states only when a documented migration requires
  them.
- Report a simplification instead of applying it when behavior preservation is
  uncertain.

## Behavior Change Mode

Work in vertical red-green slices: one behavior, one failing test, one minimal
implementation.

1. Read the local instructions and domain docs governing the touched area.
   Continue when the relevant rules and validation expectations are known.
2. State the smallest meaningful tracer-bullet behavior through a public or
   user-observable surface. Continue when the next slice is one behavior.
3. Write one failing test and run the narrowest command that proves it is red
   for the expected reason. When automation is genuinely unavailable, record
   the reason and manual verification before implementation.
4. Implement the smallest useful change that makes the same command green.
   Continue when the requested behavior passes without speculative additions.
5. Repeat steps 2-4 until every requested behavior has automated evidence or a
   recorded manual verification.
6. While green, make only local cleanup needed to keep the slices readable.
   Leave broader simplification to the independent pass.
7. Run the independent adversarial pass and integrate only authorized,
   high-confidence findings. Continue when correctness challenges are resolved
   and accepted edits are green.
8. Run scope-appropriate validation and all additional local checks required
   before handoff, commit, push, or release.

## Existing Code Mode

Preserve behavior; do not manufacture artificial red tests.

1. Read governing instructions and domain docs, then inspect `git status`, the
   relevant diff, and the named code area. Continue when the review boundary
   and existing changes are known.
2. State the invariants: public contracts, side effects, persistence, async
   ordering, nil/error handling, and defaults. Continue when they cover the
   changed area.
3. Evaluate existing coverage. In review-only work, report coverage gaps
   without editing tests. In cleanup-authorized work, add characterization
   tests only for risky, under-covered behavior observable through a public
   surface.
4. Run the independent adversarial pass with the same authority as the main
   task. Integrate only authorized, high-confidence behavior-preserving edits.
5. Re-read the diff for semantic drift and perform the leftover sweep.
6. Run scope-appropriate validation and all additional local checks required
   before handoff, commit, push, or release.

## Test Standards

Good tests describe observable behavior and survive internal refactors. Prefer
integration-style tests when practical; use unit tests when the public
interface is already narrow and meaningful.

Reject tests coupled to private methods, incidental call order, unnecessary
internal mocks, or expected values recomputed by the implementation's own
logic. Mock system boundaries such as remote APIs, time, randomness, or the
filesystem rather than internal collaborators.

## Independent Adversarial Pass

The independent pass is mandatory whenever Santommaso is explicitly invoked.
It challenges correctness before seeking simplification.

When the host supports independent agents, spawn a fresh reviewer using the
host's default available configuration. Never reuse an implementation agent or
an agent with task history. Explicit Santommaso invocation authorizes this
reviewer, but its edit authority remains identical to the user's request.

If no independent mechanism is available, state that Santommaso cannot be
fully applied before starting a local-only fallback. A spawned reviewer reviews
directly and never spawns another reviewer. Treat an explicit user or host ban
on delegation like an unavailable mechanism and report the partial application.

Before delegating:

1. Read [the adversarial review reference](references/adversarial-review.md).
2. Select the comparison base deliberately: use `HEAD` for uncommitted work;
   use the actual branch base, merge base, tag, or release commit when reviewing
   committed work. Draft the reviewer packet with that explicit revision:

   ```text
   python3 <skill-dir>/scripts/reviewer_packet.py --base <revision> [--scope path ...]
   ```

3. Replace every `TODO`; delegation is blocked while any remain. Prefer paths,
   commands, constraints, and an exact diff command over a pasted diff. Use
   `--include-diff` only when the reviewer cannot inspect the workspace.

The packet must identify scope, authority, original request/spec and governing
docs, changed files, behavior contract, local constraints, diff command or
summary, validation already run, known risks, and the desired output contract.

Delegate with this role in the prompt:

```text
Your role is the fresh independent reviewer for a Santommaso adversarial pass.
Use the packet for orientation, then verify it against the original request,
specification, and governing docs named in the packet.
Challenge correctness and test coverage before considering simplification.
Respect the packet's authority and ownership boundary.
Do not apply Santommaso recursively and do not spawn another agent.
```

The pass is complete when the reviewer has reported prioritized correctness
findings or explicitly found none, returned one packet-defined cleanup outcome,
accepted edits have been revalidated, and skipped opportunities record their
behavior risk.

## Validation

Run the smallest validation that proves the changed behavior and preserves
confidence. Demonstrate red before green in Behavior Change Mode when
practical. For pure refactors, existing focused tests are often sufficient.
Follow all additional project-defined gates and report skipped checks with
their reason.

## Reporting

Report only behavior changed or preserved, tests added or used, meaningful
simplifications, leftover searches, validation, the independent reviewer's
finding, and skipped risky opportunities. Keep the report proportional to the
work.
