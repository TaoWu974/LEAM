# 2.5D (Planar) Curve Reference

## Line
create_polyline(points: list, segment_type: PolylineSegment | list = None, cover_surface: bool = False, close_surface: bool = False, name: str | None = None, material: str | None = None, xsection_type: str = None, xsection_orient: str = None, xsection_width: int = 1, xsection_topwidth: int = 1, xsection_height: int = 1, xsection_num_seg: int = 0, xsection_bend_type: str = None, non_model: bool = False)

Parameters:
pointslist
Array of positions of each point of the polyline. A position is a list of 2D or 3D coordinates. Position coordinate values can be numbers or valid AEDT string expressions. For example, [0, 1, 2], ["0mm", "5mm", "1mm"], or ["x1", "y1", "z1"].

segment_typestr or PolylineSegment or list, optional
The default behavior is to connect all points as "Line" segments. The default is None. Use a "PolylineSegment", for "Line", "Arc", "Spline", or "AngularArc". A list of segment types (str or ansys.aedt.core.modeler.cad.primitives.PolylineSegment) is valid for a compound polyline.

cover_surfacebool, optional
The default is False.

close_surfacebool, optional
The default is False, which automatically joins the starting and ending points.

namestr, optional
Name of the polyline. The default is None.

materialstr, optional
Name of the material. The default is None, in which case the default material is assigned.

xsection_typestr, optional
Type of the cross-section. Options are "Line", "Circle", "Rectangle", and "Isosceles Trapezoid". The default is None.

xsection_orientstr, optional
Direction of the normal vector to the width of the cross-section. Options are "X", "Y", "Z", and "Auto". The default is None, which sets the direction to "Auto".

xsection_widthfloat or str, optional
Width or diameter of the cross-section for all types. The default is 1.

xsection_topwidthfloat or str, optional
Top width of the cross-section for type "Isosceles Trapezoid" only. The default is 1.

xsection_heightfloat or str
Height of the cross-section for type "Rectangle" or "Isosceles Trapezoid" only. The default is 1.

xsection_num_segint, optional
Number of segments in the cross-section surface for type "Circle", "Rectangle", or "Isosceles Trapezoid". The default is 0. The value must be 0 or greater than 2.

xsection_bend_typestr, optional
Type of the bend for the cross-section. The default is None, in which case the bend type is set to "Corner". For the type "Circle", the bend type should be set to "Curved".

non_modelbool, optional
Either if the polyline will be created as model or unmodel object.

```python
test_points = [
    ["0mm", "0mm", "0mm"],
    ["100mm", "20mm", "0mm"],
    ["71mm", "71mm", "0mm"],
    ["0mm", "100mm", "0mm"],
]

polyline = hfss.modeler.create_polyline(test_points, name="PL_line_segments")
```

## Closed Extruded Profile
```python
spline_profile_points = [
    [0, 0, "$ts"],
    [10, 10, "$ts"],
    [20, 10, "$ts"],
    [30, 0, "$ts"],
    [35, -5, "$ts"],
    [25, -15, "$ts"],
    [10, -15, "$ts"],
    [0, -5, "$ts"],
    [0, 0, "$ts"],
]

spline_profile_tool = hfss.modeler.create_polyline(
    points=spline_profile_points,
    segment_type=[
        PolylineSegment(segment_type="Spline", num_points=4),
        PolylineSegment(segment_type="Line"),
        PolylineSegment(segment_type="Spline", num_points=4),
        PolylineSegment(segment_type="Line"),
    ],
    close_surface=False,
    name="SplineLineSplineLineTool",
)
hfss.modeler.cover_lines(assignment="SplineLineSplineLineTool")
hfss.modeler.thicken_sheet(
    assignment="SplineLineSplineLineTool",
    thickness="$tp",
    both_sides=False,
)
```

## Circle
create_circle(orientation: str | int | Plane, origin: list, radius: float | int | str, num_sides: int = 0, is_covered: bool = True, name: str = None, material: str = None, non_model: bool = False, **kwargs)
```python
circle_object = hfss.modeler.create_circle(
    orientation="Z",
    origin=[0, 0, 0],
    radius=2,
    num_sides=8,
    name="mycyl",
    material="vacuum",
)
```

## Ellipse
create_ellipse(origin: list, major_radius: float | str, ratio: float, is_covered: bool = True, name: str | None = None, material: str | None = None, non_model: bool = False, segments: int = 0, **kwargs)
```python
ellipse1 = hfss.modeler.create_ellipse([0, -2, -2], 4.0, 0.2)
ellipse2 = hfss.modeler.create_ellipse(
    origin=[0, -2, -2],
    major_radius=4.0,
    ratio=0.2,
    name="MyEllipse",
    material="Copper",
)
```
