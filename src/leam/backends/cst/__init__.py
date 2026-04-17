from .tools import (
    BooleanOperationsGenerator,
    CheckSolid,
    DimensionGenerator,
    MaterialsProcessor,
    Model2DGenerator,
    Model3DGenerator,
    ParameterGenerator,
    ParameterUpdater,
    StrongDescriptionToSolids,
    WeakDescriptionToSolids,
)

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
    if name == "CstRunner":
        from .tools import CstRunner

        return CstRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
