# Adversarial Review Reference

Read this reference immediately before preparing the independent reviewer
packet. Review in this order: correctness, evidence, then simplification.

Treat the original user request, specification, and governing project docs as
primary sources. Use the implementer's packet for orientation and challenge
its behavior contract when it diverges from those sources.

## Challenge Correctness

Try to disprove that the change is safe and complete. Inspect the changed area
and directly adjacent callers and callees for:

- requested behavior that is only partially implemented
- regressions outside the requested behavior
- mutation, async, event, retry, or cleanup ordering drift
- altered defaults, nil handling, error semantics, persistence, or public API
- races, duplicated work, leaks, stale ownership, and unbounded fan-out
- assumptions that are undocumented or unsupported by code and domain docs
- compatibility paths, defensive fallbacks, or invalid states added without a
  current requirement

Report findings by severity with concrete evidence. Explicitly state when no
correctness issue is found.

## Challenge Evidence

Check that tests exercise observable behavior through an appropriate seam and
would fail without the intended change. Look for:

- tests that assert implementation shape rather than behavior
- tautological expectations derived from the same logic as production code
- mocked internal collaborators or incidental call-count/order assertions
- missing error, retry, lifecycle, or concurrency evidence relevant to the bug
- manual verification standing in for a practical automated test

Report missing or weak evidence before proposing cleanup.

## Simplify While Preserving Behavior

Only after the correctness and evidence challenges, look for:

- duplicate sources of truth, validators, parsers, labels, or calculations
- repeated subscriptions, refreshes, effects, state mirrors, or cleanup paths
- obsolete adapters, compatibility shims, legacy paths, and defensive branches
- redundant wrappers, pass-through layers, one-use helpers, and abstractions
  that hide rather than clarify
- custom code already solved idiomatically by the language, framework,
  standard library, or project utilities
- over-nested control flow, vague names, unnecessary temporaries, obvious
  comments, and stale concept names or literals

Keep abstractions that name domain concepts, isolate side effects, improve
testability, or clarify ownership. Apply changes only when the packet grants
cleanup authority and behavior preservation is high-confidence. Otherwise
report the opportunity and its risk.

## Reviewer Outcome

Keep the output contract emitted by `reviewer_packet.py` intact. The reviewer
must return correctness and evidence findings first, then exactly one cleanup
outcome. Any edit must include changed files, preservation reasoning, and
validation; any skipped opportunity must include its behavior risk or missing
coverage.
