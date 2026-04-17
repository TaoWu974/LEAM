from importlib import import_module

from .boolean_ops import BooleanOperationsGenerator
from .check_solid import CheckSolid
from .dimension_generator import DimensionGenerator
from .materials import MaterialsProcessor
from .model_2d_generator import Model2DGenerator
from .model_3d_generator import Model3DGenerator
from .parameter_generator import ParameterGenerator
from .parameter_update import ParameterUpdater
from .strong_description_to_solids import StrongDescriptionToSolids
from .weak_description_to_solids import WeakDescriptionToSolids

__all__ = [
    "BooleanOperationsGenerator",
    "CheckSolid",
    "CstRunner",
    "DimensionGenerator",
    "MaterialsProcessor",
    "Model2DGenerator",
    "Model3DGenerator",
    "ParameterGenerator",
    "ParameterUpdater",
    "StrongDescriptionToSolids",
    "WeakDescriptionToSolids",
]


def __getattr__(name: str):
    if name in {
        "boolean_ops",
        "check_solid",
        "cst_runner",
        "dimension_generator",
        "materials",
        "model_2d_generator",
        "model_3d_generator",
        "parameter_generator",
        "parameter_update",
        "strong_description_to_solids",
        "weak_description_to_solids",
    }:
        return import_module(f".{name}", __name__)
    if name == "CstRunner":
        from .cst_runner import CstRunner

        return CstRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
