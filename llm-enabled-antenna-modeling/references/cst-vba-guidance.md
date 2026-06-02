# CST VBA Guidance

## General Output Rules

- Output VBA only for code artifacts.
- Do not include `Sub Main`, `End Sub`, function wrappers, prose, or simulation setup.
- Geometry code should start directly with `With Brick`, `With Cylinder`, `With ExtrudeCurve`, `With Transform`, or `Solid.*`.
- Use component name `component1` unless the user specifies a different component.
- Do not use units in CST parameter values or ranges.

## Parameters

Use:

```vba
Dim names(1 To 2) As String
Dim values(1 To 2) As String
names(1) = "W_sub"  ' Substrate width
values(1) = "30"
names(2) = "L_sub"  ' Substrate length
values(2) = "20"
StoreParameters(names, values)
```

Rules:

- Keep array sizes exactly consistent.
- One `names(i)` and `values(i)` per emitted variable.
- Include short geometric comments.
- Do not emit material, frequency, dielectric, or solver variables.

## Materials

Use existing material names where possible. CST built-ins are `Vacuum` and `PEC`.

If custom material properties are explicitly provided, create one `With Material` block per material:

```vba
With Material
    .Reset
    .Name "FR-4 (lossy)"
    .Folder ""
    .FrqType "all"
    .Type "Normal"
    .SetMaterialUnit "GHz", "mm"
    .Epsilon "4.3"
    .Mu "1.0"
    .TanD "0.025"
    .TanDGiven "True"
    .Create
End With
```

Do not fabricate material properties.

## 3D Solids

Model only `Type="3D"` solids. Do not perform boolean operations here.

Brick:

```vba
With Brick
     .Reset
     .Name "Substrate"
     .Component "component1"
     .Material "Rogers RO4003C (lossy)"
     .Xrange "0", "W_sub"
     .Yrange "0", "L_sub"
     .Zrange "0", "ts"
     .Create
End With
```

Cylinder:

```vba
With Cylinder
     .Reset
     .Name "Probe"
     .Component "component1"
     .Material "PEC"
     .OuterRadius "r_probe"
     .InnerRadius "0"
     .Axis "z"
     .Zrange "0", "ts+tm"
     .Xcenter "x_probe"
     .Ycenter "y_probe"
     .Segments "0"
     .Create
End With
```

Other supported primitives include `Sphere`, `Cone`, `Torus`, `Cylinder` with `Segments` for prisms, and `ECylinder` for elliptical cylinders.

Sphere:

```vba
With Sphere
     .Reset
     .Name "LoadSphere"
     .Component "component1"
     .Material "PEC"
     .Axis "z"
     .CenterRadius "r_load"
     .TopRadius "0"
     .BottomRadius "0"
     .Center "x_load", "y_load", "z_load"
     .Segments "0"
     .Create
End With
```

Cone:

```vba
With Cone
     .Reset
     .Name "TaperedPost"
     .Component "component1"
     .Material "PEC"
     .BottomRadius "r_bottom"
     .TopRadius "r_top"
     .Axis "z"
     .Zrange "z_min", "z_max"
     .Xcenter "x_post"
     .Ycenter "y_post"
     .Segments "0"
     .Create
End With
```

Torus:

```vba
With Torus
     .Reset
     .Name "Ring"
     .Component "component1"
     .Material "PEC"
     .OuterRadius "r_outer"
     .InnerRadius "r_inner"
     .Axis "z"
     .Xcenter "x_ring"
     .Ycenter "y_ring"
     .Zcenter "z_ring"
     .Segments "0"
     .Create
End With
```

Elliptical cylinder:

```vba
With ECylinder
     .Reset
     .Name "EllipticalPatch"
     .Component "component1"
     .Material "Copper (pure)"
     .Xradius "rx_patch"
     .Yradius "ry_patch"
     .Axis "z"
     .Zrange "ts", "ts+tm"
     .Xcenter "x_patch"
     .Ycenter "y_patch"
     .Segments "0"
     .Create
End With
```

Analytical face for explicitly mathematical surfaces:

```vba
With AnalyticalFace
     .Reset
     .Name "CurvedSheet"
     .Component "component1"
     .Material "PEC"
     .LawX "u"
     .LawY "v"
     .LawZ "z0 + a*(u^2-v^2)"
     .ParameterRangeU "u_min", "u_max"
     .ParameterRangeV "v_min", "v_max"
     .Create
End With
```

Use analytical faces only when the user provides an explicit surface equation or enough constraints to define one.

## 2.5D Solids

Model only `Type="2.5D"` solids. Define planar curves and extrude/rotate them. Do not perform boolean operations here.

Closed polygon plus extrude:

```vba
With Polygon
     .Reset
     .Name "SlotProfile"
     .Curve "curve1"
     .Point "x1", "y1"
     .LineTo "x2", "y2"
     .LineTo "x3", "y3"
     .LineTo "x1", "y1"
     .Create
End With

With ExtrudeCurve
     .Reset
     .Name "SlotTool"
     .Component "component1"
     .Material "Vacuum"
     .Thickness "tm"
     .Twistangle "0.0"
     .Taperangle "0.0"
     .DeleteProfile "True"
     .Curve "curve1:SlotProfile"
     .Create
End With
```

If `ExtrudeCurve` creates the shape from `z=0` to thickness but the target is offset, immediately translate with `Transform`.

Use splines for curved profiles rather than polygon approximations when the description provides spline/curve intent.

Planar profile primitives:

```vba
With Line
     .Reset
     .Name "FeedEdge"
     .Curve "curve1"
     .X1 "x1"
     .Y1 "y1"
     .X2 "x2"
     .Y2 "y2"
     .Create
End With
```

```vba
With Spline
     .Reset
     .Name "TaperEdge"
     .Curve "curve1"
     .Point "x1", "y1"
     .SetInterpolationType "PointInterpolation"
     .LineTo "x2", "y2"
     .LineTo "x3", "y3"
     .LineTo "x4", "y4"
     .Create
End With
```

```vba
With Circle
     .Reset
     .Name "ViaProfile"
     .Curve "curve1"
     .Radius "r_via"
     .Xcenter "x_via"
     .Ycenter "y_via"
     .Segments "0"
     .Create
End With
```

```vba
With Ellipse
     .Reset
     .Name "EllipticalSlotProfile"
     .Curve "curve1"
     .XRadius "rx_slot"
     .YRadius "ry_slot"
     .Xcenter "x_slot"
     .Ycenter "y_slot"
     .Segments "0"
     .Create
End With
```

```vba
With Arc
     .Reset
     .Name "ArcEdge"
     .Curve "curve1"
     .Orientation "Clockwise"
     .XCenter "x_c"
     .YCenter "y_c"
     .X1 "x_start"
     .Y1 "y_start"
     .X2 "x_end"
     .Y2 "y_end"
     .Angle "theta_arc"
     .UseAngle "True"
     .Segments "0"
     .Create
End With
```

```vba
With AnalyticalCurve
     .Reset
     .Name "AnalyticalEdge"
     .Curve "curve1"
     .LawX "x0 + t"
     .LawY "y0 + a*t^2"
     .LawZ "0"
     .ParameterRange "t_min", "t_max"
     .Create
End With
```

Rotate a closed planar point list when the solid is explicitly a revolved profile:

```vba
With Rotate
     .Reset
     .Name "RevolvedSolid"
     .Component "component1"
     .Material "PEC"
     .Mode "Pointlist"
     .StartAngle "0.0"
     .Angle "360"
     .Height "0.0"
     .RadiusRatio "1.0"
     .NSteps "0"
     .SplitClosedEdges "True"
     .SegmentedProfile "False"
     .SimplifySolid "False"
     .UseAdvancedSegmentedRotation "True"
     .CutEndOff "False"
     .Origin "0.0", "0.0", "0.0"
     .Rvector "0.0", "1.0", "0.0"
     .Zvector "1.0", "0.0", "0.0"
     .Point "x1", "y1"
     .LineTo "x2", "y2"
     .LineTo "x3", "y3"
     .LineTo "x1", "y1"
     .Create
End With
```

## Transform Operations

Use transform code only inside model-generation steps when placement requires it. Do not put transforms in the boolean artifact unless the user explicitly requested a boolean-step transform.

Translate:

```vba
With Transform
     .Reset
     .Name "component1:SlotTool"
     .Vector "0", "0", "ts"
     .UsePickedPoints "False"
     .InvertPickedPoints "False"
     .MultipleObjects "False"
     .GroupObjects "False"
     .Repetitions "1"
     .MultipleSelection "False"
     .Destination ""
     .Material ""
     .AutoDestination "True"
     .Transform "Shape", "Translate"
End With
```

Scale:

```vba
With Transform
     .Reset
     .Name "component1:ScaledSolid"
     .Origin "Free"
     .Center "0", "0", "0"
     .ScaleFactor "sx", "sy", "sz"
     .MultipleObjects "False"
     .GroupObjects "False"
     .Repetitions "1"
     .MultipleSelection "False"
     .AutoDestination "True"
     .Transform "Shape", "Scale"
End With
```

Rotate:

```vba
With Transform
     .Reset
     .Name "component1:RotatedSolid"
     .Origin "Free"
     .Center "x0", "y0", "z0"
     .Angle "0", "0", "theta"
     .MultipleObjects "False"
     .GroupObjects "False"
     .Repetitions "1"
     .MultipleSelection "False"
     .AutoDestination "True"
     .Transform "Shape", "Rotate"
End With
```

Mirror:

```vba
With Transform
     .Reset
     .Name "component1:MirroredSolid"
     .Origin "Free"
     .Center "0", "0", "0"
     .PlaneNormal "0", "1", "0"
     .MultipleObjects "True"
     .GroupObjects "False"
     .Repetitions "1"
     .MultipleSelection "False"
     .Destination ""
     .Material ""
     .AutoDestination "True"
     .Transform "Shape", "Mirror"
End With
```

## Boolean Operations

Only in the boolean artifact:

```vba
Solid.Add "component1:Feed", "component1:Patch"
Solid.Subtract "component1:Patch", "component1:SlotTool"
Solid.Intersect "component1:A", "component1:B"
Solid.Insert "component1:Host", "component1:InsertedSolid"
Solid.Imprint "component1:Patch", "component1:ImprintTool"
Solid.Delete "component1:TemporaryHelper"
```

Rules:

- Use exact existing solid names.
- Boolean subtract deletes the tool solid automatically in this workflow; do not generate `.Delete` or `Solid.Delete` lines after subtract.
- Use `Solid.Delete` only when the user explicitly asks to remove an object that is not already consumed by another boolean operation.
- Do not transform geometry in this step.

## Parameter Updates

Only update variables that change:

```vba
StoreParameter "W_slot", 1.2
StoreParameter "L_feed", "L_feed+0.5"
Rebuild
```

Do not include unchanged parameters, units, wrappers, or prose.
