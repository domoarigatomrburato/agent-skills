---
name: domain-modeling
description: Clarify domain vocabulary, relationships, and durable decisions. Use only when the user explicitly requests Domain Modeling.
disable-model-invocation: true
---

# Domain Modeling

Make the project's concepts precise enough to guide code and conversation.
Capture agreed meaning and the reasons for durable decisions without turning the
domain model into an implementation plan.

## Read the existing model

Follow repository instructions to find its glossary, domain documentation, and
ADRs. Respect their locations, ownership, terminology, and formats. If a context
map already exists, use it to find the relevant context. Reading or using an
existing glossary during ordinary work does not require this workflow.

## Resolve meaningful ambiguity

Check terms against the existing definitions and relevant code. Distinguish a
contradiction in meaning from an implementation defect; code is evidence of
current behavior, not proof of intended behavior.

Use concrete scenarios to test relationships, ownership, lifecycle, and edge
cases. Ask the user only about ambiguity that changes the model or a decision;
recommend terminology and explain its consequences. Preserve familiar project
terms when they are already precise. Avoid renaming concepts to fit a generic
architecture vocabulary.

## Record what was agreed

When documentation changes are within the request, update the canonical source
with accepted terms and relationships. Keep definitions short and domain-specific.
Keep proposed interpretations visibly separate from accepted ones. If the session
is discussion-only, summarize proposed edits without writing them.

Record an ADR when a decision has a durable consequence or meaningful reversal
cost, a rationale a future maintainer would otherwise miss, and a real tradeoff.
Capture the context, decision, reasons, and material consequences. Include rejected
alternatives only when remembering why they lost would help. A short paragraph
can suffice; do not manufacture user stories or acceptance tests to fill a template.

Preserve accepted ADR history. When a decision changes, follow the project's
supersession convention and link the replacement. Keep task lists and execution
plans in their existing planning surface.

Use [the documentation formats](references/documentation-formats.md) only when
the repository has no established format. Create documentation lazily when there
is agreed content to record. This skill requires no other installed skill and
does not authorize implementation, issue publication, commits, or pushes.
