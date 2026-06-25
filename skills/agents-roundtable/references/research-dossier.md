# Research Dossier Workflow

Use this branch when the user asks for an investigation into the current state
of tools, vendors, standards, regulations, APIs, or other fast-moving facts.

## Completion Standard

The human-facing output is still `<run-dir>/final.md`, but it must be backed by
an evidence matrix in the transcript. A dossier is incomplete unless shortlisted
items have source-backed entries for:

- category;
- support status or applicability;
- deployment or operating model;
- data exposure or trust boundary;
- integration surface;
- cost or licensing caveat when relevant;
- source URL or explicit `unknown`;
- confidence.

If evidence is missing, keep the item and mark it `unknown`; do not fill gaps
with confident prose.

## Arbiter Rules

- Prefer official documentation, standards, release notes, pricing/licensing
  pages, and primary repositories.
- Keep source URLs near the claims they support.
- Separate confirmed facts, inferences, assumptions, and open questions.
- Treat vendor claims as claims, not as independent proof.
- Do not introduce new factual claims in `final.md` unless they appeared in the
  evidence matrix or are explicitly marked as inference or assumption.
- If a research or audit turn fails and recovery uses a shorter prompt, label
  the result as a recovered dossier and lower confidence where evidence was not
  rechecked.

## Expected Final Shape

`final.md` should include:

- executive summary;
- evidence summary table;
- recommendation;
- shortlist with confidence;
- major unknowns and decision gates;
- what to verify next;
- recovery note when applicable.
