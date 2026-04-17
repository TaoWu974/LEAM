import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from leam.backends.cst.paths import prompt_path, resource_path
from leam.backends.cst.tools.dimension_generator import DimensionGenerator
from leam.backends.cst.tools.parameter_generator import (
    ParameterGenerator as CstParameterGenerator,
)
from leam.backends.cst.tools.parameter_update import (
    ParameterUpdater as CstParameterUpdater,
)
from leam.backends.cst.tools.strong_description_to_solids import (
    StrongDescriptionToSolids as CstStrongDescriptionToSolids,
)
from leam.backends.cst.tools.weak_description_to_solids import (
    WeakDescriptionToSolids as CstWeakDescriptionToSolids,
)
from leam.backends.hfss.paths import prompt_path as hfss_prompt_path
from leam.backends.hfss.paths import resource_path as hfss_resource_path
from leam.backends.hfss.tools.dimension_generator import (
    DimensionGenerator as HfssDimensionGenerator,
)
from leam.backends.hfss.tools.parameter_generator import (
    ParameterGenerator as HfssParameterGenerator,
)
from leam.backends.hfss.tools.parameter_update import (
    ParameterUpdater as HfssParameterUpdater,
)
from leam.backends.hfss.tools.strong_description_to_solids import (
    StrongDescriptionToSolids as HfssStrongDescriptionToSolids,
)

EXPECTED_TOOLS = [
    {"type": "code_interpreter", "container": {"type": "auto"}}
]
EXPECTED_TOOL_CHOICE = "auto"


class ParameterToolConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ensure_key_patcher = patch(
            "leam.core.llm_caller.ensure_openai_api_key",
            return_value="test-key",
        )
        self.openai_patcher = patch("leam.core.llm_caller.openai.OpenAI")

        self.ensure_key_patcher.start()
        self.mock_openai_cls = self.openai_patcher.start()
        self.mock_openai_cls.return_value = MagicMock()

    def tearDown(self) -> None:
        self.openai_patcher.stop()
        self.ensure_key_patcher.stop()

    def test_parameter_workflows_enable_code_interpreter_by_default(
        self,
    ) -> None:
        cst_generator = CstParameterGenerator()
        cst_updater = CstParameterUpdater()
        hfss_generator = HfssParameterGenerator()
        hfss_updater = HfssParameterUpdater()

        llm_callers = [
            cst_generator.vba_generator.generator.llm_caller,
            cst_updater.vba_generator.generator.llm_caller,
            hfss_generator.script_generator.generator.llm_caller,
            hfss_updater.script_generator.generator.llm_caller,
        ]

        for caller in llm_callers:
            self.assertEqual(caller.default_tools, EXPECTED_TOOLS)
            self.assertEqual(caller.default_tool_choice, EXPECTED_TOOL_CHOICE)

    def test_non_parameter_workflow_does_not_enable_tools(self) -> None:
        dimension_generator = DimensionGenerator()
        caller = dimension_generator

        self.assertIsNone(caller.default_tools)
        self.assertIsNone(caller.default_tool_choice)

    def test_solids_and_dimension_workflows_default_to_high_reasoning(self) -> None:
        cst_dimension_generator = DimensionGenerator()
        hfss_dimension_generator = HfssDimensionGenerator()
        cst_solids_generator = CstStrongDescriptionToSolids()
        hfss_solids_generator = HfssStrongDescriptionToSolids()

        self.assertEqual(cst_dimension_generator.reasoning_effort, "high")
        self.assertEqual(hfss_dimension_generator.reasoning_effort, "high")
        self.assertEqual(cst_solids_generator.reasoning_effort, "high")
        self.assertEqual(hfss_solids_generator.reasoning_effort, "high")

    def test_weak_description_to_solids_includes_modeling_resources(self) -> None:
        generator = CstWeakDescriptionToSolids()

        self.assertIn(
            prompt_path("weak_description_to_solids.md"),
            generator.prompt_files,
        )
        self.assertIn(resource_path("modeling_2d.md"), generator.prompt_files)
        self.assertIn(resource_path("modeling_3d.md"), generator.prompt_files)

    def test_hfss_parameter_prompts_use_variable_assignment_api(self) -> None:
        parameter_prompt = Path(hfss_prompt_path("parameter_prompt.md")).read_text(
            encoding="utf-8"
        )
        update_prompt = Path(
            hfss_prompt_path("parameter_update_prompt.md")
        ).read_text(encoding="utf-8")

        self.assertIn('hfss["$name"] = "expression"', parameter_prompt)
        self.assertIn("Use the `code_interpreter` tool", parameter_prompt)
        self.assertIn("Do not emit physical-specification variables or material variables", parameter_prompt)
        self.assertIn("Do not leave symbolic physics formulas in the final emitted parameters", parameter_prompt)
        self.assertIn("prefer keeping that clean dependent expression", parameter_prompt)
        self.assertIn("This preserves explicit HFSS design relationships", parameter_prompt)
        self.assertIn("Use emitted geometry-to-geometry expressions whenever the relation is exact", parameter_prompt)
        self.assertIn("Do not numerically expand a dependent geometric variable", parameter_prompt)
        self.assertIn("Include AEDT units", parameter_prompt)
        self.assertIn("Allowed AEDT Expression Functions", parameter_prompt)
        self.assertIn("`pow(x,y)`", parameter_prompt)
        self.assertIn("`ln(x)`", parameter_prompt)
        self.assertIn('"0.5*$w1"', parameter_prompt)
        self.assertIn('"($W_sub-$W_patch)/2"', parameter_prompt)
        self.assertIn('hfss["$patch_len"] = "28.8mm"', parameter_prompt)
        self.assertIn('hfss["$x_offset"] = "($W_sub-$W_patch)/2"', parameter_prompt)
        self.assertNotIn("Dim arrays", parameter_prompt)
        self.assertNotIn("CST-style behavior", parameter_prompt)
        self.assertNotIn("`Fix(x)`", parameter_prompt)
        self.assertNotIn("`Round(x, n)`", parameter_prompt)
        self.assertNotIn('hfss["$eps_sub"] = "4.3"', parameter_prompt)

        self.assertIn('hfss["$name"] = "expression"', update_prompt)
        self.assertIn("Use the `code_interpreter` tool", update_prompt)
        self.assertIn("Do not emit physical-specification variables or material variables", update_prompt)
        self.assertIn("prefer keeping that clean dependent expression", update_prompt)
        self.assertIn("Use emitted geometry-to-geometry expressions whenever the relation is exact", update_prompt)
        self.assertIn("Do not include any explicit rebuild/update call", update_prompt)
        self.assertNotIn("hfss.modeler.update()", update_prompt)
        self.assertNotIn("CST-style behavior", update_prompt)
        self.assertIn("Allowed AEDT Expression Functions", update_prompt)
        self.assertIn("`pow(x,y)`", update_prompt)
        self.assertIn('hfss["$slot_len"] = "0.5*$w2"', update_prompt)
        self.assertIn('hfss["$x_offset"] = "($W_sub-$W_patch)/2"', update_prompt)
        self.assertNotIn('hfss["$eps_sub"] = "4.3"', update_prompt)

    def test_hfss_resources_drop_cst_box_terminology(self) -> None:
        dimension_prompt = Path(
            hfss_prompt_path("dimension_prompt.md")
        ).read_text(encoding="utf-8")
        modeling_3d_resource = Path(
            hfss_resource_path("modeling_3d.md")
        ).read_text(encoding="utf-8")

        self.assertIn("Box, Cylinder, Extrude, Rotate", dimension_prompt)
        self.assertNotIn("Brick, Cylinder, Extrude, Rotate", dimension_prompt)
        self.assertIn("## New Box", modeling_3d_resource)
        self.assertNotIn("## New Box (Brick)", modeling_3d_resource)

    def test_hfss_boolean_resources_use_pyaedt_python_api(self) -> None:
        boolean_prompt = Path(hfss_prompt_path("boolean_prompt.md")).read_text(
            encoding="utf-8"
        )
        boolean_resource = Path(
            hfss_resource_path("boolean_operations.md")
        ).read_text(encoding="utf-8")

        self.assertIn("hfss.modeler", boolean_prompt)
        self.assertIn("Do NOT use `oEditor`", boolean_prompt)
        self.assertIn("Fail fast on PyAEDT failures", boolean_prompt)
        self.assertIn("If an operation returns `False`, immediately raise `RuntimeError(...)`", boolean_prompt)
        self.assertIn("hfss.modeler.unite", boolean_resource)
        self.assertIn("hfss.modeler.subtract", boolean_resource)
        self.assertIn("hfss.modeler.intersect", boolean_resource)
        self.assertIn("hfss.modeler.split", boolean_resource)
        self.assertIn("hfss.modeler.imprint", boolean_resource)
        self.assertIn("if result is False:", boolean_resource)
        self.assertIn("raise RuntimeError", boolean_resource)
        self.assertNotIn("oEditor.", boolean_resource)

    def test_hfss_extrude_resource_uses_thicken_sheet_api(self) -> None:
        extrude_resource = Path(
            hfss_resource_path("extrude.md")
        ).read_text(encoding="utf-8")

        self.assertIn("hfss.modeler.thicken_sheet", extrude_resource)
        self.assertIn("assignment=", extrude_resource)
        self.assertIn("thickness=", extrude_resource)
        self.assertIn("both_sides=False", extrude_resource)
        self.assertNotIn("oEditor.ThickenSheet", extrude_resource)

    def test_hfss_transform_resource_uses_pyaedt_object_methods(self) -> None:
        modeling_2d_prompt = Path(
            hfss_prompt_path("modeling_2d_prompt.md")
        ).read_text(encoding="utf-8")
        boolean_prompt = Path(
            hfss_prompt_path("boolean_prompt.md")
        ).read_text(encoding="utf-8")
        transform_resource = Path(
            hfss_resource_path("transform.md")
        ).read_text(encoding="utf-8")

        self.assertIn("profile_z", modeling_2d_prompt)
        self.assertIn("Do NOT sketch the profile at `z=0`", modeling_2d_prompt)
        self.assertIn("create the planar profile directly on that Z plane", modeling_2d_prompt)
        self.assertIn("directly spans that Z range", modeling_2d_prompt)
        self.assertIn("Do not fix placement in this step", boolean_prompt)
        self.assertIn("Do NOT move, rotate, mirror", boolean_prompt)
        self.assertIn('hfss.modeler["Box1"].move', transform_resource)
        self.assertIn('hfss.modeler["Box1"].rotate', transform_resource)
        self.assertIn('hfss.modeler["Box1"].mirror', transform_resource)
        self.assertIn("duplicate_along_line", transform_resource)
        self.assertIn("duplicate_around_axis", transform_resource)
        self.assertNotIn("oEditor.Move", transform_resource)
        self.assertNotIn("oEditor.Rotate", transform_resource)
        self.assertNotIn("oEditor.Mirror", transform_resource)

    def test_hfss_modeling_2d_prompt_and_resource_prefer_insert_segment_workflow(self) -> None:
        modeling_2d_prompt = Path(
            hfss_prompt_path("modeling_2d_prompt.md")
        ).read_text(encoding="utf-8")
        modeling_2d_resource = Path(
            hfss_resource_path("modeling_2d.md")
        ).read_text(encoding="utf-8")

        self.assertIn("Closed-profile construction", modeling_2d_prompt)
        self.assertIn("Build each closed contour in one `create_polyline(...)` call.", modeling_2d_prompt)
        self.assertIn("Close the contour inside that one call by repeating the start point", modeling_2d_prompt)
        self.assertIn("Use `segment_type=None` for all-line contours.", modeling_2d_prompt)
        self.assertIn('`segment_type=[...]` for compound contours made of `"Line"`, `"Arc"`, `"Spline"`, or `"AngularArc"` segments', modeling_2d_prompt)
        self.assertIn("After `create_polyline(...)`, call `cover_lines(...)`, then call `thicken_sheet(...)`.", modeling_2d_prompt)
        self.assertIn("call it directly without any `import` statement", modeling_2d_prompt)
        self.assertNotIn("insert_segment(...)", modeling_2d_prompt)
        self.assertNotIn("Fail fast on PyAEDT failures", modeling_2d_prompt)

        self.assertIn("## Closed Extruded Profile", modeling_2d_resource)
        self.assertIn("hfss.modeler.create_polyline(", modeling_2d_resource)
        self.assertIn('PolylineSegment(segment_type="Spline", num_points=4)', modeling_2d_resource)
        self.assertIn('PolylineSegment(segment_type="Line")', modeling_2d_resource)
        self.assertIn('hfss.modeler.cover_lines(assignment="SplineLineSplineLineTool")', modeling_2d_resource)
        self.assertIn("hfss.modeler.thicken_sheet(", modeling_2d_resource)
        self.assertNotIn(
            "from ansys.aedt.core.modeler.cad.primitives import PolylineSegment",
            modeling_2d_resource,
        )

    def test_hfss_modeling_3d_prompt_requires_fail_fast(self) -> None:
        modeling_3d_prompt = Path(
            hfss_prompt_path("modeling_3d_prompt.md")
        ).read_text(encoding="utf-8")

        self.assertIn("Fail fast on PyAEDT failures", modeling_3d_prompt)
        self.assertIn("If a mutating PyAEDT call returns `False`", modeling_3d_prompt)


if __name__ == "__main__":
    unittest.main()
