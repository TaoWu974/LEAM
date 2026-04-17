import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from leam.backends.hfss.paths import resource_path as hfss_resource_path
from leam.desktop.workflow.engine import WorkflowEngine
from leam.desktop.workflow.models import StepResult


class FakeRunner:
    def __init__(self, statuses=None):
        self.statuses = statuses or {}

    def run(self, definition, session):
        status = self.statuses.get(definition.id, "success")
        return StepResult(status=status, logs=[f"ran {definition.id}"])

    def detect_25d_from_artifacts(self, session, artifact_ids):
        return False

    def get_environment_report(self):
        return {
            "platform": "nt",
            "cst_path": "C:\\CST",
            "cst_path_ok": "yes",
            "cst_path_message": "",
            "cst_interface_ok": "yes",
            "cst_python_libraries_path": "C:\\CST\\AMD64\\python_cst_libraries",
            "cst_available": True,
            "cst_available_message": "",
            "hfss_path": "C:\\Program Files\\ANSYS Inc\\v252\\AnsysEM",
            "hfss_path_ok": "yes",
            "hfss_path_message": "",
            "pyaedt_ok": "yes",
            "hfss_available": True,
            "hfss_available_message": "",
            "unsafe_execution_enabled": True,
            "unsafe_execution_message": "",
            "available_backends": ["cst", "hfss"],
            "all_backends_unavailable": False,
        }


class DesktopWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.engine = WorkflowEngine(runner=FakeRunner())
        self.session = self.engine.create_session(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_default_workflow_is_strong_with_execution_enabled(self):
        step_ids = [
            definition.id
            for definition in self.engine.get_step_definitions(self.session)
        ]
        self.assertEqual(self.session.template, "strong_description")
        self.assertEqual(self.session.steps["input"].settings["backend"], "cst")
        self.assertTrue(self.session.steps["input"].settings["enable_execution"])
        self.assertFalse(self.session.steps["input"].settings["enable_25d"])
        self.assertIn("parameters", step_ids)
        self.assertIn("cst_project", step_ids)
        self.assertNotIn("hfss_project", step_ids)
        self.assertNotIn("initial_solids", step_ids)
        self.assertNotIn("model_2d", step_ids)

    def test_weak_template_adds_initial_solids_branch(self):
        self.session.steps["input"].settings["template"] = "weak_description"
        step_ids = [
            definition.id
            for definition in self.engine.get_step_definitions(self.session)
        ]
        self.assertIn("initial_solids", step_ids)
        self.assertIn("parameters", step_ids)
        self.assertIn("materials", step_ids)
        self.assertIn("solids", step_ids)

    def test_paper_reconstruction_uses_strong_main_chain(self):
        self.session.steps["input"].settings["template"] = "paper_reconstruction"
        step_ids = [
            definition.id
            for definition in self.engine.get_step_definitions(self.session)
        ]
        self.assertIn("parameters", step_ids)
        self.assertIn("solids", step_ids)
        self.assertNotIn("initial_solids", step_ids)

    def test_enabling_25d_adds_model_step_and_cst_dependency(self):
        self.session.steps["input"].settings["enable_25d"] = True
        self.session.steps["input"].settings["enable_execution"] = True
        step_ids = [
            definition.id
            for definition in self.engine.get_step_definitions(self.session)
        ]
        self.assertIn("model_2d", step_ids)

        cst_definition = self.engine.get_step_definition(self.session, "cst_project")
        self.assertIn("model_2d", cst_definition.upstream_step_ids)

    def test_hfss_25d_model_uses_extrude_resource(self):
        self.session.steps["input"].settings["backend"] = "hfss"
        self.session.steps["input"].settings["enable_25d"] = True

        definition = self.engine.get_step_definition(self.session, "model_2d")

        self.assertIn(hfss_resource_path("extrude.md"), definition.system_files)
        self.assertNotIn(
            hfss_resource_path("extrude_and_rotate.md"), definition.system_files
        )

    def test_disabling_25d_keeps_boolean_and_cst_on_3d_path_only(self):
        self.session.steps["input"].settings["enable_25d"] = False
        self.session.steps["input"].settings["enable_execution"] = True
        boolean_definition = self.engine.get_step_definition(self.session, "boolean")
        cst_definition = self.engine.get_step_definition(self.session, "cst_project")

        self.assertNotIn("model_2d", boolean_definition.upstream_step_ids)
        self.assertNotIn("model_2d", cst_definition.upstream_step_ids)

    def test_hfss_backend_swaps_execution_steps_and_artifact_defaults(self):
        self.session.steps["input"].settings["backend"] = "hfss"
        self.session.steps["input"].settings["enable_execution"] = True
        self.session.steps["input"].settings["enable_parameter_update"] = True
        step_ids = [
            definition.id
            for definition in self.engine.get_step_definitions(self.session)
        ]

        self.assertIn("hfss_project", step_ids)
        self.assertNotIn("cst_project", step_ids)

        model_3d_definition = self.engine.get_step_definition(self.session, "model_3d")
        self.assertEqual(
            model_3d_definition.default_selected_outputs["parameters"],
            ["parameters_json"],
        )
        self.assertEqual(
            model_3d_definition.default_selected_outputs["materials"],
            ["materials_json"],
        )

        hfss_definition = self.engine.get_step_definition(self.session, "hfss_project")
        self.assertEqual(
            hfss_definition.default_selected_outputs["parameters"],
            ["parameters_py"],
        )
        self.assertEqual(
            hfss_definition.default_selected_outputs["model_3d"],
            ["model_3d_py"],
        )
        self.assertEqual(
            hfss_definition.default_selected_outputs["boolean"],
            ["boolean_py"],
        )

        parameter_update_definition = self.engine.get_step_definition(
            self.session, "parameter_update"
        )
        self.assertEqual(
            parameter_update_definition.default_selected_outputs["parameters"],
            ["parameters_json"],
        )

    def test_disabling_execution_hides_cst_and_hfss_execution_steps(self):
        self.session.steps["input"].settings["enable_execution"] = False
        step_ids = [
            definition.id
            for definition in self.engine.get_step_definitions(self.session)
        ]
        self.assertNotIn("cst_project", step_ids)
        self.assertNotIn("hfss_project", step_ids)

    def test_legacy_enable_cst_is_migrated_to_backend_and_execution(self):
        self.session.steps["input"].settings.pop("backend", None)
        self.session.steps["input"].settings.pop("enable_execution", None)
        self.session.steps["input"].settings["enable_cst"] = False

        self.engine.refresh_session(self.session)

        self.assertEqual(self.session.steps["input"].settings["backend"], "cst")
        self.assertFalse(self.session.steps["input"].settings["enable_execution"])
        self.assertNotIn("enable_cst", self.session.steps["input"].settings)

    def test_legacy_execution_project_settings_are_removed(self):
        self.session.steps["input"].settings["execution_project_path"] = "legacy.cst"
        self.session.steps["input"].settings["overwrite_execution_project"] = True

        self.engine.refresh_session(self.session)

        self.assertNotIn("execution_project_path", self.session.steps["input"].settings)
        self.assertNotIn(
            "overwrite_execution_project",
            self.session.steps["input"].settings,
        )

    def test_optional_steps_are_hidden_until_upstream_is_ready(self):
        visible_ids = [
            definition.id
            for definition in self.engine.get_visible_step_definitions(self.session)
        ]
        self.assertNotIn("cst_project", visible_ids)

        for step_id in [
            "parameters",
            "materials",
            "solids",
            "check_solid",
            "dimensions",
            "model_3d",
            "boolean",
        ]:
            self.session.steps[step_id].status = "success"

        visible_ids = [
            definition.id
            for definition in self.engine.get_visible_step_definitions(self.session)
        ]
        self.assertIn("cst_project", visible_ids)

    def test_blocker_reports_first_missing_upstream_step(self):
        blocker = self.engine.get_step_blocker(self.session, "parameters")
        self.assertEqual(blocker, "Run `Workspace Setup` first.")

        self.session.steps["input"].status = "success"
        blocker = self.engine.get_step_blocker(self.session, "solids")
        self.assertEqual(blocker, "Run `Parameters` first.")

    def test_check_solid_refill_marks_target_and_blocks_descendants(self):
        for step_id in ["parameters", "materials", "solids", "dimensions"]:
            self.session.steps[step_id].status = "success"

        issues = [
            {
                "category": "parameters",
                "severity": "error",
                "path": "parameters.items[0].name",
                "issue": "Parameter mismatch detected.",
            }
        ]
        definition = self.engine.get_step_definition(self.session, "check_solid")
        routed = self.engine.apply_check_refills(
            self.session,
            definition,
            issues,
        )

        self.assertEqual(len(routed), 1)
        self.assertEqual(self.session.steps["parameters"].status, "rerun_required")
        self.assertIn(
            "Parameter mismatch detected.",
            self.session.steps["parameters"].refill_notes,
        )
        self.assertEqual(self.session.steps["materials"].status, "blocked_by_upstream")
        self.assertEqual(self.session.steps["solids"].status, "blocked_by_upstream")
        self.assertEqual(
            self.session.steps["dimensions"].status,
            "blocked_by_upstream",
        )

    def test_check_solid_prefers_llm_route_target_over_local_heuristic(self):
        for step_id in ["parameters", "materials", "solids", "dimensions"]:
            self.session.steps[step_id].status = "success"

        issues = [
            {
                "category": "parameters",
                "severity": "error",
                "route_to": "materials",
                "path": "parameters.items[0].name",
                "issue": "Use the correct custom material instead.",
            }
        ]
        definition = self.engine.get_step_definition(self.session, "check_solid")
        routed = self.engine.apply_check_refills(
            self.session,
            definition,
            issues,
        )

        self.assertEqual(len(routed), 1)
        self.assertEqual(routed[0].target_step_id, "materials")
        self.assertEqual(self.session.steps["materials"].status, "rerun_required")
        self.assertEqual(
            self.session.steps["parameters"].status,
            "success",
        )

    def test_successful_rerun_releases_blocked_descendants_to_stale(self):
        rerun_engine = WorkflowEngine(runner=FakeRunner({"parameters": "success"}))
        session = rerun_engine.create_session(self.tempdir.name)
        session.steps["parameters"].status = "rerun_required"
        session.steps["solids"].status = "blocked_by_upstream"
        session.steps["dimensions"].status = "blocked_by_upstream"

        rerun_engine.run_step(session, "parameters")

        self.assertEqual(session.steps["parameters"].status, "success")
        self.assertEqual(session.steps["solids"].status, "stale")
        self.assertEqual(session.steps["dimensions"].status, "stale")


if __name__ == "__main__":
    unittest.main()
