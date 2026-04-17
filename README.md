# LEAM

LEAM is an open-source research toolkit for LLM-enabled antenna modeling. It is
the public codebase accompanying the paper
[`Large Language Model-Based Intelligent Antenna Design System`](https://arxiv.org/abs/2504.18271)
and focuses on the workflow layer between antenna intent and simulator-facing
artifacts for CST and HFSS.

LEAM provides:

- CST-oriented prompt and VBA generation tools
- HFSS-oriented prompt and PyAEDT script generation tools
- A Windows desktop workflow UI for step-by-step, human-in-the-loop modeling

LEAM is designed for research demonstration, transparent workflow inspection,
and practical antenna engineering support. It does not bundle CST, HFSS, or
AEDT, and it does not replace simulator validation or engineering review.

## Quick Start

LEAM Desktop currently targets Windows with Python 3.11.

You need:

- Windows
- Python 3.11
- an OpenAI API key
- at least one local simulator install:
  - CST Studio Suite for CST workflows
  - Ansys Electronics Desktop for HFSS workflows

Normal desktop path:

- no virtual environment
- no separate `leam-configure` step
- no manual CST/HFSS path setup unless auto-detection fails

Open PowerShell and run:

```powershell
pip install leam
$env:OPENAI_API_KEY = "your_api_key_here"
leam-desktop
```

`pip install leam` now includes the desktop UI and the HFSS Python dependency
in the base package.

If you prefer the shortest mental model, the setup is:

1. Install `leam`
2. Set `OPENAI_API_KEY`
3. Start `leam-desktop`

If your machine has multiple Python versions installed, use:

```powershell
py -3.11 -m pip install leam
```

If `leam-desktop` is not on your `PATH` yet, use:

```powershell
py -3.11 -m leam.desktop
```

If you add `OPENAI_API_KEY` through the Windows "Environment Variables"
settings instead, close and reopen PowerShell and LEAM Desktop so the new value
is picked up.

## What LEAM Checks On Startup

When `leam-desktop` starts, LEAM:

- reads configuration from `LEAM_CONFIG`, if set, otherwise from the default
  user config file, typically `~/.leam/config.json`
- auto-detects local CST and HFSS installs and saves detected paths when needed
- does not create an empty config file when no local simulator install is
  detected
- bootstraps the CST Python libraries automatically from the resolved local
  CST install
- checks whether HFSS Python support is available through `ansys.aedt.core`
- keeps local simulator execution disabled by default through
  `allow_unsafe_execution: false`

You do not need to run `leam-configure` before the first desktop launch.

## If Launch Is Blocked

LEAM Desktop requires at least one usable local backend before you can create or
open a workspace.

If startup is blocked:

1. Confirm that CST Studio Suite or Ansys Electronics Desktop is installed
   locally.
2. If HFSS is installed but Python support is missing, rerun:

   ```powershell
   pip install leam
   ```

3. Restart LEAM Desktop.
4. If your simulator is installed in a non-standard location, pin the exact
   CST/HFSS path in `~/.leam/config.json` or use `leam-configure` as an
   advanced fallback.

## Desktop Workflow

LEAM Desktop is a workspace-based tool:

- workspaces are stored under the user LEAM workspace root, typically
  `~/.leam/workspaces`
- recent-workspace metadata is stored under the user LEAM data directory,
  typically `~/.leam`
- missing backends are disabled in the UI
- if neither backend is available, the launchpad blocks entry into the workspace
  flow
- new workspaces and built-in examples include the execution branch by default,
  but actual CST/HFSS execution stays blocked unless you explicitly enable
  unsafe execution

Runtime execution remains intentionally separate from generation. LEAM can
generate CST VBA or HFSS Python artifacts without running them locally.

To enable local execution for one PowerShell session:

```powershell
$env:LEAM_ALLOW_UNSAFE_EXECUTION=1
```

Keep execution enabled only when you trust the prompts, attachments, and
generated artifacts involved in the run.

## Advanced Setup

Most users can skip this section.

`leam-configure` is still available for advanced and troubleshooting workflows.
Use it only when normal desktop startup still cannot detect the simulator you
already installed, or when you want to manage multiple config files
explicitly.

Helpful commands:

```powershell
leam-configure --dry-run
leam-configure --print-example
```

For pinned-version workflows, manual config editing, and multi-config setups,
see the advanced setup sections in
[Getting Started](https://github.com/TaoWu974/LEAM/blob/main/docs/getting_started.md).

## Documentation

- Desktop onboarding: https://github.com/TaoWu974/LEAM/blob/main/docs/getting_started.md
- Workflow reference: https://github.com/TaoWu974/LEAM/blob/main/docs/workflow_reference.md
- Python API: https://github.com/TaoWu974/LEAM/blob/main/docs/python_api.md

## Python API

If you want to use LEAM as a Python library instead of the desktop app, start
with the [Python API documentation](https://github.com/TaoWu974/LEAM/blob/main/docs/python_api.md).

## Built-in Examples

LEAM Desktop ships built-in example presets, but not every preset is available
in every installation.

- presets that only need text remain available in wheel installs
- presets that depend on repository-only assets are shown as unavailable unless
  those assets exist locally

If you want every example, including asset-backed ones such as the monopole
demo, use the source repository checkout.

## Links

- Homepage: https://github.com/TaoWu974/LEAM
- Paper: https://arxiv.org/abs/2504.18271
- Repository: https://github.com/TaoWu974/LEAM
- Documentation: https://taowu974.github.io/LEAM/

## License

MIT. See `LICENSE`.

## Citation

```bibtex
@inproceedings{wu2025large,
  title={Large Language Model-Based Intelligent Antenna Design System},
  author={Wu, Tao and Fu, Kexue and Hua, Qiang and Liu, Xinxin and Liu, Bo},
  booktitle={20th European Conference on Antennas and Propagation},
  year={2025},
  organization={IEEE}
}
```
