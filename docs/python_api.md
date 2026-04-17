# LEAM Python API

This page is for users who want to call LEAM from Python rather than from the
desktop app.

If you are mainly using LEAM as a desktop tool, the simpler path is still:

```powershell
pip install leam
$env:OPENAI_API_KEY = "your_api_key_here"
leam-desktop
```

For Python use, LEAM is most practical in two styles:

- backend-specific workflow tools for CST and HFSS
- runtime and configuration helpers for local simulator discovery

## Prerequisites

Use this page when you are writing your own Python scripts.

For the current package layout:

- install LEAM with `pip install leam`
- use Python 3.11
- set `OPENAI_API_KEY` in the environment before calling model-backed tools
- keep CST Studio Suite or Ansys Electronics Desktop installed locally when
  you need local material discovery or simulator execution

Notes:

- the base `leam` package now includes `PySide6` and `PyAEDT`
- CST support still relies on the local CST installation for
  `cst.interface`

## What To Import

In most cases, import from one backend package directly:

```python
from leam.backends.cst import ParameterGenerator
from leam.backends.cst import MaterialsProcessor
from leam.backends.hfss import Model3DGenerator
from leam.backends.hfss import HfssRunner
```

This keeps your script explicit about which simulator workflow you want.

## Small Top-Level Surface

The top-level `leam` package intentionally exposes only a small public surface:

```python
from leam import LLMCaller, VBAGenerator
```

For most practical work, import from `leam.config`, `leam.backends.cst`, or
`leam.backends.hfss` instead of relying on broad top-level imports.

## Core Modules

### `leam.config`

`leam.config` is the main helper module for runtime discovery and environment
handling.

Common functions:

- `load_config()`: load the active LEAM config file
- `resolve_cst_path(config)`: resolve the pinned or overridden CST install root
- `resolve_cst_python_libraries_path(config)`: derive the CST Python libraries
  path from the resolved CST install
- `resolve_hfss_path(config)`: resolve the pinned or overridden HFSS root
- `resolve_openai_api_key(config)`: read `OPENAI_API_KEY` from the environment
- `resolve_allow_unsafe_execution(config)`: resolve the execution gate from
  environment or config
- `resolve_openai_timeout_seconds(config)`: resolve request timeout
- `validate_cst_path(path)` / `validate_hfss_path(path)`: validate simulator
  paths
- `autofill_simulator_paths(config)`: fill missing simulator paths from local
  detection
- `initialize_user_config(config=None)`: write a user config with detected
  paths
- `main(argv=None)`: CLI entrypoint used by `leam-configure`

Simple example:

```python
from leam.config import load_config, resolve_cst_path, resolve_hfss_path

config = load_config()
print("CST:", resolve_cst_path(config))
print("HFSS:", resolve_hfss_path(config))
```

### `leam.core`

`leam.core` exposes reusable lower-level classes:

- `LLMCaller`
- `PythonScriptGenerator`
- `VBAGenerator`
- `LeamError`
- `InputValidationError`
- `LlmCallError`
- `GenerationError`

These are useful if you want to build your own prompts or generation flows on
top of LEAM primitives rather than using the backend tool wrappers directly.

## CST Backend

Use the CST backend when you want LEAM to generate CST-oriented artifacts such
as VBA macros and CST material selections.

Recommended import:

```python
from leam.backends.cst import ParameterGenerator
```

Main CST classes:

- `ParameterGenerator`
- `ParameterUpdater`
- `MaterialsProcessor`
- `StrongDescriptionToSolids`
- `WeakDescriptionToSolids`
- `CheckSolid`
- `DimensionGenerator`
- `Model3DGenerator`
- `Model2DGenerator`
- `BooleanOperationsGenerator`
- `CstRunner`

Typical methods:

- `generate_parameters(...)`
- `generate_update(...)`
- `generate_materials(...)`
- `get_solids(...)`
- `check(...)`
- `generate_dimensions(...)`
- `generate_model(...)`
- `generate_operations(...)`

Minimal CST example:

```python
from leam.backends.cst import ParameterGenerator

generator = ParameterGenerator(save_dir="output")
generator.generate_parameters(
    description="Design a rectangular patch antenna for 2.45 GHz.",
    output_file="parameters.bas",
    json_file="parameters.json",
)
```

This produces:

- a CST VBA macro such as `parameters.bas`
- a companion JSON file such as `parameters.json`

CST materials example:

```python
from leam.backends.cst import MaterialsProcessor

processor = MaterialsProcessor(save_dir="output")
processor.generate_materials(
    description="Use Rogers RO4003C substrate and PEC metal.",
    save_as="materials.json",
    macro_file="materials.bas",
)
```

Important CST notes:

- LEAM resolves CST materials from the local CST material library
- generated CST material output includes a JSON record plus a VBA import macro
- CST runtime execution depends on `cst.interface` being bootstrapped from the
  configured install

## HFSS Backend

Use the HFSS backend when you want LEAM to generate PyAEDT-oriented scripts and
HFSS project artifacts.

Recommended import:

```python
from leam.backends.hfss import ParameterGenerator
```

Main HFSS classes:

- `ParameterGenerator`
- `ParameterUpdater`
- `MaterialsProcessor`
- `StrongDescriptionToSolids`
- `WeakDescriptionToSolids`
- `CheckSolid`
- `DimensionGenerator`
- `Model3DGenerator`
- `Model2DGenerator`
- `BooleanOperationsGenerator`
- `HfssRunner`

Typical methods:

- `generate_parameters(...)`
- `generate_update(...)`
- `generate_materials(...)`
- `get_solids(...)`
- `check(...)`
- `generate_dimensions(...)`
- `generate_model(...)`
- `generate_operations(...)`

Minimal HFSS example:

```python
from leam.backends.hfss import ParameterGenerator

generator = ParameterGenerator(save_dir="output")
generator.generate_parameters(
    description="Design a rectangular patch antenna for 2.45 GHz.",
    output_file="parameters.py",
    json_file="parameters.json",
)
```

This produces:

- an HFSS/PyAEDT-oriented Python script such as `parameters.py`
- a companion JSON file such as `parameters.json`

HFSS materials example:

```python
from leam.backends.hfss import MaterialsProcessor

processor = MaterialsProcessor(save_dir="output")
processor.generate_materials(
    description="Use Rogers RO4003C substrate and PEC metal.",
    save_as="materials.json",
)
```

Important HFSS notes:

- LEAM resolves material names against built-ins plus the local AEDT
  `syslib` material libraries
- the standard HFSS material-generation path writes `materials.json`
- optional custom-material Python generation exists separately through
  `generate_material_script(...)`

## Typical Output Files

Most generators write one or both of these output styles:

- a simulator-facing script or macro
- a normalized JSON companion file

Typical filenames:

- `parameters.bas`
- `parameters.py`
- `parameters.json`
- `materials.bas`
- `materials.json`
- `solids.json`
- `dimensions.json`
- `model_3d.bas`
- `model_3d.py`
- `model_2d.bas`
- `model_2d.py`
- `boolean.bas`
- `boolean.py`
- `parameter_update.bas`
- `parameter_update.py`

## Launching The Desktop From Python

The desktop app can be launched from the installed GUI entrypoint:

```powershell
leam-desktop
```

or from Python:

```powershell
py -3.11 -m leam.desktop
```

The desktop module is not exposed as a top-level package entrypoint such as
`leam.__main__`.

## Built-In Example Helpers

Built-in desktop example presets are available through `leam.desktop.examples`.

Useful functions:

- `available_example_presets()`
- `unavailable_example_presets()`
- `get_example_preset(...)`
- `apply_example_preset(...)`

Use these helpers when you want to inspect the packaged presets or seed a new
desktop workflow session programmatically.

## Stability Guidance

The backend wrapper classes and `leam.config` helpers are the most practical
APIs to depend on directly.

For long-term stability:

- prefer documented classes from `leam.backends.cst` and `leam.backends.hfss`
- prefer helper functions from `leam.config`
- treat private names and undocumented modules as implementation details

## Related Documentation

- [Getting Started](getting_started.md)
- [Workflow Reference](workflow_reference.md)
