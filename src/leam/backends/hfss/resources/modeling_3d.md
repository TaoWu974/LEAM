# 3D Modeling Reference

## New Box
create_box(origin: list, sizes: list, name: str = None, material: str = None, **kwargs)
```python
from ansys.aedt.core import Hfss
hfss = Hfss()
origin = [0, 0, 0]
dimensions = [10, 5, 20]
box_object = hfss.modeler.create_box(origin=origin, sizes=dimensions, name="mybox", material="copper")
```

## Cylinder
create_cylinder(orientation: str | int | Plane, origin: list, radius: float | str, height: float | str, num_sides: int = 0, name: str = None, material: str = None, **kwargs)
```python
from ansys.aedt.core import Hfss
aedtapp = Hfss()
cylinder_object = aedtapp.modeler.create_cylinder(
    orientation="Z", origin=[0, 0, 0], radius=2, height=3, name="mycyl", material="vacuum"
)
```

## New Sphere
create_sphere(origin: list, radius: float | int | str, name: str = None, material: str = None, **kwargs)
```python
from ansys.aedt.core import Hfss
aedtapp = Hfss()
ret_object = aedtapp.modeler.create_sphere(origin=[0,0,0],radius=2,name="mysphere",material="copper")
```

## New Cone
create_cone(orientation: str = None, origin: list = None, bottom_radius: float | int | str = None, top_radius: float | int | str = None, height: float | int | str = None, name: str = None, material: str = None, **kwargs)
```python
from ansys.aedt.core import Hfss
aedtapp = Hfss()
cone_object = aedtapp.modeler.create_cone(orientation='Z', origin=[0, 0, 0],
                                          bottom_radius=2, top_radius=3, height=4,
                                          name="mybox", material="copper")
```

## New Torus
create_torus(origin: list, major_radius: float | int | str, minor_radius: float | int | str, axis: str = None, name: str = None, material: str = None, **kwargs)
```python
from ansys.aedt.core import Hfss
hfss = Hfss()
origin = [0, 0, 0]
torus = hfss.modeler.create_torus(origin=origin,major_radius=1,minor_radius=0.5,
                                  axis="Z",name="mytorus",material="copper")
```

## Regular Polyhedron
create_polyhedron(orientation: str | int = None, center: list = (0.0, 0.0, 0.0), origin: list = (0.0, 1.0, 0.0), height: float = 1.0, num_sides: int = 12, name: str = None, material: str = None, **kwargs)
``` python
from ansys.aedt.core import Hfss
aedtapp = Hfss()
ret_obj = aedtapp.modeler.create_polyhedron(orientation='X',center=[0, 0, 0],
                                            origin=[0,5,0],height=0.5,num_sides=8,
                                            name="mybox",material="copper")
```

## Bondwire
create_bondwire(start: list, end: list, h1: float = 0.2, h2: int = 0, alpha: int = 80, beta: int = 5, bond_type: int = 0, diameter: float = 0.025, facets: int = 6, name: str = None, material: str = None, orientation: str = 'Z', **kwargs)
```python
from ansys.aedt.core import Hfss
hfss = Hfss()
origin = [0,0,0]
endpos = [10,5,20]
#Material and name are not mandatory fields
object_id = hfss.modeler.create_bondwire(origin,endpos,h1=0.5,h2=0.1,alpha=75,
                                         beta=4,bond_type=0,name="mybox",material="copper")
```
