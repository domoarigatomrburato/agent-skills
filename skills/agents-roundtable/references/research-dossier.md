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

## Citation Integrity Protocol

Source-backed runs fail in a specific way: an evidence-builder can attach a real
source to the wrong subject (for example a GitLab fact attributed to Qodo or
PR-Agent). The dossier flow guards against this in three steps.

1. The `source-auditor` turn verifies subject/source attribution and ends with a
   verdict line that is exactly `CITATION_INTEGRITY: PASS` or
   `CITATION_INTEGRITY: FAIL`, followed by each contaminated claim as
   `claim -> wrong source/subject -> correct subject`.
2. A mandatory `source-repair` turn runs before the final. On `FAIL` it
   re-attributes every flagged claim, marks unverifiable claims `unknown`,
   rebuilds the affected rows, and writes a `Citation Corrections` log. On
   `PASS` it states that no repair was required and restates the verified key
   sources. The pass always runs so the repair is never skipped.
3. `final.md` must keep contamination visible in a `Citation Integrity &
   Corrections` section: what the audit flagged, what the repair fixed, and any
   flagged citation that was not repaired (with lowered confidence).

Do not let the final quietly absorb corrections. A reader must be able to see
that the first draft was contaminated and how it was repaired.

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
- citation integrity and corrections;
- major unknowns and decision gates;
- what to verify next;
- recovery note when applicable.
