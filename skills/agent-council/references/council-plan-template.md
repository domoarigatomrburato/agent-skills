# Council Plan Template

Use this template for non-smoke preflight. Replace every bracketed value before
asking the user to confirm.

```markdown
# Council Plan

- preset: [preset name]
- profile: [smoke | budget | standard | premium]
- objective: [one sentence]
- expected_final_artifact: [what final.md should be]
- decision_grade: [for example: first-pass, not procurement-ready]
- model_diversity: [real | partial | absent, with short reason]
- confirmation: [user confirmed on YYYY-MM-DD, or explicit proceed phrase]

## Seats

| seat | epistemic role | model slot | resolved model | reason |
| --- | --- | --- | --- | --- |
| [seat] | [role] | [slot] | [model or harness default] | [why this is suitable] |

## External Seat Access

| seat | provider | cwd/access envelope | trust authorization | discovery/probe artifact |
| --- | --- | --- | --- | --- |
| [seat or n/a] | [cursor/copilot/shell] | [cwd covers repo and run-dir?] | [none or explicit user authorization] | [path or n/a] |

## Limitations

- [budget, vendor, model-selection, source-access, or time limitation]

## Alternatives Considered

- [alternative preset/profile/model mix] -> [why not chosen]
```

Recommended confirmation phrase when the user wants the chair to proceed
without more discussion:

```text
Proceed with this [profile] [preset] council.
```
