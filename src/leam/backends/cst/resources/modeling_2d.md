# 2.5D (Planar) Curve Reference

## Line
```vba
With Line
     .Reset 
     .Name "line1" 
     .Curve "curve1" 
     .X1 "-6" 
     .Y1 "4" 
     .X2 "-0" 
     .Y2 "4" 
     .Create
End With
```

## Polygon
```vba
With Polygon 
     .Reset 
     .Name "polygon1" 
     .Curve "curve1" 
     .Point "-6", "2" 
     .LineTo "-6", "-2" 
     .LineTo "-0", "-2" 
     .LineTo "0", "2" 
     .LineTo "-6", "2" 
     .Create 
End With
```

## Spline
```vba
With Spline 
     .Reset 
     .Name "spline1" 
     .Curve "curve1" 
     .Point "-6", "-6.5" 
     .SetInterpolationType "PointInterpolation" 
     .LineTo "-4", "-9" 
     .LineTo "-2", "-7" 
     .LineTo "-0", "-9" 
     .LineTo "1", "-7" 
     .Create 
End With
```

## Circle
```vba
With Circle
     .Reset 
     .Name "circle1" 
     .Curve "curve1" 
     .Radius "2" 
     .Xcenter "6" 
     .Ycenter "4" 
     .Segments "0" 
     .Create
End With
```

## Ellipse
```vba
With Ellipse
     .Reset 
     .Name "ellipse1" 
     .Curve "curve1" 
     .XRadius "4" 
     .YRadius "2" 
     .Xcenter "-3" 
     .Ycenter "8" 
     .Segments "0" 
     .Create
End With
```

## Arc
```vba
With Arc
     .Reset 
     .Name "arc1" 
     .Curve "curve1" 
     .Orientation "Clockwise" 
     .XCenter "-4" 
     .YCenter "4" 
     .X1 "-4" 
     .Y1 "2" 
     .X2 "-2" 
     .Y2 "4" 
     .Angle "270" 
     .UseAngle "True" 
     .Segments "0" 
     .Create
End With
```

## Analytical Line
```vba
With AnalyticalCurve
     .Reset 
     .Name "analytical1" 
     .Curve "curve1" 
     .LawX "t*2" 
     .LawY "t*2" 
     .LawZ "0" 
     .ParameterRange "0", "5" 
     .Create
End With
```