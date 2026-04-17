# LEAM Getting Started

This guide is for users who want to use LEAM without writing Python code.

LEAM is a Windows desktop tool that helps you turn an antenna description,
figures, and supporting notes into CST or HFSS modeling artifacts with the
help of an LLM.

If you need the exact desktop workflow rules, attachment behavior, or execution
gates, also read [`workflow_reference.md`](workflow_reference.md).

## What LEAM Can Do

LEAM can help you:

- extract geometric parameters from a design description
- identify materials
- generate a structured solids description
- generate CST VBA or HFSS/PyAEDT modeling artifacts
- optionally execute generated CST or HFSS artifacts on your local machine

In normal use, you work through the desktop app step by step.

## Before You Start

You need:

- Windows
- Python 3.11
- an OpenAI API key
- at least one local simulator runtime:
  - CST Studio Suite for CST workflows
  - Ansys Electronics Desktop for HFSS workflows

Important:

- LEAM Desktop will not continue if neither CST nor HFSS is available.
- Local simulator execution is disabled by default.
- You do not need to enable local execution just to generate files.

## Quick Start

For most users, the setup is only three steps:

```powershell
pip install leam
$env:OPENAI_API_KEY = "your_api_key_here"
leam-desktop
```

This is the only installation path recommended for normal desktop users. It now
includes the desktop UI and the HFSS Python dependency (`PyAEDT 0.25.1`) in the
base install.

Normal first launch does not require:

- a virtual environment
- `leam-configure`
- a manual config file
- manual simulator path setup unless auto-detection fails

If Python is not installed yet, install Python 3.11 first and then run the
command above.

If your machine has multiple Python versions installed, use:

```powershell
py -3.11 -m pip install leam
```

## Set Your OpenAI API Key

LEAM needs an OpenAI API key before it can run workflow steps.

For one PowerShell session:

```powershell
$env:OPENAI_API_KEY = "your_api_key_here"
```

If you want to keep it permanently, add `OPENAI_API_KEY` through the Windows
"Environment Variables" settings.

LEAM reads the OpenAI API key from the environment variable only. Do not put it
in `config.json`.

If you add `OPENAI_API_KEY` through the Windows settings while PowerShell or
LEAM Desktop is already open, close and reopen them first. A full computer
restart is usually not required.

## Start LEAM Desktop

Launch the desktop app from PowerShell:

```powershell
leam-desktop
```

If that command is not available yet, use the fallback launcher:

```powershell
py -3.11 -m leam.desktop
```

When LEAM opens, you will first see the launchpad.

## What LEAM Checks On Startup

On desktop startup, LEAM:

- reads the active config file from `LEAM_CONFIG`, if set, otherwise from the
  default user config file, typically `~/.leam/config.json`
- auto-detects local CST and HFSS installs and writes detected paths when
  needed
- does not create an empty config file when it cannot detect a local simulator
- derives the CST Python libraries path from the resolved local CST install
- checks whether the HFSS Python package import `ansys.aedt.core` is available
- keeps `allow_unsafe_execution` disabled by default

Normal first launch does not require `leam-configure`.

## If LEAM Says No Runtime Is Available

This usually means one of these is true:

- CST Studio Suite is not installed locally
- Ansys Electronics Desktop is not installed locally
- HFSS is installed, but the Python package `ansys.aedt.core` is missing
- the simulator is installed in a non-standard location and needs an advanced
  path override

Use this recovery order:

1. Confirm that at least one simulator is installed locally.
2. If HFSS is installed, rerun:

   ```powershell
   pip install leam
   ```

3. Restart LEAM Desktop.
4. If the runtime is still not detected, pin the CST/HFSS path manually in
   `~/.leam/config.json` or use `leam-configure`.

Most users should stop here and check the install first. Manual config editing
is only the fallback path.

## Advanced Runtime Setup

`leam-configure` is still available for advanced and troubleshooting workflows.
Use it when you want to inspect the packaged config template, pin simulator
paths after auto-detection fails, or manage multiple config files.

Helpful commands:

```powershell
leam-configure --dry-run
leam-configure --print-example
```

Typical manual config:

```json
{
  "cst_path": "C:\\Program Files (x86)\\CST Studio Suite 2025",
  "hfss_path": "C:\\Program Files\\ANSYS Inc\\v251\\AnsysEM",
  "allow_unsafe_execution": false
}
```

Use your real installation paths. If you need help pinning a specific version
or switching between multiple configs, use the advanced notes below.

## How LEAM Chooses Config

LEAM reads configuration in this order:

1. `LEAM_CONFIG`, if set
2. the default user config file, typically `~/.leam/config.json`

`OPENAI_API_KEY` is separate from `config.json`. LEAM reads it from the
environment variable only.

## Switch Between Multiple Configs

If you keep more than one config file, point LEAM at the one you want before
launching the desktop app.

PowerShell:

```powershell
$env:LEAM_CONFIG = "D:\LEAM\configs\hfss.json"
leam-desktop
```

Command Prompt:

```cmd
set LEAM_CONFIG=D:\LEAM\configs\cst.json
leam-desktop
```

Advanced shell-local overrides also exist:

- `CST_PATH`
- `HFSS_PATH`
- `LEAM_ALLOW_UNSAFE_EXECUTION`

## Create Your First Workspace

Click `New Workspace`.

You will be asked for:

- `Workspace name`
- `Backend`
  - choose `CST` for CST workflows
  - choose `HFSS` for HFSS workflows
- `Export root`

LEAM creates a workspace folder automatically. By default, workspaces are
stored under the LEAM workspace root, typically `~/.leam/workspaces`.

Each workspace is a normal folder on disk. This makes it easy to back up,
copy, or reopen later.

You can also:

- click `Open Workspace` to reopen an existing workspace folder
- click `Recent Workspaces` to resume a recent project
- click `Start From Example` to create a workspace from a built-in example

## Understand The Workspace Layout

Inside one workspace, LEAM usually creates:

- `session.json`: the saved session state
- `attachments\`: files you attached to steps
- `artifacts\`: generated outputs from workflow steps

You do not need to edit these files manually in normal use, but it is useful
to know where they are.

## Choose A Workflow Style

In the `Workspace Setup` step, you can choose a template.

Use:

- `Strong Description` when you can describe the geometry clearly
- `Weak Description` when you only have a rough concept and want LEAM to infer
  more structure
- `Paper Reconstruction (strong workflow + figures)` when you are rebuilding a
  design from paper figures and supporting images

You can also choose:

- `EM Simulator`: `CST` or `HFSS`
- optional `Enable 2.5D` workflow branch when needed
- optional `Enable Simulator Execution` if you want project-build steps in the
  workflow
- optional `Enable Parameter Update` branch if you expect to refine dimensions
  later

After changing workspace options, click `Apply Workspace Setup`.

Important:

- after `Workspace Setup` is applied, the workflow branches are locked for that
  workspace
- if you need a different backend or a very different workflow layout, it is
  usually better to create a new workspace

## Add Your Design Description

The first step is `Workspace Setup`.

In this step:

1. Write the main antenna description in the description box.
2. Add supporting attachments if needed.
3. Apply the workspace setup.

Write in plain English. You do not need special prompt syntax.

A good description usually includes:

- antenna type
- target frequency or band
- substrate material and thickness
- important dimensions
- feed structure
- slots, stubs, vias, or special shapes
- anything that must stay fixed

## Add Attachments

LEAM supports three practical attachment paths in the desktop UI:

- `Add Text`: create a text note inside the workspace
- `Add Files`: attach any file type, including simulator assets such as `.mtd`
- `Add Images`: quickly attach common image formats

Current practical rules:

- readable text-like files are forwarded as prompt attachments even if the extension is uncommon
- `PDF` is still forwarded as a document input
- common images are forwarded as image inputs
- text attachments can be edited directly in LEAM
- PDF files do not have an inline preview yet
- opaque binary attachments are kept in the workspace for reference and are not sent to the LLM

If you are reconstructing a paper design, a combination of:

- one clear text description
- one or more figures as PNG/JPG/JPEG
- the paper PDF

usually works better than images alone.

## Run The Workflow Step By Step

After the workspace is set up, run the workflow from top to bottom.

The common steps are:

1. `Parameters`
2. `Materials`
3. `Solids`
4. `Check Solid`
5. `Dimensions`
6. `3D Model`
7. `2.5D Model` if enabled
8. `Boolean Operations`

If execution is enabled, you may also see:

- `CST Project`
- `HFSS Project`
- `CST Update`
- `HFSS Update`

To run a step:

1. Click the step in the left panel.
2. Review the description, attachments, and selected upstream artifacts.
3. Click `Run This Step`.
4. Wait for the status to finish.
5. Review the generated output in the right-side result areas.

## Recommended Order For Beginners

For a first project, use this simple order:

1. Finish `Workspace Setup`
2. Run `Parameters`
3. Run `Materials`
4. Run `Solids`
5. Run `Check Solid`
6. If `Check Solid` finds problems, improve the earlier description and rerun
7. Run `Dimensions`
8. Run `3D Model`
9. Run `Boolean Operations`

This usually gives you a complete generation-only workflow without touching
local simulator execution.

## What `Check Solid` Is For

`Check Solid` is a quality-control step.

It helps catch issues such as:

- missing material references
- mismatched parameter names
- solids that do not align with the current dimensions
- structure inconsistencies before model generation

If it reports issues, go back and improve upstream steps instead of forcing the
workflow forward.

## When To Use `Parameter Update`

Use `Parameter Update` when the first pass is mostly correct and you only want
to modify values or a small part of the geometry.

Examples:

- increase patch width
- change slot length
- adjust feed dimensions
- tune one dimension set after the first result

This is usually faster than restarting the whole workflow from scratch.

## Local Execution Is Optional

LEAM can generate CST VBA or HFSS/PyAEDT artifacts without executing them.

That is the safest way to start.

If you want LEAM to run generated artifacts locally, two things must both be
true:

1. the workspace option `Enable Simulator Execution` is turned on
2. global runtime execution has not been disabled in config or by environment

Example config:

```json
{
  "allow_unsafe_execution": true
}
```

Important:

- execution is disabled by default
- turning it on means generated CST VBA or HFSS Python may run on your machine
- if you need to enable it globally, set `allow_unsafe_execution` to `true`
  or set `LEAM_ALLOW_UNSAFE_EXECUTION=1`
- only keep it enabled when you trust the prompts, attachments, and generated output

## Where To Find The Generated Results

LEAM stores outputs inside your workspace folder.

Typical files include:

- `parameters.json`
- `materials.json`
- `solids.json`
- `dimensions.json`
- `model_3d.bas` or `model_3d.py`
- `boolean.bas` or `boolean.py`
- simulator project outputs if execution is enabled

These files are usually stored under step-specific folders inside `artifacts`.

## Reopen An Old Project

To continue previous work:

1. open LEAM Desktop
2. click `Open Workspace` or `Recent Workspaces`
3. choose the workspace folder

LEAM will reload the saved session from `session.json` when it is available.

## Common Problems

### LEAM says no runtime is available

This usually means:

- the software is not installed locally
- HFSS is installed, but the Python package `ansys.aedt.core` is missing
- the path in `config.json` points to the wrong folder

Start with the desktop startup message. It tells you whether LEAM could not
detect CST, could not detect HFSS, or found HFSS but still needs the Python
package installed.

### The desktop app opens but steps cannot run

Common reasons:

- `OPENAI_API_KEY` is not set
- `OPENAI_API_KEY` was added in Windows settings after PowerShell or LEAM was already open
- your internet connection is unavailable
- the selected backend is not available
- a required upstream step has not run yet

### The generated model is wrong

Start by improving the input quality:

- write a clearer description
- add dimensions in consistent units
- attach a cleaner figure
- attach the paper PDF if available
- rerun `Parameters`, `Materials`, and `Solids`

### A built-in example is unavailable

Some examples depend on repository-only assets and may not appear in every
installation. This is normal.

## Best Practices

- Start with generation only. Do not enable local execution on day one.
- Keep one workspace per antenna concept.
- Put the target frequency, substrate, and units in the first description.
- Use a paper figure or a simple labeled image when the geometry is complex.
- Rerun only the steps affected by your change.
- Keep your simulator paths pinned in config so LEAM always uses the version
  you expect.

## Minimal Beginner Workflow

If you want the shortest possible path:

1. install LEAM Desktop
2. set `OPENAI_API_KEY`
3. if you set it through Windows settings, reopen PowerShell and LEAM Desktop
4. launch `leam-desktop`
5. let LEAM auto-detect CST or HFSS on startup
6. create a new workspace
7. choose `CST` or `HFSS`
8. write your antenna description
9. attach a PDF and one or two images if available
10. run `Parameters`, `Materials`, `Solids`, `Check Solid`, `Dimensions`,
   `3D Model`, and `Boolean Operations`
11. review the generated files in the workspace folder

That is enough for most non-programmer users to get started.
