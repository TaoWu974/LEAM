# Artifact Schemas

## Parameters

CST parameter artifact is VBA:

```vba
Dim names(1 To N) As String
Dim values(1 To N) As String
names(1) = "W_sub"  ' Substrate width
values(1) = "30"
StoreParameters(names, values)
```

HFSS parameter artifact is PyAEDT variable assignment:

```python
hfss["$W_sub"] = "30mm"
hfss["$L_sub"] = "20mm"
hfss["$x_offset"] = "($W_sub-$W_patch)/2"
```

Rules:

- Include only geometric or dimensional variables used by geometry construction.
- Exclude frequency, wavelength, relative permittivity, loss tangent, conductivity, impedance, booleans, flags, counters, and notes.
- Use explicit user values when available.
- If physics-derived dimensions are needed, compute numeric dimensions first. Do not emit undefined constants such as `c`, `eps0`, or `$f0`.
- Preserve exact geometry-to-geometry relationships when meaningful.

## Materials

CST material selections use this JSON shape for non-built-in/imported materials:

```json
{
  "representation": "materials",
  "items": [
    {"name": "Rogers RO4003C (lossy)", "file": "Rogers RO4003C (lossy).mtd"},
    {"name": "Copper (pure)", "file": "Copper (pure).mtd"}
  ]
}
```

HFSS material selections use this JSON shape:

```json
{
  "representation": "materials",
  "items": [
    {"name": "vacuum", "source": "builtin", "builtin": true, "notes": ""},
    {"name": "pec", "source": "builtin", "builtin": true, "notes": ""},
    {"name": "Rogers RO4003C (lossy)", "source": "syslibrary", "builtin": false, "notes": ""}
  ]
}
```

If full custom HFSS material properties are supplied and the user asks for a material creation script, emit an optional `materials.py` artifact:

```python
material = hfss.materials.add_material("FR-4 (lossy)")
material.permittivity = "4.3"
material.permeability = "1.0"
material.loss_tangent = "0.025"
```

Rules:

- Use exact library names when provided by the user or source context.
- CST built-ins: `Vacuum`, `PEC`; omit these from `materials.json` because they do not require import macros.
- HFSS built-ins: `vacuum`, `pec`.
- If conductor is unspecified, use the backend convention: CST defaults to `Copper (pure)` when available and falls back to `PEC` when not; HFSS may use `pec`.
- Do not create custom materials unless the full material properties are explicitly supplied.

## Solids

Return JSON only:

```json
{
  "solids": [
    {
      "Type": "3D",
      "name": "Substrate",
      "Role": "Dielectric",
      "material": "Rogers RO4003C (lossy)",
      "dimensions": {
        "shape": "brick",
        "x_range": ["0", "W_sub"],
        "y_range": ["0", "L_sub"],
        "z_range": ["0", "ts"]
      },
      "operations": [],
      "notes": "Origin at lower-left bottom corner."
    }
  ]
}
```

Rules:

- `Type` must be exactly `3D` or `2.5D`.
- One item per final solid or boolean tool solid.
- Referenced solid names in `operations` must exactly match actual solid names.
- Do not include an air box.
- Slots and cutouts should be actual vacuum tool solids so boolean subtraction can use them later.

## Check Solid

Return a status-bearing JSON report:

```json
{
  "status": "issues",
  "issues": [
    {
      "category": "geometry",
      "severity": "error",
      "solid": "SlotTool",
      "path": "solids[3].dimensions",
      "route_to": "solids",
      "issue": "Slot length contradicts the parameter table."
    }
  ],
  "issue_counts": {"total": 1, "errors": 1, "warnings": 0}
}
```

Use `status: "ok"` and an empty issue list when acceptable:

```json
{
  "status": "ok",
  "issues": [],
  "issue_counts": {"total": 0, "errors": 0, "warnings": 0}
}
```

Warnings may be included, but only non-warning issues should block downstream regeneration.

## Dimensions

Return JSON only:

```json
{
  "solids": [
    {
      "Type": "3D",
      "name": "Patch",
      "reference": "Brick",
      "coordinates": {"x": 0, "y": 0, "z": 0},
      "dimensions": {
        "x_range": ["x_patch_min", "x_patch_max"],
        "y_range": ["y_patch_min", "y_patch_max"],
        "z_range": ["ts", "ts+tm"]
      },
      "notes": "Xmin=(W_sub-W_patch)/2, Xmax=(W_sub+W_patch)/2."
    }
  ]
}
```

For 2.5D:

```json
{
  "Type": "2.5D",
  "name": "TaperedSlotTool",
  "reference": "Extrude",
  "coordinates": {"x": 0, "y": 0, "z": 0},
  "dimensions": {
    "shape": "Extrude (closed profile)",
    "profile_plane": "z = ts",
    "profile": {
      "kind": "spline",
      "points": [{"x": "x1", "y": "L_sub"}, {"x": "x2", "y": "L_sub-1"}],
      "closed": true,
      "constraints": "right side mirrored by W_sub-x_i"
    },
    "z_range": ["ts", "ts+tm"]
  },
  "notes": "Vacuum tool solid for subtracting tapered slot from patch."
}
```

Rules:

- Avoid vague placement words like "centered" or "on top of"; resolve them into ranges.
- For boxes/bricks, specify Xmin/Xmax/Ymin/Ymax/Zmin/Zmax.
- For cylinders, specify axis, center, radius, and z/range.
- If unknown, define a parameter rather than omit the dimension.
