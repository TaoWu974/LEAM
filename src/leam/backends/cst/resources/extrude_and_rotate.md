# Extrude and Rotate Reference

## Extrude Closed Curve
Note: Curve should reference one curve item from the closed profile.
```vba
With ExtrudeCurve
     .Reset 
     .Name "solid1" 
     .Component "component1" 
     .Material "Copper (pure)" 
     .Thickness "1" 
     .Twistangle "0.0" 
     .Taperangle "0.0" 
     .DeleteProfile "True" 
     .Curve "curve1:line1"
     .Create
End With
```

## Rotate Object
```vba
With Rotate 
     .Reset 
     .Name "solid10" 
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
     .Point "-0", "-28.5" 
     .LineTo "-3", "-24.5" 
     .LineTo "-5", "-30" 
     .LineTo "-0.5", "-33.5" 
     .LineTo "-2.5", "-29.5" 
     .LineTo "-0", "-28.5" 
     .Create 
End With
```

## Translate
```vba
With Transform 
     .Reset 
     .Name "component1:solid2" 
     .Vector "10", "10", "10" 
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