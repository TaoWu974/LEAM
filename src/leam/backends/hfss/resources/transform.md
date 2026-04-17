# Transform Reference

## Move
move(vector: list | object) → 'UserDefinedComponent' | bool
```python
hfss.modeler["Box1"].move(
    vector=["0mm", "-0.7mm", "0mm"],
)
```

## Rotate
rotate(axis: Axis, angle: float = 90.0, units: str = 'deg') → 'UserDefinedComponent' | bool
```python
hfss.modeler["Box1"].rotate(
    axis="Y",
    angle="45deg",
)
```

## Mirror
mirror(origin: list | object, vector: list | object) → 'UserDefinedComponent' | bool
```python
hfss.modeler["Box1"].mirror(
    origin=["-0.5mm", "-0.4mm", "0mm"],
    vector=["-0.164398987305357mm", "0.986393923832144mm", "0mm"],
    duplicate=False,
)
```

## Duplicate Along Line
duplicate_along_line(vector: list | object, clones: int = 2, attach: bool = False, **kwargs) → list | bool
```python
hfss.modeler["Box1"].duplicate_along_line(
    vector=["0.3mm", "-0.9mm", "0mm"],
    clones=4,
    attach=False,
)
```

## Duplicate Around Axis
duplicate_around_axis(axis: Axis, angle: int = 90, clones: int = 2, create_new_objects: bool = True) → list | bool
```python
hfss.modeler["Box1"].duplicate_around_axis(
    axis="Y",
    angle="90deg",
    clones=4,
    create_new_objects=True,
)
```