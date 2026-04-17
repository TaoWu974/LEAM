# Transform Reference

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

## Scale
```vba
With Transform 
     .Reset 
     .Name "component1:solid2_6" 
     .Origin "Free" 
     .Center "0", "0", "0" 
     .ScaleFactor "2", "2", "2" 
     .MultipleObjects "False" 
     .GroupObjects "False" 
     .Repetitions "1" 
     .MultipleSelection "False" 
     .AutoDestination "True" 
     .Transform "Shape", "Scale" 
End With
```

## Rotate
```vba
With Transform 
     .Reset 
     .Name "component1:solid7" 
     .Origin "Free" 
     .Center "0", "0", "0" 
     .Angle "5", "0", "0" 
     .MultipleObjects "False" 
     .GroupObjects "False" 
     .Repetitions "1" 
     .MultipleSelection "False" 
     .AutoDestination "True" 
     .Transform "Shape", "Rotate" 
End With
```

## Mirror
```vba
With Transform 
     .Reset 
     .Name "component1:solid7" 
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
