# HFSS PyAEDT Guidance

## General Output Rules

- Output pure Python/PyAEDT operation lines for code artifacts.
- Do not include imports, wrappers, `if __name__ == "__main__"`, prose, markdown fences, `oEditor`, `ScriptEnv`, or IronPython APIs.
- Assume active objects such as `hfss`, `aedtapp`, and `PolylineSegment` are available in the execution context.
- Use project-level variables with `$` prefix.
- Include AEDT units in physical dimensions, such as `mm` and `deg`.
- Fail fast: if a mutating PyAEDT call returns `False`, raise `RuntimeError`.

## Parameters

```python
hfss["$W_sub"] = "30mm"
hfss["$L_sub"] = "20mm"
hfss["$x_patch"] = "($W_sub-$W_patch)/2"
```

Rules:

- Emit only geometric variables.
- Exclude frequency, wavelength, material properties, impedance, and constants.
- Preserve useful expressions like `($W_sub-$W_patch)/2`.
- Use AEDT functions such as `abs`, `sqrt`, `pow`, `ln`, `log10`, `sin`, `cos`, `tan`, `atan2`, and constants such as `pi` only when needed.

## Materials

Use exact names from material context. Built-ins are `vacuum` and `pec`.

Do not create materials in geometry steps. If full custom material properties are explicitly supplied, use:

```python
material = hfss.materials.add_material("FR-4 (lossy)")
material.permittivity = "4.3"
material.permeability = "1.0"
material.loss_tangent = "0.025"
```

Do not recreate `vacuum` or `pec`.

## 3D Solids

Model only `Type="3D"` solids. Do not perform boolean operations here.

Box:

```python
obj = hfss.modeler.create_box(
    origin=["0mm", "0mm", "0mm"],
    sizes=["$W_sub", "$L_sub", "$ts"],
    name="Substrate",
    material="Rogers RO4003C (lossy)",
)
if obj is False:
    raise RuntimeError("Failed to create Substrate.")
```

Cylinder:

```python
obj = hfss.modeler.create_cylinder(
    orientation="Z",
    origin=["$x_probe", "$y_probe", "0mm"],
    radius="$r_probe",
    height="$ts+$tm",
    name="Probe",
    material="pec",
)
if obj is False:
    raise RuntimeError("Failed to create Probe.")
```

Sphere:

```python
obj = hfss.modeler.create_sphere(
    origin=["$x_load", "$y_load", "$z_load"],
    radius="$r_load",
    name="LoadSphere",
    material="pec",
)
if obj is False:
    raise RuntimeError("Failed to create LoadSphere.")
```

Cone:

```python
obj = hfss.modeler.create_cone(
    orientation="Z",
    origin=["$x_post", "$y_post", "$z_min"],
    bottom_radius="$r_bottom",
    top_radius="$r_top",
    height="$z_max-$z_min",
    name="TaperedPost",
    material="pec",
)
if obj is False:
    raise RuntimeError("Failed to create TaperedPost.")
```

Torus:

```python
obj = hfss.modeler.create_torus(
    origin=["$x_ring", "$y_ring", "$z_ring"],
    major_radius="$r_major",
    minor_radius="$r_minor",
    axis="Z",
    name="Ring",
    material="pec",
)
if obj is False:
    raise RuntimeError("Failed to create Ring.")
```

Regular polyhedron:

```python
obj = hfss.modeler.create_polyhedron(
    orientation="Z",
    center=["$x_poly", "$y_poly", "$z_min"],
    origin=["$x_poly+$r_poly", "$y_poly", "$z_min"],
    height="$h_poly",
    num_sides=6,
    name="HexPost",
    material="pec",
)
if obj is False:
    raise RuntimeError("Failed to create HexPost.")
```

Bondwire:

```python
obj = hfss.modeler.create_bondwire(
    start=["$x1", "$y1", "$z1"],
    end=["$x2", "$y2", "$z2"],
    h1="$h_bond1",
    h2="$h_bond2",
    alpha=75,
    beta=4,
    bond_type=0,
    diameter="$d_bond",
    facets=6,
    name="BondwireFeed",
    material="pec",
)
if obj is False:
    raise RuntimeError("Failed to create BondwireFeed.")
```

Use bondwire only when the source describes a curved wire/bond-style feed. Otherwise use cylinders, boxes, or 2.5D profiles.

## 2.5D Solids

Model only `Type="2.5D"` solids. Create one closed contour per solid, then cover and thicken it.

```python
points = [
    ["$x1", "$y1", "$ts"],
    ["$x2", "$y2", "$ts"],
    ["$x3", "$y3", "$ts"],
    ["$x1", "$y1", "$ts"],
]
profile = hfss.modeler.create_polyline(
    points=points,
    segment_type=None,
    close_surface=False,
    name="SlotProfile",
)
if profile is False:
    raise RuntimeError("Failed to create SlotProfile.")
result = hfss.modeler.cover_lines(assignment="SlotProfile")
if result is False:
    raise RuntimeError("Failed to cover SlotProfile.")
solid = hfss.modeler.thicken_sheet(
    assignment="SlotProfile",
    thickness="$tm",
    both_sides=False,
)
if solid is False:
    raise RuntimeError("Failed to thicken SlotProfile.")
hfss.modeler["SlotProfile"].material_name = "vacuum"
```

Compound spline/line contour:

```python
profile = hfss.modeler.create_polyline(
    points=points,
    segment_type=[
        PolylineSegment(segment_type="Spline", num_points=4),
        PolylineSegment(segment_type="Line"),
        PolylineSegment(segment_type="Spline", num_points=4),
        PolylineSegment(segment_type="Line"),
    ],
    close_surface=False,
    name="TaperedSlotTool",
)
```

Circle sheet:

```python
sheet = hfss.modeler.create_circle(
    orientation="Z",
    origin=["$x_via", "$y_via", "$ts"],
    radius="$r_via",
    num_sides=0,
    is_covered=True,
    name="CircularToolSheet",
    material="vacuum",
)
if sheet is False:
    raise RuntimeError("Failed to create CircularToolSheet.")
solid = hfss.modeler.thicken_sheet(
    assignment="CircularToolSheet",
    thickness="$tm",
    both_sides=False,
)
if solid is False:
    raise RuntimeError("Failed to thicken CircularToolSheet.")
```

Ellipse sheet:

```python
sheet = hfss.modeler.create_ellipse(
    origin=["$x_slot", "$y_slot", "$ts"],
    major_radius="$rx_slot",
    ratio="$ry_slot/$rx_slot",
    is_covered=True,
    name="EllipticalToolSheet",
    material="vacuum",
)
if sheet is False:
    raise RuntimeError("Failed to create EllipticalToolSheet.")
solid = hfss.modeler.thicken_sheet(
    assignment="EllipticalToolSheet",
    thickness="$tm",
    both_sides=False,
)
if solid is False:
    raise RuntimeError("Failed to thicken EllipticalToolSheet.")
```

Rules:

- Repeat the first point at the end to close the contour.
- Use one flat ordered `points` list for the whole contour.
- If target `z_range` is explicit, create the profile at that z plane and thicken to the correct thickness; do not sketch at `z=0` and move later unless unavoidable.
- Current distilled workflow supports extruded profiles; avoid rotate-based construction unless the user explicitly needs it and accepts manual review.

## Transform Operations

Use object transforms only inside model-generation steps when placement or repeated geometry requires them. Do not place transforms in the boolean artifact.

Move:

```python
result = hfss.modeler["SlotTool"].move(
    vector=["0mm", "0mm", "$ts"],
)
if result is False:
    raise RuntimeError("Failed to move SlotTool.")
```

Rotate:

```python
result = hfss.modeler["RotatedPatch"].rotate(
    axis="Z",
    angle="$theta",
)
if result is False:
    raise RuntimeError("Failed to rotate RotatedPatch.")
```

Mirror:

```python
result = hfss.modeler["MirroredArm"].mirror(
    origin=["0mm", "0mm", "0mm"],
    vector=["1mm", "0mm", "0mm"],
    duplicate=False,
)
if result is False:
    raise RuntimeError("Failed to mirror MirroredArm.")
```

Duplicate along a line:

```python
result = hfss.modeler["Via"].duplicate_along_line(
    vector=["$via_pitch", "0mm", "0mm"],
    clones=4,
    attach=False,
)
if result is False:
    raise RuntimeError("Failed to duplicate Via along line.")
```

Duplicate around an axis:

```python
result = hfss.modeler["ArrayElement"].duplicate_around_axis(
    axis="Z",
    angle="90deg",
    clones=4,
    create_new_objects=True,
)
if result is False:
    raise RuntimeError("Failed to duplicate ArrayElement around axis.")
```

## Boolean Operations

Only in the boolean artifact:

```python
result = hfss.modeler.unite(
    assignment=["Feed", "Patch"],
    keep_originals=False,
)
if result is False:
    raise RuntimeError("Unite failed for Feed and Patch.")

result = hfss.modeler.subtract(
    blank_list=["Patch"],
    tool_list=["SlotTool"],
    keep_originals=False,
)
if result is False:
    raise RuntimeError("Subtract failed for Patch minus SlotTool.")

result = hfss.modeler.intersect(
    assignment=["A", "B"],
    keep_originals=False,
)
if result is False:
    raise RuntimeError("Intersect failed for A and B.")

result = hfss.modeler.split(
    assignment=["Ground"],
    plane="XY",
    sides="PositiveOnly",
)
if result is False:
    raise RuntimeError("Split failed for Ground on the XY plane.")

result = hfss.modeler.imprint(
    blank_list=["Patch"],
    tool_list=["ImprintTool"],
    keep_originals=False,
)
if result is False:
    raise RuntimeError("Imprint failed for Patch and ImprintTool.")
```

Supported operations include `unite`, `subtract`, `intersect`, `split`, and `imprint`.

Do not move, rotate, mirror, or otherwise transform objects in the boolean step.

## Parameter Updates

Only update changed project variables:

```python
hfss["$W_slot"] = "1.2mm"
hfss["$L_feed"] = "$L_feed+0.5mm"
```

Do not include rebuild calls, imports, wrappers, comments, or unchanged variables.
