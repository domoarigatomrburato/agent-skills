---
name: inquisition
description: Review a set of changes with two fresh reviewers covering correctness and test evidence, and design and efficiency; then fix supported issues. Use only when the user explicitly requests the Inquisition skill.
disable-model-invocation: true
---

# Inquisition

Independently challenge a completed set of changes, then address supported
findings. Review requirements and correctness, test evidence, and design and
efficiency. This is a final review workflow; ordinary implementation requires
no separate skill or mandatory TDD loop.

## Establish scope and authority

Read repository instructions, inspect Git status, and identify the original
request or specification. Use the user's requested commits, revision range,
branch changes, paths, or working-tree changes. When none is specified, review
all staged, unstaged, and untracked changes. Include adjacent code needed to
understand their behavior; investigation beyond the diff does not expand edit
authority. If there is no change set or named target, ask for one.

Resolve references to commit IDs and record the comparison, included files, and
starting staging state. For a commit, compare its parent to that commit; for a
range, use the requested endpoints; for branch changes, use the merge base with
the intended target branch. Clarify an ambiguous merge parent or comparison
base. Include working-tree changes only when requested or selected by default.
For a combined review, inspect the net tracked diff from the selected base to
the working tree and enumerate untracked files separately. Plain `git diff`
omits staged and untracked changes; a committed diff omits working-tree changes.

Inspect the selected revisions, not unrelated later edits in the current checkout.
Preserve unrelated changes and the Git index. If the selected source changes
while reviewers work, refresh the affected review before applying findings.
Divide large scopes into bounded batches with the same two reviewer assignments
rather than silently sampling or claiming complete coverage.

An explicit Inquisition request authorizes localized fixes to the requested behavior
and behavior-preserving cleanup, unless the user requests review-only. Honor
narrower constraints. If requirements are unavailable, say so, use established
contracts, and ask only about uncertainty that materially affects a fix. A
review-only request produces findings without file edits. Skill invocation does
not authorize commits, pushes, PRs, publication, or destructive Git operations.

## Two fresh reviewers

The coordinating agent owns scope, synthesis, edits, and verification. Explicit
invocation authorizes two independent reviewers: one for correctness and test
evidence, and one for design and efficiency. Both inspect the complete selected
scope under their assigned responsibilities. Use fresh contexts without inherited
implementation conversation. Supply the same original requirements, governing
docs, resolved comparison, and file inventory to both reviewers. Provide paths or
snapshots they can inspect. Label implementation claims
and prior test results as unverified; do not steer reviewers with the implementer's
preferred conclusions or other reviewers' findings.

Run reviewers in parallel when supported. If concurrency is limited, run them
sequentially in separate fresh contexts. If independent contexts are unavailable,
report that limitation and do not claim a completed Inquisition review.

Reviewers read source and tests but do not edit, run formatters or shared test
suites, or spawn more reviewers. They request targeted execution evidence from
the coordinator when needed. Each returns concrete findings with location,
trigger or example, consequence, and suggested fix direction. Distinguish verified
defects, hypotheses, and test-evidence gaps. Include a compact coverage note for
each assigned lens: inspected and clean, findings, not applicable, or not
inspected. No findings is a valid result.

### Model and reasoning defaults

Honor explicit user or repository reviewer-model and reasoning preferences.
Otherwise apply the host's default to both reviewers:

| Host | Model family | Reasoning effort |
|---|---|---|
| Claude / Claude Code | Latest Opus | Medium |
| GPT / Codex | Latest Sol | Medium |
| Cursor | Latest Grok | High |

Select by host, not by the parent model: Cursor uses the Grok default even when
its parent runs Claude or GPT. Resolve "latest" at invocation time from the host's
current model catalog or a documented current-family alias. Use the newest
full-capability model in the required family available to that host; check official
provider documentation if version ordering is unclear. Do not pin a version in
this skill or substitute another family or a lightweight variant. These defaults
do not imply equal capability, cost, or reasoning scales across providers.

Set model and effort explicitly through the available subagent controls or an
existing compatible reviewer configuration. Check the host's supported values;
do not assume the parent's settings or an omitted effort match the table. Keep
this portable policy in the skill instructions and apply it through host-native
controls. Do not change persistent host configuration to enforce it.

Disclose the resolved models and effort levels briefly. If a setting cannot be
verified, say so instead of claiming it was applied. Use these defaults without
a routine model-selection question. If the required family or effort cannot be
selected through the available controls or existing configuration, ask once for
an alternative instead of silently substituting. Reuse a choice already supplied
by the user.

### 1. Correctness and test evidence

This reviewer owns both lenses below and reports their coverage separately.
Trace the behavior and its evidence together; neither lens is optional.

#### Correctness and requirements

Check whether the change fulfills the original request without unintended
behavior. Examine relevant errors, boundaries, persistence, compatibility,
resource ownership, concurrency, cancellation, stale completions, and security
consequences. Trace changed behavior into callers and dependencies. Prioritize
real defects and missing requirements over speculative edge cases.

#### Tests and evidence

Check whether tests exercise production behavior and reject plausible defects.
Assess independent expectations, meaningful boundaries, failure paths, and any
lifecycle or concurrency risks introduced by the change. Look for tests that
mirror implementation, exercise only mocks, or pass despite broken behavior.
Consider existing coverage before proposing additions or removals. Simple
assertions can protect important contracts; complexity and test counts are not
quality measures. Suggest a targeted mutation when sensitivity is uncertain,
not as a compulsory step for every test. Identify checks not actually run.

### 2. Design and efficiency

Look for duplicated logic or state, unnecessary layers, confusing ownership,
overcomplicated control flow, obsolete paths, and avoidable repeated work or
resource growth. Prefer existing project facilities and clear domain concepts.
Support performance findings with a concrete workload or code path. Preserve
useful abstractions; avoid redesigning adjacent systems or proposing speculative
optimizations. Cleanup must preserve intended behavior and relevant contracts.

## Resolve findings and verify

Re-read the cited code and test disputed claims. Deduplicate findings and rank
by impact and evidence, not reviewer agreement or report length. Reject false
positives and unsupported style preferences. Correctness and evidence gaps take
precedence over cosmetic cleanup.

As sole editor, apply supported fixes within authority. Reproduce a testable bug
with a failing regression test before fixing it. Strengthen weak tests when the
gap matters; retain independent expectations and use the smallest meaningful
scope. Pure refactors ordinarily use existing tests. Follow project rules for
non-automatable behavior and record precise manual verification when needed.
Report changes needing new product decisions or broader authority instead of
silently expanding the task.

Run focused checks while resolving defects, then applicable repository gates
against the final changes. Re-read the resulting diff for regressions, scope
creep, and obsolete leftovers. Revalidate affected areas after further edits.
Request a targeted follow-up from the relevant reviewer when a material fix or
unresolved disagreement needs independent checking; do not routinely repeat the
whole two-reviewer pass. Follow repository retry limits and report persistent
failures or missing evidence honestly.

Conclude with the reviewed scope, meaningful findings and fixes, validation
actually performed, and remaining risks or decisions. State incomplete review
coverage explicitly. Keep the report proportional to the change; the user should
be able to assess the outcome without reading individual reviewer transcripts.
