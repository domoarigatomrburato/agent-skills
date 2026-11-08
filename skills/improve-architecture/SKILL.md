---
name: improve-architecture
description: Find deepening opportunities in a codebase, rank them in the chat, and work through the one the user picks. Use only when the user explicitly requests Improve Architecture.
---

# Improve Architecture

Surface architectural friction and propose **deepening opportunities**: refactors that
turn shallow modules into deep ones, for testability and easier navigation. Results go
in the chat, short. Write no HTML, artifact or report file.

## Vocabulary

Use these terms consistently; do not drift into "component", "service", "API" or
"boundary".

- **Module**: anything with an interface and an implementation, at any scale: a
  function, class, package or slice.
- **Interface**: everything a caller must know to use the module correctly: types,
  invariants, ordering constraints, error modes, required configuration.
- **Depth**: leverage at the interface, the behaviour a caller or test can exercise per
  unit of interface to learn. Deep: much behaviour behind a small interface. Shallow:
  an interface nearly as complex as the implementation.
- **Seam**: where a module's interface lives, a place to change behaviour without
  editing there. Its placement is a design decision apart from what sits behind it.
- **Adapter**: a concrete thing that satisfies an interface at a seam.
- **Leverage**: what callers get from depth. **Locality**: what maintainers get from
  it: change, bugs and verification concentrate in one place.

## Process

### 1. Scope

Deepening pays off where code keeps changing (YAGNI). If the user named a direction (a
module, a subsystem, a pain point), take it. Otherwise read a good stretch of
`git log --oneline` for hot spots, the files and areas that keep coming up, and look
there first; if changes are scattered, widen the net.

### 2. Read the domain first

Follow the repository's instructions to its domain vocabulary (a glossary or domain
catalog such as `CONTEXT.md` or `GLOSSARY.md`) and its decision records (ADRs under
`docs/adr/` or wherever they live), for the area in scope. Name modules with the domain
terms: "the Order intake module", not "the OrderHandler service". Do not re-litigate a
decision record unless the friction is real enough to warrant it, and then say so
explicitly in the candidate.

### 3. Explore

Explore yourself. Use one read-only subagent only when the area does not fit your
context. Note where you meet friction:

- One concept needs many small modules to understand.
- Modules are shallow.
- Pure functions were extracted for testability while the bugs hide in how they are
  called.
- Coupled modules leak across their seams.
- Areas are untested or hard to test through their current interface.

Principles for judging what you find:

- **Deletion test**: imagine deleting the module. If complexity vanishes, it was a
  pass-through, a candidate to merge or remove; if it reappears across N callers, it
  earned its keep.
- **One adapter is a hypothetical seam, two are a real one.** Add a seam only where
  something varies across it.
- **Depth belongs to the interface.** A deep module may have small internal parts and
  internal seams; do not expose them just because tests use them.
- **The interface is the test surface.** Testing past the interface means the module
  has the wrong shape.
- **Replace, don't layer.** Once tests exist at the deepened interface, delete the old
  tests on the shallow pieces.

Classify a candidate's dependencies, which decides how its seam is tested:

- **In-process** (pure, in-memory): merge the modules and test through the new
  interface; no adapter.
- **Local-substitutable** (a local stand-in exists, such as an embedded database or
  in-memory filesystem): test with the stand-in; the seam stays internal.
- **Remote but owned** (your own services over a network): a port at the seam, a
  production adapter, and an in-memory adapter for tests.
- **True external** (third-party services): an injected port, a mock adapter in tests.

### 4. Present candidates

Reply in the chat with 3-5 candidates ranked, most valuable first. Each gets:

- **Files**: the modules involved.
- **Friction**: what hurts now.
- **Change**: what would be deepened, in plain words.
- **Gain**: in locality, leverage and tests.
- **Strength**: `Strong`, `Worth exploring` or `Speculative`.

Then one top recommendation with the reason, and the question: "Which of these would
you like to explore?" Do not propose interfaces yet.

### 5. Work through the pick

Ask focused questions one at a time, recommending an answer to each: constraints,
dependencies and their category, the deepened module's shape, what stays behind the
seam, which tests survive.

Only when the interface is genuinely uncertain, sketch two contrasting interfaces
yourself in the chat: a minimal one (one to three entry points) and one optimized for
the most common caller. Compare them on depth, locality and seam placement, then
recommend one. Start no parallel design subagents.

### 6. Side effects

- A new domain term for a deepened module, or a sharpened one, goes into the project's
  glossary in its existing format, created lazily if none exists.
- If the user rejects a candidate for a load-bearing reason a future review would need,
  offer to record a decision record. Skip ephemeral reasons ("not now") and obvious
  ones.

This skill requires no other installed skill and does not authorize implementation,
commits or pushes.
