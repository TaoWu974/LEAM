# Distilled Examples

## Vivaldi Antenna Pattern

Use `strong_description`, usually with 2.5D enabled.

Typical solids:

- Dielectric substrate brick.
- Front copper cover patch brick.
- Tapered slot vacuum tool from closed spline profile, extruded through metal thickness.
- Circular slot vacuum cylinder/tool.
- Back feed rectangles as thin copper bricks.
- Back circular feed element as thin cylinder.

Important modeling lessons:

- Define a clear origin, often lower-left bottom of substrate.
- Tapered slot should be 2.5D when defined by spline points.
- Mirror right spline points as `W_sub - x_i` when symmetry is specified.
- Boolean step subtracts slot tools from patch and unites/adds feed pieces as needed.
- Feed rectangles and circular feed should use exact ranges and overlap where connected.

## Slotted Rectangular Patch Pattern

Use `weak_description` when only frequency/intent is provided.

Typical solids:

- Substrate brick.
- Ground plane brick.
- Radiating patch brick.
- Microstrip feed brick.
- Slot vacuum bricks or 2.5D profile tools depending on slot shape.

Important modeling lessons:

- High-level frequency alone is not a full geometry; infer first-pass dimensions and mark assumptions.
- Rectangular slots can be 3D vacuum bricks.
- Centered placement must become explicit coordinate ranges.
- Do not include solver setup unless requested.

## Slotted Monopole Paper Reconstruction Pattern

Use `paper_reconstruction`.

Typical solids:

- FR-4 substrate brick.
- Driven circular patch radiator cylinder/thin metal.
- Microstrip feed brick.
- Coplanar partial ground rectangles.
- Quasi-cross slot vacuum tools in the circular radiator.

Important modeling lessons:

- Preserve parameter-table symbols where possible.
- Correct known figure/table inconsistencies explicitly as assumptions.
- Slot length/width orientation must be mapped to axes: horizontal slot on x-axis, vertical slot on y-axis.
- Boolean step should add/unite feed to radiator if needed, then subtract slot tools from radiator.

## Output Packaging Pattern

For a full response, organize artifacts like:

```text
assumptions.md
parameters.bas or parameters.py
parameters.json
materials.json
solids.json
solids_check.json
dimensions.json
model_3d.bas or model_3d.py
model_2d.bas or model_2d.py
boolean.bas or boolean.py
parameter_update.bas or parameter_update.py
validation_notes.md
```

If the user asks for inline output rather than files, present each artifact under a clear heading and keep code blocks separate.
