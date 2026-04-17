# 3D Modeling Reference (Main Focus)

## New Cuboid (Brick)
```vba
With Brick
     .Reset 
     .Name "solid1" 
     .Component "component1" 
     .Material "PEC" 
     .Xrange "-2", "2" 
     .Yrange "-2", "2" 
     .Zrange "0", "4" 
     .Create
End With
```

## Cylinder
```vba
With Cylinder 
     .Reset 
     .Name "solid5" 
     .Component "component1" 
     .Material "PEC" 
     .OuterRadius "1" 
     .InnerRadius "0" 
     .Axis "z" 
     .Zrange "0", "6" 
     .Xcenter "-17" 
     .Ycenter "-3" 
     .Segments "0" 
     .Create 
End With
```

# 3D Modeling Reference (Low focus)
## New Sphere
```vba
With Sphere 
     .Reset 
     .Name "solid2" 
     .Component "component1" 
     .Material "PEC" 
     .Axis "z" 
     .CenterRadius "2" 
     .TopRadius "0" 
     .BottomRadius "0" 
     .Center "-6", "8", "0" 
     .Segments "0" 
     .Create 
End With
```

## New Cone
```vba
With Cone 
     .Reset 
     .Name "solid3" 
     .Component "component1" 
     .Material "PEC" 
     .BottomRadius "3" 
     .TopRadius "1" 
     .Axis "z" 
     .Zrange "0", "5" 
     .Xcenter "10" 
     .Ycenter "7" 
     .Segments "0" 
     .Create 
End With
```

## New Torus
```vba
With Torus 
     .Reset 
     .Name "solid4" 
     .Component "component1" 
     .Material "PEC" 
     .OuterRadius "3" 
     .InnerRadius "1" 
     .Axis "z" 
     .Xcenter "5" 
     .Ycenter "-7" 
     .Zcenter "0" 
     .Segments "0" 
     .Create 
End With
```

## Prism
Note: Segments controls the polygon edge count.
```vba
With Cylinder 
     .Reset 
     .Name "solid6" 
     .Component "component1" 
     .Material "PEC" 
     .OuterRadius "1.5" 
     .InnerRadius "1" 
     .Axis "z" 
     .Zrange "0", "9" 
     .Xcenter "-15" 
     .Ycenter "0.5" 
     .Segments "4"
     .Create 
End With
```

## Elliptical Cylinder (or Prism)
```vba
With ECylinder 
     .Reset 
     .Name "solid7" 
     .Component "component1" 
     .Material "PEC" 
     .Xradius "2.5" 
     .Yradius "3.5" 
     .Axis "z" 
     .Zrange "0", "8" 
     .Xcenter "-12" 
     .Ycenter "-6" 
     .Segments "0" 
     .Create 
End With
```

## Analytic Face (Saddle Surface Example)
```vba
With AnalyticalFace
     .Reset 
     .Name "solid8" 
     .Component "component1" 
     .Material "PEC" 
     .LawX "u" 
     .LawY "v" 
     .LawZ "0.25*(u^2 - v^2)" 
     .ParameterRangeU "-4", "4" 
     .ParameterRangeV "-4", "4" 
     .Create
End With
```