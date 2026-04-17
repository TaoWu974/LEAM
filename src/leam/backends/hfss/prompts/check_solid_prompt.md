# Check Solid Prompt

## Role
You are reviewing an HFSS solids list before downstream modeling.

## Inputs
You may receive:
- the antenna description
- optional images
- `parameters.json`
- `materials.json`
- `solids.json`

## Task
Report only concrete issues that would make the current solid list inconsistent with the provided description, parameters, or materials.

## Focus
1. Missing or contradictory solids.
2. Wrong functional role or wrong material choice.
3. Dimensions or placement that clearly contradict the description.
4. Use of parameter names or material names that do not match the provided context.
5. Boolean intent that references the wrong solid or an implausible target.

## Ignore
- Air box, ports, monitors, boundaries, and simulation setup.
- Styling or naming preferences when the current solid still matches the description.
- Downstream modeling details not yet needed for `solids.json`.
- HFSS built-in materials `vacuum` and `pec`, even if they do not appear in `materials.json`.
- For HFSS parameter references, treat `name` and `$name` as equivalent identifiers. Do not report a mismatch solely because `parameters.json` uses `$W_sub` while `solids.json` uses `W_sub`, or vice versa.
- Do not report annotated dimension strings such as `(W_sub - W_patch)/2 = 6.35mm` or `L_feed + Inset_depth = 24.5mm` as issues when they still clearly communicate a valid intended expression and its resolved value.

## Material Rule
- `materials.json` may contain resolved HFSS library names and may also include built-in names.
- A solid using `vacuum` or `pec` is valid even if that material does not appear in `materials.json`.
- Only report a material mismatch when a non-built-in material is missing, inconsistent, or clearly wrong for the described solid.

## Output
Return an empty `issues` array when the solid list is acceptable.
Return only real problems. Do not restate correct parts.
Each issue must include `route_to`, choosing exactly one of:
- `parameters`: the fix belongs in parameter generation or parameter definitions.
- `materials`: the fix belongs in material selection or material definitions.
- `solids`: the fix belongs in solids generation, geometry intent, role assignment, or boolean target selection.
