---
name: llm-enabled-antenna-modeling
description: "Use this skill when an antenna engineer asks ChatGPT or a coding agent to convert antenna requirements, paper excerpts, figures, parameter tables, or geometry notes into simulator-ready CST/HFSS workflows. It provides an independent LLM-guided antenna modeling workflow for detecting available simulator backends, producing parameters, materials, solids, dimensions, CST VBA macros, HFSS/PyAEDT scripts, boolean operations, validation reports, simulator project creation, and parameter updates."
---

# LLM-Enabled Antenna Modeling

## Purpose

This skill is an independent antenna-modeling workflow for LLM agents. Use it to let an agent detect the locally available simulator backend, choose an appropriate CST or HFSS path, and produce simulator-ready modeling artifacts.

## Background

The workflow is based on the modeling approach described in "Large Language Model-Based Intelligent Antenna Design System" by Wu, Fu, Hua, Liu, and Liu, accepted for the 20th European Conference on Antennas and Propagation (EuCAP). A related reference implementation is the `leam` Python package.

## Operating Flow

First detect simulator availability before entering the modeling loop:

1. Check whether CST and/or HFSS is usable in the current environment.
   - CST is usable only when a local CST install and its Python interface/material library can be reached.
   - HFSS is usable only when a local AEDT/HFSS install is present and PyAEDT (`ansys.aedt.core`) is importable.
2. If the user explicitly requested `cst` or `hfss`, use that backend only if it is available. If it is unavailable, exit the agent loop and tell the user which backend was requested and what availability check failed.
3. If the user did not specify a backend, choose one available backend yourself. Prefer the backend that best fits the requested output or available material libraries; if both are equally suitable, choose CST for VBA-oriented requests and HFSS for PyAEDT/Python-oriented requests.
4. If neither CST nor HFSS is available, exit the agent loop and tell the user that no usable simulator backend was detected.

Then identify the modeling target:

1. Backend: selected `cst` or `hfss`.
2. Input type:
   - `strong_description`: detailed geometry and dimensions are supplied.
   - `weak_description`: only high-level antenna intent is supplied; infer a reasonable initial structure.
   - `paper_reconstruction`: paper text, figures, captions, or parameter tables are supplied.
3. Output requested: JSON artifacts, CST VBA, HFSS PyAEDT Python, review report, simulator project creation, or parameter update.
4. Whether 2.5D geometry is required for splines, polygons, curved outlines, or extruded planar artwork.

Load references as needed:

- `references/modeling-workflow.md`: full step order, decision points, and artifact handoff rules.
- `references/artifact-schemas.md`: required JSON and script output shapes.
- `references/cst-vba-guidance.md`: CST parameter, material, 3D, 2.5D, boolean, and update rules.
- `references/hfss-pyaedt-guidance.md`: HFSS parameter, material, 3D, 2.5D, boolean, and update rules.
- `references/validation-and-safety.md`: check-solid review, assumptions, and engineering limits.
- `references/examples.md`: distilled examples for Vivaldi, slotted patch, and slotted monopole workflows.

## Default Deliverable

Unless the user asks for a single artifact, produce a staged modeling package:

1. `initial_solids`: `initial_solids.json`; only for `weak_description`; infer a first-pass solid list before parameters/materials.
2. `parameters`: `parameters.json` plus `parameters.bas` for CST or `parameters.py` for HFSS; geometric variables only.
3. `materials`: `materials.json` plus `materials.bas` for CST when imported/custom materials are needed; simulator material names and assumptions.
4. `solids`: `solids.json`; functional solid list with 3D/2.5D classification.
5. `check_solid`: `solids_check.json`; status-bearing report with concrete issues or an empty issues array.
6. `dimensions`: `dimensions.json`; coordinate-based ranges and structured profiles.
7. `model_3d`: `model_3d.bas` for CST or `model_3d.py` for HFSS; code for 3D solids only.
8. `model_2d`: `model_2d.bas` for CST or `model_2d.py` for HFSS; code for 2.5D profiles only, when needed.
9. `boolean`: `boolean.bas` for CST or `boolean.py` for HFSS; code for union/subtract/intersect only.
10. `parameter_update`: `parameter_update.bas` for CST or `parameter_update.py` for HFSS; only when the user requests tuning or revised dimensions.

Optional execution deliverables:

- `cst_project`: `antenna.cst`; requires selected CST artifacts `parameters.bas`, `materials.bas`, `model_3d.bas`, optional `model_2d.bas`, and `boolean.bas`.
- `hfss_project`: `antenna.aedt`; requires selected HFSS artifacts `parameters.py`, `model_3d.py`, optional `model_2d.py`, and `boolean.py`.
- `cst_update`: `antenna_updated.cst`; requires `antenna.cst` plus `parameter_update.bas`.
- `hfss_update`: `antenna_updated.aedt`; requires `antenna.aedt` plus `parameter_update.py`.

Keep artifacts separated. Do not mix boolean operations into model generation. Do not include simulation setup, ports, boundaries, monitors, sweeps, optimization, or results unless the user explicitly asks for those and provides enough context.

When a writable workspace is available, prefer one artifact per file using the filenames above. If inline output is more appropriate or the user asks for it, present one artifact per clearly labeled section or code block.

## Interaction Rules

- Preserve exact user-provided dimensions, materials, coordinate origins, and parameter names when available.
- If needed values are missing, introduce explicit geometric parameters rather than pretending exact data exists.
- For unspecified conductors, use the backend convention unless the user or material context provides a specific conductor: CST defaults to `Copper (pure)`; HFSS may use `pec`.
- Treat voids, slots, and cutouts as `Vacuum`/`vacuum` solids that are later subtracted.
- Feeds should slightly overlap the fed element instead of merely touching.
- Generated code is a draft for engineering review and simulator validation, not a verified antenna design.
- If asked to run CST/HFSS or produce measured performance, do so only when the selected simulator backend is available and the agent can execute the simulator workflow in the current environment; otherwise exit the agent loop and explain the missing backend or execution capability.
