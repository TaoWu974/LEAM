# Weak D2Solids Prompt

## Role
You are an expert in HFSS software and antenna design.

## Input
A simple description of an antenna from a beginner.

## Goal
List each separate solid needed to design an antenna in HFSS. Prefer 3D solids whenever possible and only use 2.5D when a shape cannot be represented by a built-in 3D primitive. Determine appropriate materials, dimensions, and position relationships based on standard design practices.

## Definitions
- 3D: can be created directly with a built-in HFSS 3D solid command (e.g., Box, Cylinder, Cone, Sphere, Torus, Prism, Elliptical Cylinder).
- 2.5D: requires creating a planar sketch (polygon/spline/curve) and then Extrude or Rotate to form a solid.

## Output Format (JSON ONLY)
Return valid JSON and nothing else (no markdown, no prose), with this shape:
```json
{
  "solids": [
    {
      "Type": "3D",
      "name": "string",
      "Role": "string (functional role: Feeding/Radiating/Ground/Dielectric/Cutout/etc.)",
      "material": "string",
      "dimensions": { "any": "object with parametric dimensions/relationships" },
      "operations": ["string"],
      "notes": "string"
    }
  ]
}
```

## Rules
0) Type must be exactly "3D" or "2.5D".
1) One item per final HFSS solid. Prefer 3D solids whenever a primitive can represent the shape (e.g., rectangular patches, ground planes, slots, and feed lines should be thin Box solids with copper thickness).
   - For 3D: one item per HFSS 3D solid creation command (Box/Cylinder/etc.).
   - For 2.5D: one item per resulting solid created by extrude/rotate (include the planar profile definition + the extrude/rotate instruction in dimensions).
2) Use parametric dimensions/relationships when possible.
3) Use 2.5D only when a built-in 3D primitive cannot represent the solid (e.g., splines, curved outlines, irregular polygons). If you do use 2.5D, include them as separate solids with Type = "2.5D" (do not only mention them in notes/operations).
4) If you mention another solid in operations (e.g., boolean subtract), the referenced name must exactly match the target solid's name.
5) Do not include an air box.
