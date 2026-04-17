# Extrude Reference

## Cover_lines
cover_lines(assignment) → bool
Cover closed lines and transform them to a sheet.

Parameters:
assignmentstr, int
Polyline object to cover.

Returns:
bool
True when successful, False when failed

## Thicken One Sheet
thicken_sheet(assignment: str | int | list | Object3d, thickness: float | str, both_sides: bool = False)
```python
solid = hfss.modeler.thicken_sheet(
    assignment="Polyline4",
    thickness="0.03mm",
    both_sides=False,
)
```