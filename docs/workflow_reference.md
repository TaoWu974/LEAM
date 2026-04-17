# LEAM Workflow Reference

This document describes the actual LEAM Desktop workflow behavior implemented in
the current codebase. It complements [`getting_started.md`](getting_started.md)
by focusing on workflow rules, workspace structure, step visibility,
attachment handling, artifact selection, and simulator-execution gates.

Use this document when you need a precise reference for how LEAM Desktop
decides what to show, what to forward to the model, and when a step can run.

## Workspace Model

LEAM Desktop works with LEAM workspaces, not external CST or HFSS project files
as the primary unit of work.

Each workspace is a folder that contains:

- `session.json`: the saved desktop session state
- `attachments/`: copied user attachments, organized by step
- `artifacts/`: generated outputs, organized by step and run

By default, new workspaces are created under:

the user's LEAM workspace root, typically `~/.leam/workspaces`

The generated workspace folder name includes:

- a sanitized workspace title
- the selected backend
- a local creation stamp used to keep workspace folders distinct

The creation stamp is a local filesystem detail inside the user's own LEAM
workspace root. It is not transmitted as part of model input by LEAM itself.

When the backend changes during workspace setup, LEAM tries to rename the
workspace folder so the folder name stays aligned with the selected backend.

## Workspace Persistence And Recovery

LEAM stores workspace-relative paths inside `session.json` whenever possible.
This makes a workspace more portable if you move the whole folder.

If `session.json` is missing but the workspace still contains `attachments/` and
`artifacts/`, LEAM can reconstruct a best-effort session by scanning the
workspace contents. In that reconstructed mode:

- the latest known artifacts per step are restored
- step status is inferred from the discovered files
- the backend is inferred from artifact labels and file kinds
- the 2.5D branch is inferred from `model_2d` artifacts or `solids.json`
- the session is marked internally as reconstructed from the workspace

This recovery path is useful, but `session.json` is still the canonical source
of desktop state.

## Workspace Setup And Branch Locking

The first desktop step is always `Workspace Setup`.

It controls:

- workflow template
- backend
- whether the 2.5D branch is enabled
- whether simulator execution branches are enabled
- whether the parameter-update branch is enabled

Supported templates:

- `strong_description`
- `weak_description`
- `paper_reconstruction`

Supported backends:

- `cst`
- `hfss`

After `Workspace Setup` is applied successfully, the workflow branch structure
is treated as locked for that workspace session. You can still continue editing
descriptions and attachments, but changing branch topology after work has
already started is intentionally constrained in the UI.

## Step Graph

The exact visible step graph depends on the selected template, backend, and
workspace options.

### Base Step

Every workspace starts with:

1. `Workspace Setup`

### Strong Description And Paper Reconstruction

For `strong_description` and `paper_reconstruction`, the standard generation
path is:

1. `Workspace Setup`
2. `Parameters`
3. `Materials`
4. `Solids`
5. `Check Solid`
6. `Dimensions`
7. `3D Model`
8. `Boolean Operations`

### Weak Description

For `weak_description`, LEAM inserts an extra bootstrap step:

1. `Workspace Setup`
2. `Initial Solids`
3. `Parameters`
4. `Materials`
5. `Solids`
6. `Check Solid`
7. `Dimensions`
8. `3D Model`
9. `Boolean Operations`

### Optional 2.5D Branch

If `Enable 2.5D` is turned on in workspace setup, LEAM inserts:

- `2.5D Model`

This step runs after `3D Model` and before `Boolean Operations`.

### Optional Execution Branch

If `Enable Simulator Execution` is turned on in workspace setup:

- CST workspaces expose `CST Project`
- HFSS workspaces expose `HFSS Project`

These are optional execution steps. They appear only when the workspace branch
is enabled. They still require global runtime execution to be enabled before
they can actually run.

In current code, new workspaces and built-in examples start with
`Enable Simulator Execution` turned on by default. Turning it off in
`Workspace Setup` removes the execution branch from that workspace.

### Optional Parameter-Update Branch

If `Parameter Update` is turned on in workspace setup, LEAM inserts:

- `Parameter Update`

If simulator execution is also enabled:

- CST workspaces also expose `CST Update`
- HFSS workspaces also expose `HFSS Update`

## Step Visibility Rules

Some steps are optional. LEAM does not show every optional step immediately.

An optional step becomes visible when at least one of these is true:

- the step has already run
- the step has its own description, refill notes, attachments, selected
  artifacts, or output artifacts
- all of its upstream steps have reached a ready status

This matters most for:

- execution steps
- parameter-update steps
- update-application steps

## Input Assembly For A Step Run

When LEAM runs a step, it builds the final prompt input from multiple sources.

The final description text is assembled in this order:

1. the workspace-level description from `Workspace Setup`
2. the current step description
3. any routed refill notes inserted after `Check Solid`

For the `Solids` step, LEAM also appends one explicit sentence:

- `There should be 2.5D element`
- or `There should be no 2.5D element`

That sentence is derived from the workspace-level `Enable 2.5D` setting.

## Attachment Handling

LEAM copies user attachments into the workspace instead of reading them from
their original location each time.

The desktop accepts three practical attachment categories:

- text-like files
- PDF files
- images

### What Reaches The Model

Only enabled attachments are forwarded. Disabled attachments stay in the
workspace but are ignored for model input.

Description attachments are special:

- LEAM maintains an editable `description.txt` attachment internally for each
  step description
- that file is not forwarded as a separate attachment
- its content is already included in the assembled final description text

For normal user attachments:

- readable text-like files are forwarded as prompt text files
- PDFs are forwarded as document inputs
- PNG and JPEG files are forwarded as model images
- opaque binary files stay local to the workspace and are not forwarded

### Image Support Rules

LEAM can store more image formats in the workspace than it can forward to the
model.

Workspace-level image classification includes:

- `.png`
- `.jpg`
- `.jpeg`
- `.bmp`
- `.gif`
- `.webp`
- `.tif`
- `.tiff`

Model-input image forwarding is stricter. Only these image formats are
accepted for LLM input:

- `.png`
- `.jpg`
- `.jpeg`

If an enabled attachment is an image but not one of those three formats, the
step fails validation before the model call and asks you to convert or disable
that image.

### Text-Like File Rules

LEAM treats readable text-like files as prompt attachments even when the file
extension is uncommon, as long as the file passes the text-file checks used by
the desktop runner.

This is why files such as `.mtd`, `.log`, `.ini`, `.cfg`, `.yaml`, `.toml`, or
similar readable files can still contribute prompt context.

## Artifact Selection

Each step can consume artifacts from upstream steps. LEAM auto-selects default
upstream outputs based on the current step definition.

Examples:

- `Check Solid` defaults to `solids_json`, `parameters_json`, and
  `materials_json`
- `3D Model` defaults to the parameter artifact, `dimensions_json`, and the
  backend-specific materials artifact
- `Boolean Operations` defaults to the parameter artifact, `dimensions_json`,
  `3D Model`, and optionally `2.5D Model`

If you manually change artifact selections in the UI, LEAM records that the
selection was user-touched and stops resetting it to the default set on later
refreshes. Missing artifacts are still pruned automatically from that saved
selection.

Only text-like upstream artifacts are forwarded as prompt files:

- `text`
- `json`
- `macro`

Binary project files such as `.cst` and `.aedt` are not forwarded as prompt
text.

## Step Status Semantics

LEAM tracks a richer state model than just idle/running/done.

Main display statuses:

- `WAITING`: the step is idle but still blocked by upstream prerequisites
- `RUNNING`: the step is currently executing
- `DONE`: the step finished successfully
- `ISSUES`: the step completed, but the result reported issues
- `BLOCKED`: the step is blocked by an upstream rerun requirement
- `RERUN`: the step itself must be rerun because `Check Solid` routed issues to it
- `STALE`: the step previously succeeded, but an upstream change made it out of date
- `ERROR`: the step run failed

In practice:

- rerunning a successful upstream step marks downstream successful steps as
  `STALE`
- if `Check Solid` routes blocking issues upstream, the targeted step becomes
  `RERUN` and later steps become `BLOCKED`

## `Check Solid` Routing Behavior

`Check Solid` is not just a report generator. It also mutates workflow state.

If the report status is `issues`:

- warning-level issues are ignored for rerun routing
- non-warning issues are routed to `parameters`, `materials`, or `solids`
- the target step receives appended refill notes
- the target step status becomes `rerun_required`
- later steps are blocked until the routed step is rerun

Route selection follows the issue payload first:

- explicit `route_to`
- then category/path heuristics

If no stronger match is found, LEAM routes the issue back to `Solids`.

## Workspace Artifacts

Generated outputs are stored under:

`artifacts/<step-id>/<run-dir>/`

Examples:

- `artifacts/parameters/<run-dir>/parameters.json`
- `artifacts/model_3d/<run-dir>/model_3d.py`
- `artifacts/cst_project/<run-dir>/antenna.cst`

Typical artifact names include:

- `parameters.json`
- `parameters.bas`
- `parameters.py`
- `materials.json`
- `materials.bas`
- `solids.json`
- `solids_check.json`
- `dimensions.json`
- `model_3d.bas`
- `model_3d.py`
- `model_2d.bas`
- `model_2d.py`
- `boolean.bas`
- `boolean.py`
- `parameter_update.bas`
- `parameter_update.py`
- `antenna.cst`
- `antenna.aedt`
- `antenna_updated.cst`
- `antenna_updated.aedt`

Each new run gets a new numbered run directory instead of overwriting the
previous run folder. Run directory names also include a local timestamp suffix
for collision avoidance inside the workspace. Like the workspace creation
stamp, that run-directory timestamp is a local storage detail rather than a
special piece of model input.

## Backend Availability

The desktop does not treat a backend as available just because the simulator
path exists in config.

### CST Availability

CST is considered available only when all of these are true:

- `cst_path` resolves to a valid directory
- the CST Python libraries path can be derived from that install
- `cst.interface` becomes importable after LEAM bootstraps the CST Python
  libraries path

### HFSS Availability

HFSS is considered available only when all of these are true:

- `hfss_path` resolves to a valid directory
- the HFSS install root contains `syslib`
- `ansys.aedt.core` is importable in the current Python environment

If neither backend is available, the desktop launchpad blocks entry into the
workspace page.

## Execution Gates

Simulator execution requires two independent approvals:

1. the workspace branch option `Enable Simulator Execution`
2. the global runtime execution gate

The global runtime execution gate is controlled by:

- `LEAM_ALLOW_UNSAFE_EXECUTION=1`
- or `"allow_unsafe_execution": true` in the active LEAM config

Even if the workspace branch is enabled, execution steps still fail if the
global unsafe-execution gate is disabled.

This separation is intentional:

- workspace setup controls whether execution steps exist in that workflow
- config/environment controls whether generated simulator code may actually run

## What Execution Steps Produce

Execution steps create simulator project files inside their own run folders.

### CST

- `CST Project` writes `antenna.cst`
- `CST Update` writes `antenna_updated.cst`

### HFSS

- `HFSS Project` writes `antenna.aedt`
- `HFSS Update` writes `antenna_updated.aedt`

These project-building steps use the selected upstream generation artifacts
rather than rerunning earlier LLM steps implicitly.

## Built-In Examples

LEAM ships built-in example presets in the desktop app:

- `Vivaldi Antenna`
- `Slotted Patch`
- `Slotted Monopole`

### `Vivaldi Antenna`

- template: `strong_description`
- default backend: `cst`
- enables `2.5D`
- enables `Parameter Update`
- does not require repository-only assets

### `Slotted Patch`

- template: `weak_description`
- default backend: `cst`
- includes the extra `Initial Solids` step from the weak-description workflow
- does not require repository-only assets

### `Slotted Monopole`

- template: `paper_reconstruction`
- default backend: `cst`
- enables `Parameter Update`
- seeds image-backed attachments and step-specific notes
- may be unavailable unless repository assets are present locally

Example availability is asset-dependent.

Examples that rely on repository-backed assets are disabled when those assets
are not present in the installed copy. This is why a source checkout can expose
more examples than a plain wheel install.

When you start from an example, the project dialog still lets you choose any
currently available backend. The preset backend is only the default selection.

When a preset is applied, LEAM can prefill:

- the workspace template
- the default backend choice
- the top-level input description
- step-specific descriptions
- bundled example attachments

## Recommended Operational Practices

- Treat one workspace as one antenna concept or one reconstruction thread.
- Leave execution disabled until the generated artifacts look structurally
  correct.
- Keep artifact selections on their defaults unless you have a concrete reason
  to override them.
- If `Check Solid` reports routed issues, rerun the targeted upstream step
  before touching downstream model-generation steps.
- Keep source assets in the workspace through attachments rather than relying on
  external file paths.
- Do not assume a simulator path alone makes a backend available; the Python
  runtime dependency must also be importable.

## Related Documentation

- [Getting Started](getting_started.md)
- [Python API](python_api.md)
