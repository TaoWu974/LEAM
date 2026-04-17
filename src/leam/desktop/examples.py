"""Built-in example presets for LEAM Desktop."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from .storage import DesktopSessionStore
from .workflow.engine import WorkflowEngine
from .workflow.models import WorkflowSession

REPO_ROOT = Path(__file__).resolve().parents[3]
ASSETS_DIR = REPO_ROOT / "examples" / "assets"


@dataclass(frozen=True)
class ExamplePreset:
    """One built-in workflow example."""

    key: str
    title: str
    template: str
    input_description: str
    enable_25d: bool = False
    backend: str = "cst"
    enable_execution: bool = True
    enable_parameter_update: bool = False
    flags: Dict[str, object] = field(default_factory=dict)
    input_attachments: List[Path] = field(default_factory=list)
    step_descriptions: Dict[str, str] = field(default_factory=dict)
    step_attachments: Dict[str, List[Path]] = field(default_factory=dict)

    def asset_paths(self) -> List[Path]:
        paths = list(self.input_attachments)
        for attachment_group in self.step_attachments.values():
            paths.extend(attachment_group)
        return paths


EXAMPLE_PRESETS: Dict[str, ExamplePreset] = {
    "vivaldi": ExamplePreset(
        key="vivaldi",
        title="Vivaldi Antenna",
        template="strong_description",
        enable_25d=True,
        backend="cst",
        enable_execution=True,
        enable_parameter_update=True,
        flags={"has_25d": True},
        input_description=(
            "We are going to model a Vivaldi antenna. It should consist of a "
            "substrate, a tapered slot (on the front of the substrate), two "
            "rectangles and a circle for feeding (on the back of the substrate). "
            "The desired working frequency is from 3.0 - 13.5 GHz, so the "
            "substrate should be 30x20 mm (W x L). "
            "Consider the left bottom corner under the substrate as origin of "
            "axis (0,0,0). The substrate should be Rogers RO4003C of thickness ts "
            "(a fixed value 0.813), so the right top corner on the front is "
            "(30,20,ts). To model the tapered slot on the front, you need a full "
            "cover patch X-range [0,30], Y-range [0,20], "
            "Z-range [ts,ts+tp], tp should be a fixed value of 0.035. Then "
            "you need to use the patch to subtract a closed spline structure "
            "(extruded) and a circle. To form the slot, you need to model two "
            "symmetric splines and connect their top and bottom points to form a "
            "closed shape to extrude. The left spline is defined by 20 points, "
            "whose y are 20, 19, ... 1, and the X axis should be variables "
            "(20 variables). The point x values should be ascending within "
            "(0, 15), exclusive. Meanwhile, the right half X should be 30-X_i. "
            "Because the Vivaldi tapered slot is complex, add step-by-step "
            "instruction to the description. The circle's center is located at "
            "(15, gap+r1), and its radius should be r1 (2 variables). On the "
            "back, the first rectangle starts from the right, and should be X "
            "range [30-l1, 30], Y range [pf, pf+w1], Z range [-tp, 0], whose "
            "dimension is l1 x w1 x tp (2 parameters, tp is fixed). The second "
            "rectangle is X range [30-l1-l2, 30-l1], Y range [pf + 0.5 * "
            "(w1 - w2), pf + 0.5 * (w1 + w2)], Z range [-tp, 0], whose dimension "
            "is l2 x w2 x tp (2 parameters, tp is fixed). From a geometry view, "
            "the second rectangle is connected to the end of the first rectangle "
            "and aligned to the middle of it. Lastly, the circle on the back is a "
            "cylinder whose center is at (30-l1-l2, pf + 0.5 * w1) with radius r2 "
            "(1 variable) and Z range [-tp, 0]."
        ),
        step_descriptions={
            "parameter_update": (
                "I want change spline definition's X_1 to X_20 values to form a "
                "Vivaldi shape and increase the rectangles length on the back and "
                "the radius of the circle on the back."
            )
        },
    ),
    "slotted_patch": ExamplePreset(
        key="slotted_patch",
        title="Slotted Patch",
        template="weak_description",
        backend="cst",
        enable_execution=True,
        input_description=(
            "I want to design a rectangular-slotted rectangular-patch antenna "
            "working at 2.45GHz."
        ),
    ),
    "monopole": ExamplePreset(
        key="monopole",
        title="Slotted Monopole",
        template="paper_reconstruction",
        backend="cst",
        enable_execution=True,
        enable_parameter_update=True,
        input_description=(
            "The layout of the slotted monopole antenna is shown in Fig. 4. "
            "The antenna is implemented on an FR-4 substrate with a thickness "
            "of 0.8 mm, a relative permittivity of 4.4, and a loss tangent of "
            "0.02. It consists of a driven circular patch radiator and two "
            "uniform rectangular metal planes separated by the microstrip line. "
            "Two slots are fused at the center of the driven circular patch "
            "radiator to form a quasi-cross slot, and the geometry of the slot "
            "helps control the surface current distribution. Meanwhile, the "
            "rectangular planes act as a coplanar partial ground."
        ),
        input_attachments=[ASSETS_DIR / "Monopole.png"],
        step_descriptions={
            "parameters": (
                "There are 12 variables. There are two errors in the graph, SL "
                "should equal to ML + DPR + 0.2."
                "And SLH and SLT values need swapping."
            ),
            "dimensions": (
                "SLH is the length of the horizontal slot on the x-axis. SLV is "
                "the length of the vertical slot on the y-axis. SLT is the width "
                "of both the rectangular slots. Two slots should be centered at "
                "the center of circle. IMPORTANT: RPL definition is not "
                "straightforward, the length of RP should be ML-RPL. The circle's "
                "center is at (SW/2, ML). The patch and the ground planes are all "
                "on the substrate."
            ),
            "boolean": (
                "We need add the feed to the patch then subtract slots from the patch."
            ),
            "parameter_update": (
                "I want to demonstrate with the following parameters. "
                "$DP_{R}$ = 6.58, $S_{W}$ = 13.43, $SL_{T}$ = 1, $SL_{V}$ = 7.9, "
                "$SL_{H}$ = 7.9, $M_{L}$ = 25.08, $RP_{L}$ = 6.67, $M_{W}$ = 1.2, "
                "$M_{G}$ = 0.3, $S_{L}$ = 31.86, $RP_{W}$ = 5.815. (unit: mm.)}"
            ),
        },
        step_attachments={
            "parameters": [ASSETS_DIR / "Monopole_para.png"],
        },
    ),
}


def is_example_preset_available(preset: ExamplePreset) -> bool:
    """Return whether all repo-backed assets for this preset are available."""
    return all(path.exists() for path in preset.asset_paths())


def available_example_presets() -> Dict[str, ExamplePreset]:
    """Return the subset of built-in examples that can run in this install."""
    return {
        key: preset
        for key, preset in EXAMPLE_PRESETS.items()
        if is_example_preset_available(preset)
    }


def unavailable_example_presets() -> Dict[str, ExamplePreset]:
    """Return built-in examples that rely on repo-only assets."""
    return {
        key: preset
        for key, preset in EXAMPLE_PRESETS.items()
        if not is_example_preset_available(preset)
    }


def get_example_preset(
    preset_key: str,
    *,
    require_available: bool = False,
) -> ExamplePreset:
    """Fetch one example preset and optionally require local asset availability."""
    if preset_key not in EXAMPLE_PRESETS:
        raise KeyError(f"Unknown example preset: {preset_key}")
    preset = EXAMPLE_PRESETS[preset_key]
    if require_available and not is_example_preset_available(preset):
        raise ValueError(
            f"Example `{preset.title}` requires repository assets that are not "
            "included in this installation."
        )
    return preset


def apply_example_preset(
    session: WorkflowSession,
    engine: WorkflowEngine,
    store: DesktopSessionStore,
    preset_key: str,
) -> ExamplePreset:
    """Populate a new session with one built-in example."""

    preset = get_example_preset(preset_key, require_available=True)
    session.template = preset.template
    input_state = session.steps["input"]
    input_state.settings["template"] = preset.template
    input_state.settings["enable_25d"] = preset.enable_25d
    input_state.settings["backend"] = preset.backend
    input_state.settings["enable_execution"] = preset.enable_execution
    input_state.settings["enable_parameter_update"] = (
        preset.enable_parameter_update
    )
    input_state.description = preset.input_description
    input_state.attachments = []
    session.flags = dict(preset.flags)

    engine.refresh_session(session)

    for step_id, state in session.steps.items():
        if step_id == "input":
            continue
        state.description = ""
        state.refill_notes = ""
        state.attachments = []
        state.artifact_ids = []
        state.selected_artifact_ids = []
        state.issues = []
        state.raw_issues = []
        state.logs = []
        state.last_error = ""
        state.status = "idle"
        state.settings.pop("artifact_selection_touched", None)

    for attachment_path in preset.input_attachments:
        if attachment_path.exists():
            input_state.attachments.append(
                store.import_attachment(
                    session,
                    "input",
                    str(attachment_path),
                )
            )

    for step_id, description in preset.step_descriptions.items():
        if step_id in session.steps:
            session.steps[step_id].description = description

    for step_id, paths in preset.step_attachments.items():
        if step_id not in session.steps:
            continue
        for attachment_path in paths:
            if attachment_path.exists():
                session.steps[step_id].attachments.append(
                    store.import_attachment(
                        session,
                        step_id,
                        str(attachment_path),
                    )
                )

    engine.refresh_session(session)
    return preset
