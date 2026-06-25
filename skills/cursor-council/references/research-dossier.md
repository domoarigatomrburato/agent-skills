# Research Dossier Doctrine

Use the `research-dossier` preset when the user wants source-backed research
rather than a fast opinion.

## Required Flow

The preset is intentionally opinionated:

1. `evidence-matrix`
2. `source-audit`
3. `source-repair`
4. one critique round
5. `final-dossier`

Do not skip the repair pass. It exists so citation contamination stays visible
instead of being quietly washed away by the final synthesis.

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

The `source-audit` turn must end with exactly one of:

- `CITATION_INTEGRITY: PASS`
- `CITATION_INTEGRITY: FAIL`

On `FAIL`, it must also list each contaminated claim as:

```text
claim -> wrong source/subject -> correct subject
```

## Source Repair

When the audit fails, `source-repair` must:

- re-attribute every flagged claim to its correct subject and source;
- mark unverifiable claims `unknown`;
- rebuild the affected rows;
- write a `Citation Corrections` log so the contamination remains visible
  downstream.

When the audit passes, `source-repair` should say that no repair was required
and restate the verified key sources.

## Final Dossier

`final.md` should include, at minimum:

- Executive Summary
- Evidence Summary
- Recommendation
- Shortlist With Confidence
- Citation Integrity & Corrections
- Unknowns
- Decision Gates
- What To Verify Next
- Patch Or Instructions

The final must not quietly invent facts. If a flagged citation was not repaired,
lower the affected confidence and say so explicitly.
