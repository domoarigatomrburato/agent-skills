# Fallback documentation formats

Use existing project conventions first. These defaults apply only when no
format or location is established.

## Domain glossary

Start with one root `CONTEXT.md`. Describe the domain briefly, then define the
terms and relationships needed for the current decision. Use a short definition
and list avoided synonyms only where confusion is plausible. Include lifecycle
or ownership constraints when they distinguish concepts.

```markdown
# Ordering

## Language

**Order**: A customer's request to purchase a set of items.
_Avoid_: Shipment; an order may produce several shipments.

**Shipment**: Items dispatched together to fulfill part or all of an order.
```

Keep implementation plans and generic programming definitions out of the domain
glossary. Introduce multiple context documents only for a demonstrated domain
need and within the authorized scope.

## Architecture decision record

Use `docs/adr/NNNN-short-title.md`, choosing the next available number. Check
again before writing so concurrent work is not overwritten.

A useful ADR explains what was decided, why, and the consequence that matters.
Add structure only when it helps:

```markdown
# Record source database changes transactionally

A partial update can leave references pointing at deleted records. We apply
related mutations in one transaction so readers observe a consistent state.
This keeps recovery simple but requires bounding each batch's transaction time.
```

If alternatives or status matter, include them. Mark a proposed decision as
proposed; mark an accepted one as accepted only when the decision is settled.
When superseding a decision, retain the original and link both records.
