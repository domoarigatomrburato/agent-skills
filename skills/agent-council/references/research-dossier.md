# Research Dossier Doctrine

Use `research-dossier-budget` or `research-dossier` when the user wants
source-backed research rather than a fast opinion.

## Required Flow

Budget dossier:

1. `evidence-matrix`
2. `citation-audit`
3. `evidence-repair`
4. `decision-critique`
5. chair final

Full dossier:

1. `evidence-matrix`
2. `citation-audit`
3. `evidence-repair`
4. `citation-reaudit`
5. parallel adoption-risk and clarity-calibration critiques
6. chair final

Do not skip the repair pass. It exists so citation contamination remains visible
instead of being washed away by synthesis.

## Evidence Matrix

The first turn should build a matrix that, for each shortlisted item, captures:

- category
- support or applicability
- deployment or operating model
- data exposure or trust boundary
- integration surface
- cost or licensing caveat when relevant
- source URL or explicit `unknown`
- confidence

Separate confirmed facts, inferences, assumptions, and open questions.

## Citation Integrity

The audit turn must end with exactly one of:

- `CITATION_INTEGRITY: PASS`
- `CITATION_INTEGRITY: FAIL`

On `FAIL`, it must list each contaminated claim as:

```text
claim -> wrong source/subject -> correct subject
```

## Repair

`evidence-repair` must emit a full `Canonical Evidence Matrix`, not a patch
annex. The canonical matrix becomes the chair's evidence source for downstream
critique and final editing.

When the audit fails, repair must:

- re-attribute every flagged claim to its correct subject and source
- mark unverifiable claims `unknown`
- rebuild every affected row
- write a `Citation Corrections` log

When the audit passes, repair still restates the verified key sources and emits
the canonical matrix.

## Re-Audit Boundary

`research-dossier-budget` stops after repair plus critique. That is enough for a
first-pass decision artifact, not for a procurement-ready claim when the initial
audit failed.

`research-dossier` includes `citation-reaudit`. To call a dossier
procurement-ready after `CITATION_INTEGRITY: FAIL`, the re-audit must end with
`CITATION_INTEGRITY: PASS`, or the chair must finalize with an explicit override
and state why that risk is acceptable.

## Final Dossier

`final.md` should include:

- Executive Summary
- Evidence Summary
- Recommendation
- Shortlist With Confidence
- Citation Integrity & Corrections
- Unknowns
- Decision Gates
- What To Verify Next
- Patch Or Instructions

If citation integrity failed and was not clearly repaired, the final must lower
confidence and say the dossier is not publish-ready. If there is no second audit
after repair, do not imply a clean independent pass; say the chair synthesized
from the repaired matrix.
