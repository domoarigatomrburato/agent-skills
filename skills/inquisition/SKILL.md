---
name: inquisition
description: Clean up a set of changes, then review the cleaned-up result for bugs, mirroring Claude Code's /simplify followed by /code-review. Four parallel reviewers first look for reuse, simplification, efficiency, and fix-depth issues, and the coordinator applies the behavior-preserving fixes. The depth of the bug review then follows a review level (low, medium, high, xhigh, or max), taken from the coordinator's reasoning effort unless the user names one; lower levels run the review angles in the coordinator's own context, and only the max level adds parallel finders, independent verification of every candidate, and a gap sweep. The coordinator fixes the supported defects. Use only when the user explicitly requests the Inquisition skill.
---

# Inquisition

Challenge a completed set of changes in two phases, in this order:

1. **Clean up.** Find code that duplicates what the codebase already has, is
   more complex or slower than it needs to be, or patches a symptom instead of
   the cause, and fix it without changing behavior.
2. **Review for bugs.** Review the cleaned-up result for defects at the review
   level, and fix the supported ones.

The order matters. Reviewing for bugs after the cleanup means the review reads
the code that will actually ship, and catches defects the cleanup itself
introduced. The two phases mirror Claude Code's `/simplify` followed by
`/code-review` at the review level, rewritten for any agent host.

## Scope and authority

Read the repository's instruction files and inspect Git status. Identify the
original request or specification. If none is available, say so, rely on the
established contracts in the code and documentation, and ask only about
uncertainty that changes a fix.

Review what the user names: commits, a revision range, a branch, paths, or
working-tree changes. When nothing is named, review the current branch's
changes since its merge base with the remote default branch, together with all
staged, unstaged, and untracked changes. Include working-tree changes in any
other scope only when the user asks. If there is nothing to review, ask for a
target.

Resolve the scope once and record it as the exact comparison: the parent of a
single commit, the named endpoints of a range, or the merge base with the
target branch, and whether it ends at a commit or at the working tree. Ask when
the base is ambiguous, such as which parent of a merge commit. Record the files
involved, listing untracked files separately, since plain `git diff` omits
them. Read adjacent code as needed to understand the change; reading it does
not extend what you may edit. Review the selected revisions, not unrelated
later changes in the checkout. Preserve unrelated changes and the Git index. If
the code under review changes while reviewers work, rerun the affected review
before acting on its findings.

An explicit request authorizes behavior-preserving cleanup and localized fixes
to the requested behavior. Honor narrower constraints. On a review-only
request, edit nothing: since no edits separate the phases, run both phases on
the change as it is, starting Phase 2 together with the Phase 1 reviewers, and
report the cleanup findings as proposals. The skill never authorizes commits,
pushes, pull or merge requests, publication, or destructive Git operations.

If the change cannot alter behavior, such as comments, formatting, or
documentation that no program or agent reads as instructions, review it
yourself in a single pass instead of starting reviewers, and say so.

## Reviewers

The coordinator owns scope, edits, checks, and the report. Reviewers find
candidates; verifiers judge them. Neither edits files, runs formatters or the
shared test suite, or starts further subagents.

- Give each reviewer and verifier a fresh context with the original request,
  the exact comparison, the file list, its task, and the output it must
  return. Pass paths, not file contents: they read what their task needs. Do
  not pass the implementation conversation or, to a reviewer, other
  reviewers' findings.
- Label each reviewer and verifier with its role and what it covers, so
  progress lists read clearly. The Phase 1 reviewers are "Inquisitor: Reuse",
  "Inquisitor: Simplification", "Inquisitor: Efficiency", and
  "Inquisitor: Fix depth". A Phase 2 finder at the max level is
  "Inquisitor: " followed by its angle, such as "Inquisitor: Line by line" or
  "Inquisitor: Removed behavior". A verifier is "Qualifier: " followed by a
  short summary of what it judges, such as "Qualifier: Missing await in
  loadUser". The gap sweep at the max level is "Grand Inquisitor". Keep the
  angle or the candidate in every label; the gap sweep runs once, so its name
  is enough. The theme is for labels only: the report and anything written to
  the repository stay plainly worded. Hosts that do not display agent names
  can ignore this rule.
- Each reviewer ends with a one-line coverage note: what it read, and what it
  skipped or could not read. No findings is a valid result. A reviewer that
  needs a test or command run asks the coordinator for it.
- Start the reviewers of a phase together, so they run in parallel. If the
  host limits concurrency, run them in turn, each in a fresh context.
- Use a full-capability model, at a reasoning effort no lower than your own,
  for reviewers and verifiers; never a lightweight or fast variant. Follow any
  model choice from the user or the repository. If the host does not let you
  set or see the model or effort, say so in the report instead of claiming
  one.
- When the host offers a read-only agent type, limited to reading files and
  running read-only commands, start reviewers and verifiers with it. They
  never edit, and a smaller toolset keeps each fresh context smaller, which
  matters when a phase starts many of them.
- If the host cannot run subagents, perform every angle and every
  verification yourself, sequentially, in your own context. Say in the report
  that the review was single-pass, so nobody mistakes it for an independent
  review.

## Review level

The review level sets how deep Phase 2 goes. It is one of `low`, `medium`,
`high`, `xhigh`, or `max`, resolved in this order:

1. a level the user names in the request;
2. otherwise your own reasoning effort, when the host exposes it, with a host
   value of `minimal` or `none` read as `low`;
3. otherwise `high`.

`medium` runs the `high` structure. The level changes only Phase 2: Phase 1
starts the same four reviewers at every level.

| Level | Phase 2 structure | Subagents started in Phase 2 |
| --- | --- | --- |
| `low` | One pass over the diff by the coordinator | 0 |
| `medium`, `high` | 9 angles run by the coordinator | 0 |
| `xhigh` | 11 angles and a gap sweep run by the coordinator | 0 |
| `max` | 11 finders, per-candidate verifiers, a sweep | 12 + 1 per candidate |

At `max`, each candidate the sweep adds gets its own verifier too. The Tests
angle is the one addition to the `/code-review` recipe, kept because it
surfaces defects the tests would let through; it does not run at `low`.

## Phase 1: Clean up

Start four reviewers, one per angle, at every level. Give each the whole
comparison and the complete file list. Each returns findings with file, line,
a one-line summary, and the concrete cost: what is duplicated, wasted, or
harder to maintain.

### Reuse

New code that re-implements something the codebase already has. Search shared
and utility modules and the files next to the change, and name the existing
function or facility to use instead.

### Simplification

Complexity the change adds without need: state that duplicates or can be
derived from other state, copy-paste with small variations, deep nesting,
layers that only forward calls, and dead code the change leaves behind. Name
the simpler form that does the same job.

### Efficiency

Work the change wastes: repeated computation or I/O, independent operations
run one after another, and blocking work on startup or on a hot path. Also
look for long-lived objects built from closures or captured environments: they
keep the whole enclosing scope alive for their lifetime, which leaks memory
when that scope holds large values, and a class or struct that copies only the
fields it needs avoids it. Back each finding with the code path or workload
where the cost appears, and name the cheaper alternative.

### Fix depth

Changes that patch a symptom instead of fixing the cause at the right level.
Special cases added to shared code are the usual sign. Prefer the simpler,
more general change to the underlying mechanism, and name where it belongs.

### Apply

When all four reviewers have reported, merge findings that point at the same
line or mechanism, and fix each remaining one. Before editing or deleting a
file, save a copy of it outside the repository, and record each file you
create. Skip a finding when its fix would change intended behavior, require
edits well outside the change, or is a false positive, and record the skip with
its reason instead of arguing with it. Run the fast checks that cover the
edited files before moving on. If a cleanup breaks a check and the cause is not
obvious, revert that cleanup and record it as skipped.

The cleanup patch is the difference between each saved copy and the current
file, plus each file Phase 1 created: the Phase 1 edits and nothing else, even
when the checkout holds other uncommitted work. Write it to a file outside the
repository, so that Phase 2 can read it by path: for example with `diff -uN`
from each saved copy to the current file, which treats a deleted file as
empty, and from `/dev/null` to each created file.

## Phase 2: Review for bugs

Review the same scope again, now including the Phase 1 edits. When the scope
ends at the working tree, the recorded comparison already contains them. When
it ends at a commit, read the recorded comparison at its end revision (for
example with `git show <revision>:<path>`) and the cleanup patch file, with
the working tree for the context around its hunks; at the max level, give
both to every finder and verifier. Later changes in the checkout stay out of
scope. Add every file Phase 1 touched to the file list.

Run the subsection for the review level. The angles and the gap sweep are
defined once below; each level lists which it runs and its caps.

### Angles

Each angle returns candidates with file, line, a one-line summary, the angle
that produced it, and a failure scenario: the input or state that triggers the
defect and the wrong result it produces. Cleanup, fix-depth, and conventions
candidates state the concrete cost instead: what is duplicated, wasted, or
harder to maintain, or which rule is broken. Report every candidate with a
nameable failure scenario, even when unsure; candidates dropped silently at
this stage are the main source of missed bugs. Put the strongest candidates
first and name any beyond the angle's cap in one line each rather than
dropping them. Do not let one angle's conclusions suppress another's: if two
angles flag the same line for different reasons, record both.

- **A. Line by line.** Read every hunk and the whole function around it; bugs
  in unchanged lines of a touched function count. For each line ask what
  input, state, timing, or platform makes it wrong: inverted conditions,
  off-by-one errors, missing null checks, a zero treated as missing, a missing
  `await`, the wrong variable after copy-paste, errors swallowed instead of
  propagated, unescaped patterns.
- **B. Removed behavior.** For every deleted or replaced line, name the
  guarantee it provided and find where the new code provides it again. If
  nowhere, that is a candidate: a dropped guard, error path, validation, or
  test.
- **C. Callers and callees.** For every changed function, find its callers and
  check that the change breaks none of them: a new precondition, a different
  return shape, a new error, an ordering or timing dependency. Check that the
  calls the change makes are still safe given the rest of the change.
- **D. Language pitfalls.** The classic traps of the languages and frameworks
  involved, such as type coercion, a loop variable captured by a closure,
  late-binding closures, mutable default arguments, a write to a nil map,
  queries built by string concatenation, time zones and daylight saving, and
  float equality. Report only instances the change introduces.
- **E. Wrappers and proxies.** When the change adds or modifies a type that
  wraps another, such as a cache, proxy, decorator, or adapter, check that
  every method calls the wrapped instance instead of going back through a
  registry, session, or global lookup, which re-enters the wrapper or
  recurses, and that the wrapper forwards every method its callers use.
- **F. Tests.** Whether the tests exercise the changed behavior and would fail
  if it broke: tests that only exercise mocks, assertions that mirror the
  implementation, and failure paths or boundaries the change adds without a
  test. Say which checks were not run.
- **Reuse, Simplification, Efficiency, Fix depth.** The Phase 1 angles, as
  defined there, applied to the code after Phase 1.
- **Conventions.** The instruction files that govern the changed files: the
  user-level files the host loads, such as `~/.claude/CLAUDE.md` or
  `~/.codex/AGENTS.md`, and the repository's files, such as `AGENTS.md`,
  `CLAUDE.md`, `CONTRIBUTING.md`, and editor rule files, at the root and in
  parent directories of a changed file. A file in a directory governs only the
  files at or below that directory. Report only a clear violation, naming the
  file and quoting the rule and the line that breaks it. If no instruction
  file applies, return nothing.

Where a cap forces a cut, correctness findings outrank cleanup, fix-depth, and
conventions findings.

### Gap sweep

A final pass by a fresh reviewer that holds the list of findings so far. It
rereads the change and the functions around it looking only for defects not
already listed, without re-deriving or re-confirming anything on the list. It
focuses on what the first pass tends to miss: moved or extracted code that
lost a guard or a pattern anchor, narrowed lock scopes, a default evaluated
once and then shared, such as a dataclass field default, hash values or
iteration order assumed stable across runs, predicate methods with side
effects, setup and teardown mismatches in tests, and changed configuration
defaults. It returns up to 8 new candidates, or none when it finds nothing
new; it does not pad.

### Low

Work alone, in one pass over the diff: start no subagents and read no whole
files. Skip test and fixture hunks, under `test/`, `spec/`, `__tests__/`,
`fixtures/`, or `testdata/`, or in files named `*_test.*` or `*.test.*`: test
changes are not reviewed at this level.

Flag only runtime-correctness defects visible from the hunk alone: an inverted
or wrong condition, an off-by-one error, a null or undefined dereference where
adjacent lines show the value can be absent, a removed guard, a zero treated
as missing, a missing `await`, the wrong variable after copy-paste, or an error
swallowed where it should propagate. Also flag, still from the hunk alone, new
code that duplicates a helper visible in the diff context, and dead code the
change leaves behind. Flag nothing else: no style, naming, performance,
missing tests, or anything outside the hunk.

Keep at most 4 findings, most severe first.

### Medium and high

Run nine angles, A, B, C, F, Reuse, Simplification, Efficiency, Fix depth, and
Conventions, yourself, in sequence, in your own context; start no subagents.
Each angle surfaces up to 6 candidates.

Pool the candidates and merge only near-duplicates: the same defect at the
same place for the same reason. Do not verify or re-judge them at this step.
Sort by severity.

Aim for at least 5 findings; when fewer genuine ones exist, keep what you have
rather than inventing more. Keep at most 10, the most severe.

### Xhigh

Run all eleven angles, A to F, Reuse, Simplification, Efficiency, Fix depth,
and Conventions, yourself, in sequence, in your own context; start no
subagents. Each angle surfaces up to 8 candidates.

Pool the candidates and merge only near-duplicates: the same defect at the
same place for the same reason. Do not verify or re-judge them, and do not
drop any on uncertainty. Sort by severity.

Then run the gap sweep yourself, in the same context, with the merged list.

Aim for at least 7 findings; when fewer genuine ones exist, keep what you have
rather than inventing more. Keep at most 15, the most severe.

### Max

Start eleven finders together, one per angle: A to F, Reuse, Simplification,
Efficiency, Fix depth, and Conventions. Each surfaces up to 8 candidates.

Merge candidates that point at the same line or mechanism, keeping the one
with the most concrete failure scenario. Then give each remaining candidate to
its own fresh verifier, with the change and the files involved. The verifier
returns one verdict:

- **Confirmed**: it can name the input or state that triggers the defect and
  the wrong result, quoting the line.
- **Plausible**: the mechanism is real but the trigger depends on timing,
  environment, or configuration. It states what would confirm it. A rare but
  reachable path, such as an error handler, a cold cache, a missing optional
  field, a race, or a retry after a partial failure, is plausible, not
  refuted.
- **Refuted**: the code does not say what the candidate claims, the case is
  impossible, the change already handles it, or the issue has no observable
  effect. It quotes the line that proves it.

For a test finding (angle F), confirmed means naming a plausible defect in the
changed behavior that the tests would let through. For a conventions finding,
it means quoting a rule that applies to the file and the line that breaks it.

Keep confirmed and plausible candidates and drop refuted ones: a single vote
that is not refuted carries the finding. Do not drop on uncertainty.

Then start one more reviewer for the gap sweep, in a fresh context, with the
kept findings. Give each candidate it returns its own verifier, the same way.

Keep at most 15 findings, the most severe.

## Fix and check

Reread the code behind each kept finding before acting on it. Below the max
level nothing has been verified independently, so this reread replaces
verification: judge each finding against the code as a verifier would, and
drop the ones the code refutes, recording why. Rank findings by impact and
evidence, not by how many angles raised them.

- Fix confirmed defects within your authority. For a testable bug, write a
  regression test that fails before the fix and passes after it.
- Fix a plausible defect when the fix is small and safe; otherwise report it
  with what would confirm it.
- Add the missing test when a test finding matters, keeping its expectations
  independent of the implementation, and fix convention breaches in the
  changed lines.
- Apply Phase 2 cleanup and fix-depth findings under the same rules as Phase
  1's Apply section.
- Report instead of fixing anything that needs a product decision or edits
  beyond your authority.

Then run the repository's applicable checks on the final state and reread the
final diff for regressions, scope creep, and leftovers. At the max level, also
give any material fix whose correctness is not obvious to a fresh verifier. Do
not repeat both phases. Follow the repository's retry limits and report checks
that still fail.

## Report

Keep the report proportional to the change:

- the scope: the comparison and the files;
- what ran: the review level and where it came from, named by the user, your
  reasoning effort, or the default; the number of subagents started and their
  models; or that the review was single-pass;
- cleanup: what was fixed, and what was skipped and why, or, on a review-only
  run, what is proposed;
- bugs: each kept finding with its verdict, from a verifier at the max level
  or from your own judgment below it, and whether it was fixed;
- the checks actually run and their results, and those not run;
- remaining risks, open decisions, and what the coverage notes say was not
  read.
