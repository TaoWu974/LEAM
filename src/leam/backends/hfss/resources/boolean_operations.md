# Boolean Operations Reference

Use pure Python with the shared PyAEDT `hfss` object. Do not use `oEditor` or IronPython APIs.

## Unite
```python
result = hfss.modeler.unite(
    assignment=["Box1", "Sphere1"],
    keep_originals=False,
)
if result is False:
    raise RuntimeError("Unite failed for Box1 and Sphere1.")
```

## Subtract
```python
result = hfss.modeler.subtract(
    blank_list=["Box1"],
    tool_list=["Sphere1"],
    keep_originals=False,
)
if result is False:
    raise RuntimeError("Subtract failed for Box1 minus Sphere1.")
```

## Intersect
```python
result = hfss.modeler.intersect(
    assignment=["Box1", "Sphere1"],
    keep_originals=False,
)
if result is False:
    raise RuntimeError("Intersect failed for Box1 and Sphere1.")
```

## Split
```python
result = hfss.modeler.split(
    assignment=["Box1"],
    plane="XY",
    sides="PositiveOnly",
)
if result is False:
    raise RuntimeError("Split failed for Box1 on the XY plane.")
```

## Imprint
```python
result = hfss.modeler.imprint(
    blank_list=["Box1"],
    tool_list=["Sphere1"],
    keep_originals=False,
)
if result is False:
    raise RuntimeError("Imprint failed for Box1 and Sphere1.")
```
