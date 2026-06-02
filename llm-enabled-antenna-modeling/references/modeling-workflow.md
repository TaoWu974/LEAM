# Modeling Workflow

## Step Order

Use this pipeline unless the user asks for only one artifact:

1. **Initial Solids**: only for weak descriptions; infer a first-pass solid list before downstream extraction.
2. **Parameters**: extract only geometric variables used to build geometry. For weak descriptions, use `initial_solids` as context.
3. **Materials**: map required materials to simulator material names. For weak descriptions, use `initial_solids` as context.
4. **Solids**: produce a final solid list with functional roles, materials, 3D/2.5D type, dimensions, and boolean intent.
5. **Check Solid**: review solids against description, parameters, and materials.
6. **Dimensions**: rewrite solids into coordinate-based ranges and structured 2.5D profiles.
7. **3D Model**: generate CST VBA or HFSS PyAEDT code for Type=`3D` solids only.
8. **2.5D Model**: generate code for Type=`2.5D` profiles only.
9. **Boolean Operations**: generate only unite/subtract/intersect/imprint operations.
10. **Parameter Update**: optional tuning artifact for existing variables.

## Workflow Selection

Use `strong_description` when geometry, dimensions, layer stack, and relationships are already clear.

Use `weak_description` when the request is high level, such as "design a rectangular slotted patch at 2.45 GHz." Infer a reasonable standard antenna structure and mark assumptions.

Use `paper_reconstruction` when the input is a paper, figure, table, caption, or measurement note. Prioritize source-specific facts over generic design heuristics. If a figure/table appears inconsistent, state the correction as an assumption.

## 3D vs 2.5D

Prefer 3D whenever a built-in primitive can represent the solid:

- Box/brick rectangular substrate, patch, ground, feed, rectangular slots.
- Cylinder/circle, cone, sphere, torus, elliptical cylinder, regular prism.

Use 2.5D only for planar profiles that must be sketched and extruded:

- Splines, tapered slots, irregular polygons, curved profiles, compound outlines.
- Shapes described by points, curves, arcs, or closed planar artwork.

For 2.5D solids, include the planar profile and extrusion/rotation data in `dimensions`, not as vague notes.

## Artifact Handoff Rules

- Parameters feed all later geometry steps.
- Materials feed solids and model generation.
- Solids feed check, dimensions, and model selection.
- Dimensions feed 3D/2.5D code and boolean code.
- 3D and 2.5D code create solids but must not perform boolean operations.
- Boolean code operates only on already-created solids.

Default upstream artifact selection:

- `Check Solid` consumes `solids.json`, `parameters.json`, and `materials.json`.
- `Dimensions` consumes `solids.json` plus `parameters.bas` for CST or `parameters.json` for HFSS.
- `3D Model` consumes `dimensions.json`, the backend parameter artifact, and the backend material artifact: `materials.bas` for CST or `materials.json` for HFSS.
- `2.5D Model` consumes the same inputs as `3D Model` plus the generated `model_3d` script.
- `Boolean Operations` consumes the backend parameter artifact, `dimensions.json`, `model_3d`, and `model_2d` when 2.5D is enabled.
- `CST Project` consumes `parameters.bas`, `materials.bas`, `model_3d.bas`, optional `model_2d.bas`, and `boolean.bas`.
- `HFSS Project` consumes `parameters.py`, `model_3d.py`, optional `model_2d.py`, and `boolean.py`.
- `Parameter Update` consumes `dimensions.json` and the backend parameter artifact.
- `CST Update` consumes `antenna.cst` and `parameter_update.bas`; `HFSS Update` consumes `antenna.aedt` and `parameter_update.py`.

## Common Antenna Modeling Assumptions

Use assumptions only when the user does not provide explicit facts:

- Coordinate origin should be explicit, often the lower-left/bottom corner of substrate.
- Units should usually be millimeters for microwave antenna geometry.
- Conductive metal should follow backend convention when no specific conductor is supplied: CST defaults to `Copper (pure)` when available, otherwise falls back to `PEC` with an assumption note; HFSS may use `pec`.
- Slots/cutouts are modeled as vacuum tool solids, then subtracted.
- Thin metal patches/grounds/feeds should still have a finite thickness parameter.
- A feed should penetrate or overlap the radiator by a small amount to ensure contact.
- Do not add air boxes, ports, boundaries, monitors, or solver setup in geometry artifacts.

## Review Loop

After `check_solid`, if issues exist:

- `route_to: "parameters"` for missing/wrong geometric variables.
- `route_to: "materials"` for missing/wrong non-built-in material names.
- `route_to: "solids"` for missing solids, wrong roles, wrong materials on solids, placement contradictions, or bad boolean targets.

Fix upstream artifacts before regenerating dimensions or model code.
