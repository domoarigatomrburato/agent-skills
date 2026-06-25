# Profiles

Profiles express intent. They do not prescribe a universal model registry.

## Profile Meanings

- `smoke`: plumbing test. May use lightweight models. Output is not
  decision-grade.
- `budget`: optimize cost or quota pressure while preserving balanced reasoning
  quality. Do not silently downgrade substantive seats to lightweight models.
- `standard`: prefer quality and useful model/vendor diversity when available.
- `premium`: use the strongest available seats and maximum practical
  independence for high-impact decisions.

`budget` means quota-friendly, not weak. In a Codex/OpenAI harness, do not go
below a balanced model for substantive seats. In a multi-vendor harness, prefer
useful diversity when it is available without violating the chosen profile.

Do not hard-code model names in the skill, presets, or final prose. Resolve
models at runtime, record the actual choices in `council-plan.md`, and make the
trust implications visible in `final.md`.

For `premium`, the chair may map `balanced` slots to the strongest practical
models when the harness makes that possible. Record the mapping explicitly
instead of editing preset files just to name a stronger model.

## Preflight

Before a non-smoke council, the chair must present a plan and wait for user
confirmation unless the user already specified preset/profile and explicitly
told the chair to proceed.

The confirmed plan must include:

- preset and profile
- objective and expected final artifact
- seat names and epistemic roles
- resolved model for each seat, or `harness default`
- whether model/vendor diversity is real, partial, or absent
- profile limitations and decision grade
- meaningful alternatives when they exist

Save the confirmed plan as `council-plan.md` and pass it to `start` with
`--plan-file`.

Use [council-plan-template.md](council-plan-template.md) unless the harness has
an equivalent structured plan format.

The canonical confirmation phrase is:

```text
Proceed with this [profile] [preset] council.
```

If the user already gave an explicit preset/profile/proceed instruction, record
that instruction in the plan instead of asking again.

## Profile Fit

- `selftest` should use `smoke`.
- `research-dossier-budget` is the default budget dossier preset.
- `research-dossier` is the default standard or premium dossier preset.

The helper warns when a profile and built-in preset look mismatched. Warnings do
not block the run because the chair and user may intentionally choose a heavier
or lighter workflow.

## Diversity Labels

- `real`: at least two genuinely different model families or vendors.
- `partial`: different models or reasoning settings, but one vendor or family.
- `absent`: same-model council. This is role separation, not independent model
  diversity.

Do not block a useful same-model run. Label it plainly.

## Final Grade

The final metadata must make trust level visible before the prose:

```text
- profile: budget
- decision_grade: first-pass, not procurement-ready
- model_diversity: absent, same-model council
- confirmed_plan: council-plan.md
- transcript: transcript.md
```

For research and procurement-adjacent work, a budget run is usually a first pass
unless the evidence is independently verified and citation integrity is clean.
