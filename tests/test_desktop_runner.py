import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from leam.config import RECOMMENDED_DESKTOP_INSTALL_COMMAND
from leam.core.errors import InputValidationError
from leam.desktop.services.runner import DesktopWorkflowRunner
from leam.desktop.workflow.engine import WorkflowEngine
from leam.desktop.workflow.models import ArtifactRef, AttachmentRef


class DesktopRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.runner = DesktopWorkflowRunner()
        self.engine = WorkflowEngine(runner=self.runner)
        self.session = self.engine.create_session(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_collect_inputs_merges_case_text_attachments_and_selected_artifacts(self):
        image_path = Path(self.tempdir.name) / "case.png"
        image_path.write_bytes(b"png")
        pdf_path = Path(self.tempdir.name) / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")
        text_path = Path(self.tempdir.name) / "context.txt"
        text_path.write_text("context", encoding="utf-8")
        material_path = Path(self.tempdir.name) / "Rogers_RO4003C.mtd"
        material_path.write_text("material Rogers RO4003C", encoding="utf-8")
        description_path = Path(self.tempdir.name) / "description.txt"
        description_path.write_text("base case", encoding="utf-8")
        artifact_path = Path(self.tempdir.name) / "parameters.json"
        artifact_path.write_text("{}", encoding="utf-8")

        self.session.steps["input"].description = "base case"
        self.session.steps["input"].attachments.append(
            AttachmentRef(
                id="input-image",
                name="case.png",
                path=str(image_path),
                kind="image",
            )
        )
        self.session.steps["input"].attachments.append(
            AttachmentRef(
                id="input-description",
                name="description.txt",
                path=str(description_path),
                kind="text",
                editable=True,
                origin="description",
            )
        )
        self.session.steps["input"].attachments.append(
            AttachmentRef(
                id="input-pdf",
                name="paper.pdf",
                path=str(pdf_path),
                kind="pdf",
            )
        )
        self.session.steps["solids"].description = "step hint"
        self.session.steps["solids"].refill_notes = "rerun because check solid failed"
        self.session.steps["solids"].attachments.append(
            AttachmentRef(
                id="solids-text",
                name="context.txt",
                path=str(text_path),
                kind="text",
                editable=True,
            )
        )
        self.session.steps["solids"].attachments.append(
            AttachmentRef(
                id="solids-material-library",
                name="Rogers_RO4003C.mtd",
                path=str(material_path),
                kind="file",
            )
        )
        self.session.artifacts["parameters-parameters_json"] = ArtifactRef(
            id="parameters-parameters_json",
            step_id="parameters",
            label="parameters_json",
            path=str(artifact_path),
            kind="json",
        )
        self.session.steps["parameters"].artifact_ids = [
            "parameters-parameters_json"
        ]
        self.session.steps["solids"].selected_artifact_ids = [
            "parameters-parameters_json"
        ]
        self.session.steps["solids"].settings["artifact_selection_touched"] = True
        definition = self.engine.get_step_definition(self.session, "solids")

        description, image_paths, pdf_paths, prompt_files = self.runner._collect_inputs(
            definition,
            self.session,
        )

        self.assertIn("base case", description)
        self.assertIn("step hint", description)
        self.assertIn("rerun because check solid failed", description)
        self.assertEqual(image_paths, [str(image_path)])
        self.assertEqual(pdf_paths, [str(pdf_path)])
        self.assertEqual(
            prompt_files,
            [str(text_path), str(material_path), str(artifact_path)],
        )

    def test_collect_inputs_rejects_enabled_unsupported_image_attachments(self):
        gif_path = Path(self.tempdir.name) / "legacy.gif"
        gif_path.write_bytes(b"gif89a")

        self.session.steps["input"].description = "base case"
        self.session.steps["input"].attachments.append(
            AttachmentRef(
                id="input-gif",
                name="legacy.gif",
                path=str(gif_path),
                kind="image",
            )
        )
        definition = self.engine.get_step_definition(self.session, "parameters")

        with self.assertRaises(InputValidationError) as ctx:
            self.runner._collect_inputs(definition, self.session)

        self.assertIn("legacy.gif", str(ctx.exception))
        self.assertIn("PNG and JPEG", str(ctx.exception))

    def test_collect_inputs_appends_25d_expectation_for_solids_when_enabled(self):
        self.session.steps["input"].description = "base case"
        self.session.steps["input"].settings["enable_25d"] = True
        self.session.steps["solids"].description = "step hint"
        definition = self.engine.get_step_definition(self.session, "solids")

        description, _image_paths, _pdf_paths, _prompt_files = self.runner._collect_inputs(
            definition,
            self.session,
        )

        self.assertIn("base case", description)
        self.assertIn("step hint", description)
        self.assertIn("There should be 2.5D element", description)

    def test_collect_inputs_appends_no_25d_expectation_for_solids_when_disabled(self):
        self.session.steps["input"].description = "base case"
        self.session.steps["input"].settings["enable_25d"] = False
        self.session.steps["solids"].description = "step hint"
        definition = self.engine.get_step_definition(self.session, "solids")

        description, _image_paths, _pdf_paths, _prompt_files = self.runner._collect_inputs(
            definition,
            self.session,
        )

        self.assertIn("base case", description)
        self.assertIn("step hint", description)
        self.assertIn("There should be no 2.5D element", description)

    def test_detect_25d_from_solids_artifact(self):
        solids_path = Path(self.tempdir.name) / "solids.json"
        solids_path.write_text(
            json.dumps(
                {
                    "solids": [
                        {"Type": "3D", "name": "substrate"},
                        {"Type": "2.5D", "name": "slot"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.session.artifacts["solids-solids_json"] = ArtifactRef(
            id="solids-solids_json",
            step_id="solids",
            label="solids_json",
            path=str(solids_path),
            kind="json",
        )

        result = self.runner.detect_25d_from_artifacts(
            self.session,
            ["solids-solids_json"],
        )

        self.assertTrue(result)

    def test_create_run_dir_uses_step_specific_incrementing_subfolders(self):
        first_run_dir = self.runner._create_run_dir(self.session, "parameters")
        self.session.steps["parameters"].run_count = 1
        second_run_dir = self.runner._create_run_dir(self.session, "parameters")

        self.assertTrue(Path(first_run_dir).exists())
        self.assertTrue(Path(second_run_dir).exists())
        self.assertIn(str(Path(self.tempdir.name) / "artifacts" / "parameters"), first_run_dir)
        self.assertNotEqual(first_run_dir, second_run_dir)
        self.assertIn("run_001_", Path(first_run_dir).name)
        self.assertIn("run_002_", Path(second_run_dir).name)

    def test_environment_report_includes_hfss_fields(self):
        with patch(
            "leam.desktop.services.runner.resolve_cst_path",
            return_value="C:\\CST",
        ), patch(
            "leam.desktop.services.runner.resolve_cst_python_libraries_path",
            return_value="C:\\CST\\AMD64\\python_cst_libraries",
        ), patch(
            "leam.desktop.services.runner.validate_cst_path",
            return_value=(True, ""),
        ), patch(
            "leam.desktop.services.runner._ensure_cst_runtime_connected",
            return_value=(True, ""),
        ), patch(
            "leam.desktop.services.runner.resolve_hfss_path",
            return_value="C:\\AnsysEM",
        ), patch(
            "leam.desktop.services.runner.validate_hfss_path",
            return_value=(True, ""),
        ), patch(
            "leam.desktop.services.runner._module_spec_exists",
            return_value=True,
        ), patch(
            "leam.desktop.services.runner.resolve_allow_unsafe_execution",
            return_value=False,
        ):
            report = self.runner.get_environment_report()

        self.assertEqual(report["cst_path_ok"], "yes")
        self.assertEqual(report["hfss_path_ok"], "yes")
        self.assertEqual(report["pyaedt_ok"], "yes")
        self.assertTrue(report["cst_available"])
        self.assertTrue(report["hfss_available"])
        self.assertFalse(report["unsafe_execution_enabled"])
        self.assertEqual(report["available_backends"], ["cst", "hfss"])

    def test_environment_report_marks_hfss_unavailable_without_pyaedt(self):
        with patch(
            "leam.desktop.services.runner.resolve_cst_path",
            return_value="C:\\CST",
        ), patch(
            "leam.desktop.services.runner.resolve_cst_python_libraries_path",
            return_value="C:\\CST\\AMD64\\python_cst_libraries",
        ), patch(
            "leam.desktop.services.runner.validate_cst_path",
            return_value=(True, ""),
        ), patch(
            "leam.desktop.services.runner._ensure_cst_runtime_connected",
            return_value=(True, ""),
        ), patch(
            "leam.desktop.services.runner.resolve_hfss_path",
            return_value="C:\\AnsysEM",
        ), patch(
            "leam.desktop.services.runner.validate_hfss_path",
            return_value=(True, ""),
        ), patch(
            "leam.desktop.services.runner._module_spec_exists",
            return_value=None,
        ), patch(
            "leam.desktop.services.runner.resolve_allow_unsafe_execution",
            return_value=False,
        ):
            report = self.runner.get_environment_report()

        self.assertTrue(report["cst_available"])
        self.assertFalse(report["hfss_available"])
        self.assertEqual(report["available_backends"], ["cst"])
        self.assertIn("ansys.aedt.core", report["hfss_available_message"])
        self.assertIn(RECOMMENDED_DESKTOP_INSTALL_COMMAND, report["hfss_available_message"])
        self.assertIn("LEAM_ALLOW_UNSAFE_EXECUTION", report["unsafe_execution_message"])

    def test_environment_report_treats_hfss_path_override_as_advanced_fallback(self):
        with patch(
            "leam.desktop.services.runner.resolve_cst_path",
            return_value="C:\\CST",
        ), patch(
            "leam.desktop.services.runner.resolve_cst_python_libraries_path",
            return_value="C:\\CST\\AMD64\\python_cst_libraries",
        ), patch(
            "leam.desktop.services.runner.validate_cst_path",
            return_value=(True, ""),
        ), patch(
            "leam.desktop.services.runner._ensure_cst_runtime_connected",
            return_value=(True, ""),
        ), patch(
            "leam.desktop.services.runner.resolve_hfss_path",
            return_value=None,
        ), patch(
            "leam.desktop.services.runner.validate_hfss_path",
            return_value=(False, ""),
        ), patch(
            "leam.desktop.services.runner._module_spec_exists",
            return_value=True,
        ), patch(
            "leam.desktop.services.runner.resolve_allow_unsafe_execution",
            return_value=False,
        ):
            report = self.runner.get_environment_report()

        self.assertTrue(report["cst_available"])
        self.assertFalse(report["hfss_available"])
        self.assertEqual(report["available_backends"], ["cst"])
        self.assertIn("Install HFSS locally first.", report["hfss_available_message"])
        self.assertIn("advanced override", report["hfss_available_message"])

    def test_environment_report_treats_cst_path_override_as_advanced_fallback(self):
        with patch(
            "leam.desktop.services.runner.resolve_cst_path",
            return_value=None,
        ), patch(
            "leam.desktop.services.runner.resolve_cst_python_libraries_path",
            return_value=None,
        ), patch(
            "leam.desktop.services.runner.validate_cst_path",
            return_value=(False, ""),
        ), patch(
            "leam.desktop.services.runner._ensure_cst_runtime_connected",
            return_value=(False, ""),
        ), patch(
            "leam.desktop.services.runner.resolve_hfss_path",
            return_value="C:\\AnsysEM",
        ), patch(
            "leam.desktop.services.runner.validate_hfss_path",
            return_value=(True, ""),
        ), patch(
            "leam.desktop.services.runner._module_spec_exists",
            return_value=True,
        ), patch(
            "leam.desktop.services.runner.resolve_allow_unsafe_execution",
            return_value=False,
        ):
            report = self.runner.get_environment_report()

        self.assertFalse(report["cst_available"])
        self.assertTrue(report["hfss_available"])
        self.assertEqual(report["available_backends"], ["hfss"])
        self.assertIn("Install CST locally first.", report["cst_available_message"])
        self.assertIn("advanced override", report["cst_available_message"])

    def test_hfss_parameters_step_registers_python_and_json_artifacts(self):
        self.session.steps["input"].settings["backend"] = "hfss"
        self.engine.refresh_session(self.session)
        definition = self.engine.get_step_definition(self.session, "parameters")

        with patch(
            "leam.backends.hfss.tools.parameter_generator.ParameterGenerator"
        ) as generator_cls:
            instance = MagicMock()

            def _factory(*args, **kwargs):
                instance.save_dir = kwargs["save_dir"]
                return instance

            def _write_outputs(**kwargs):
                run_dir = Path(instance.save_dir)
                (run_dir / "parameters.py").write_text(
                    'hfss["$w1"] = "1mm"\n',
                    encoding="utf-8",
                )
                (run_dir / "parameters.json").write_text(
                    json.dumps(
                        {
                            "representation": "parameters",
                            "items": [{"name": "$w1", "value": "1mm", "notes": ""}],
                        }
                    ),
                    encoding="utf-8",
                )

            generator_cls.side_effect = _factory
            instance.generate_parameters.side_effect = _write_outputs
            result = self.runner.run(definition, self.session)

        self.assertEqual(result.status, "success")
        labels = {
            self.session.artifacts[artifact_id].label for artifact_id in result.artifact_ids
        }
        self.assertEqual(labels, {"parameters_py", "parameters_json"})

    def test_hfss_materials_step_registers_json_only_artifact(self):
        self.session.steps["input"].settings["backend"] = "hfss"
        self.engine.refresh_session(self.session)
        definition = self.engine.get_step_definition(self.session, "materials")

        with patch(
            "leam.backends.hfss.tools.materials.MaterialsProcessor"
        ) as processor_cls:
            instance = MagicMock()

            def _factory(*args, **kwargs):
                instance.save_dir = kwargs["save_dir"]
                return instance

            def _write_outputs(**kwargs):
                run_dir = Path(instance.save_dir)
                (run_dir / "materials.json").write_text(
                    json.dumps(
                        {
                            "representation": "materials",
                            "items": [{"name": "pec", "source": "builtin", "builtin": True, "notes": ""}],
                        }
                    ),
                    encoding="utf-8",
                )

            processor_cls.side_effect = _factory
            instance.generate_materials.side_effect = _write_outputs
            result = self.runner.run(definition, self.session)

        self.assertEqual(result.status, "success")
        labels = {
            self.session.artifacts[artifact_id].label for artifact_id in result.artifact_ids
        }
        self.assertEqual(labels, {"materials_json"})

    def test_hfss_check_solid_step_uses_hfss_backend_checker(self):
        self.session.steps["input"].settings["backend"] = "hfss"
        self.engine.refresh_session(self.session)
        definition = self.engine.get_step_definition(self.session, "check_solid")

        solids_path = Path(self.tempdir.name) / "solids.json"
        parameters_path = Path(self.tempdir.name) / "parameters.json"
        materials_path = Path(self.tempdir.name) / "materials.json"
        solids_path.write_text(json.dumps({"solids": []}), encoding="utf-8")
        parameters_path.write_text(json.dumps({"items": []}), encoding="utf-8")
        materials_path.write_text(json.dumps({"items": []}), encoding="utf-8")

        artifacts = {
            "solids-solids_json": ArtifactRef(
                id="solids-solids_json",
                step_id="solids",
                label="solids_json",
                path=str(solids_path),
                kind="json",
            ),
            "parameters-parameters_json": ArtifactRef(
                id="parameters-parameters_json",
                step_id="parameters",
                label="parameters_json",
                path=str(parameters_path),
                kind="json",
            ),
            "materials-materials_json": ArtifactRef(
                id="materials-materials_json",
                step_id="materials",
                label="materials_json",
                path=str(materials_path),
                kind="json",
            ),
        }
        self.session.artifacts.update(artifacts)
        self.session.steps["check_solid"].selected_artifact_ids = list(artifacts)

        with patch(
            "leam.backends.hfss.tools.check_solid.CheckSolid"
        ) as hfss_cls, patch(
            "leam.backends.cst.tools.check_solid.CheckSolid"
        ) as cst_cls:
            instance = MagicMock()

            def _factory(*args, **kwargs):
                instance.save_dir = kwargs["save_dir"]
                return instance

            def _run_check(**kwargs):
                report_path = Path(instance.save_dir) / kwargs["save_as"]
                report_path.write_text(
                    json.dumps(
                        {
                            "status": "ok",
                            "issues": [],
                            "issue_counts": {
                                "total": 0,
                                "errors": 0,
                                "warnings": 0,
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                return json.loads(report_path.read_text(encoding="utf-8"))

            hfss_cls.side_effect = _factory
            instance.check.side_effect = _run_check

            result = self.runner.run(definition, self.session)

        self.assertEqual(result.status, "success")
        hfss_cls.assert_called_once()
        cst_cls.assert_not_called()
        instance.check.assert_called_once()

    def test_hfss_project_step_invokes_hfss_runner(self):
        self.session.steps["input"].settings["backend"] = "hfss"
        self.session.steps["input"].settings["enable_execution"] = True
        self.engine.refresh_session(self.session)

        definition = self.engine.get_step_definition(self.session, "hfss_project")
        paths = {}
        for name in ["parameters.py", "model_3d.py", "boolean.py"]:
            path = Path(self.tempdir.name) / name
            path.write_text("# stub\n", encoding="utf-8")
            paths[name] = str(path)

        artifacts = {
            "parameters-parameters_py": ArtifactRef(
                id="parameters-parameters_py",
                step_id="parameters",
                label="parameters_py",
                path=paths["parameters.py"],
                kind="text",
            ),
            "model_3d-model_3d_py": ArtifactRef(
                id="model_3d-model_3d_py",
                step_id="model_3d",
                label="model_3d_py",
                path=paths["model_3d.py"],
                kind="text",
            ),
            "boolean-boolean_py": ArtifactRef(
                id="boolean-boolean_py",
                step_id="boolean",
                label="boolean_py",
                path=paths["boolean.py"],
                kind="text",
            ),
        }
        self.session.artifacts.update(artifacts)
        self.session.steps["hfss_project"].selected_artifact_ids = list(artifacts)

        self.runner.get_environment_report = MagicMock(
            return_value={
                "platform": "nt",
                "cst_path": "",
                "cst_path_ok": "no",
                "cst_path_message": "",
                "cst_interface_ok": "no",
                "cst_python_libraries_path": "",
                "cst_available": False,
                "cst_available_message": "",
                "hfss_path": "C:\\AnsysEM",
                "hfss_path_ok": "yes",
                "hfss_path_message": "",
                "pyaedt_ok": "yes",
                "hfss_available": True,
                "hfss_available_message": "",
                "unsafe_execution_enabled": True,
                "unsafe_execution_message": "",
                "available_backends": ["hfss"],
                "all_backends_unavailable": False,
            }
        )

        with patch("leam.backends.hfss.tools.hfss_runner.HfssRunner") as runner_cls:
            result = self.runner.run(definition, self.session)

        self.assertEqual(result.status, "success")
        runner_cls.assert_called_once()
        runner_kwargs = runner_cls.call_args.kwargs
        self.assertEqual(runner_kwargs["new_desktop"], True)
        self.assertEqual(runner_kwargs["non_graphical"], False)
        self.assertTrue(str(runner_kwargs["project_path"]).endswith("antenna.aedt"))
        instance = runner_cls.return_value
        instance.set_build_tasks.assert_called_once()
        instance.create_project.assert_called_once()
        _, create_kwargs = instance.create_project.call_args
        self.assertEqual(create_kwargs["save_path"], runner_kwargs["project_path"])

    def test_hfss_project_step_requires_execution_opt_in(self):
        self.session.steps["input"].settings["backend"] = "hfss"
        self.session.steps["input"].settings["enable_execution"] = True
        self.engine.refresh_session(self.session)

        definition = self.engine.get_step_definition(self.session, "hfss_project")
        for artifact_id, label, filename, step_id in [
            (
                "parameters-parameters_py",
                "parameters_py",
                "parameters.py",
                "parameters",
            ),
            ("model_3d-model_3d_py", "model_3d_py", "model_3d.py", "model_3d"),
            ("boolean-boolean_py", "boolean_py", "boolean.py", "boolean"),
        ]:
            path = Path(self.tempdir.name) / filename
            path.write_text("# stub\n", encoding="utf-8")
            self.session.artifacts[artifact_id] = ArtifactRef(
                id=artifact_id,
                step_id=step_id,
                label=label,
                path=str(path),
                kind="text",
            )
        self.session.steps["hfss_project"].selected_artifact_ids = list(
            self.session.artifacts.keys()
        )

        self.runner.get_environment_report = MagicMock(
            return_value={
                "platform": "nt",
                "cst_path": "",
                "cst_path_ok": "no",
                "cst_path_message": "",
                "cst_interface_ok": "no",
                "cst_python_libraries_path": "",
                "cst_available": False,
                "cst_available_message": "",
                "hfss_path": "C:\\AnsysEM",
                "hfss_path_ok": "yes",
                "hfss_path_message": "",
                "pyaedt_ok": "yes",
                "hfss_available": True,
                "hfss_available_message": "",
                "unsafe_execution_enabled": False,
                "unsafe_execution_message": "Execution disabled.",
                "available_backends": ["hfss"],
                "all_backends_unavailable": False,
            }
        )

        with patch("leam.backends.hfss.tools.hfss_runner.HfssRunner") as runner_cls:
            with self.assertRaises(RuntimeError) as ctx:
                self.runner.run(definition, self.session)

        self.assertIn("Execution disabled.", str(ctx.exception))
        runner_cls.assert_not_called()

    def test_cst_project_step_invokes_cst_runner(self):
        self.session.steps["input"].settings["enable_execution"] = True
        self.engine.refresh_session(self.session)

        definition = self.engine.get_step_definition(self.session, "cst_project")
        artifacts = {}
        for artifact_id, label, filename, step_id in [
            (
                "parameters-parameters_bas",
                "parameters_bas",
                "parameters.bas",
                "parameters",
            ),
            ("materials-materials_bas", "materials_bas", "materials.bas", "materials"),
            ("model_3d-model_3d_bas", "model_3d_bas", "model_3d.bas", "model_3d"),
            ("boolean-boolean_bas", "boolean_bas", "boolean.bas", "boolean"),
        ]:
            path = Path(self.tempdir.name) / filename
            path.write_text("' stub\n", encoding="utf-8")
            artifacts[artifact_id] = ArtifactRef(
                id=artifact_id,
                step_id=step_id,
                label=label,
                path=str(path),
                kind="text",
            )
        self.session.artifacts.update(artifacts)
        self.session.steps["cst_project"].selected_artifact_ids = list(artifacts)

        self.runner.get_environment_report = MagicMock(
            return_value={
                "platform": "nt",
                "cst_path": "C:\\CST",
                "cst_path_ok": "yes",
                "cst_path_message": "",
                "cst_interface_ok": "yes",
                "cst_python_libraries_path": "C:\\CST\\AMD64\\python_cst_libraries",
                "cst_available": True,
                "cst_available_message": "",
                "hfss_path": "",
                "hfss_path_ok": "no",
                "hfss_path_message": "",
                "pyaedt_ok": "no",
                "hfss_available": False,
                "hfss_available_message": "",
                "unsafe_execution_enabled": True,
                "unsafe_execution_message": "",
                "available_backends": ["cst"],
                "all_backends_unavailable": False,
            }
        )

        with patch(
            "leam.desktop.services.runner._get_cst_runner_cls"
        ) as get_runner_cls:
            runner_cls = MagicMock()
            get_runner_cls.return_value = runner_cls
            result = self.runner.run(definition, self.session)

        self.assertEqual(result.status, "success")
        runner_cls.assert_called_once_with(
            create_new_if_none=False,
            allow_unsafe_execution=True,
        )
        instance = runner_cls.return_value
        instance.set_history_tasks.assert_called_once()
        instance.create_project.assert_called_once()
        args, _ = instance.create_project.call_args
        self.assertEqual(Path(args[0]).name, "antenna.cst")
        self.assertEqual(result.preview_text, str(Path(args[0])))

    def test_hfss_update_step_invokes_hfss_runner(self):
        self.session.steps["input"].settings["backend"] = "hfss"
        self.session.steps["input"].settings["enable_execution"] = True
        self.session.steps["input"].settings["enable_parameter_update"] = True
        self.engine.refresh_session(self.session)

        definition = self.engine.get_step_definition(self.session, "hfss_update")
        update_path = Path(self.tempdir.name) / "parameter_update.py"
        update_path.write_text("# stub\n", encoding="utf-8")
        project_path = Path(self.tempdir.name) / "antenna.aedt"
        project_path.write_text("stub", encoding="utf-8")
        self.session.artifacts.update(
            {
                "parameter_update-parameter_update_py": ArtifactRef(
                    id="parameter_update-parameter_update_py",
                    step_id="parameter_update",
                    label="parameter_update_py",
                    path=str(update_path),
                    kind="text",
                ),
                "hfss_project-hfss_project": ArtifactRef(
                    id="hfss_project-hfss_project",
                    step_id="hfss_project",
                    label="hfss_project",
                    path=str(project_path),
                    kind="hfss",
                ),
            }
        )
        self.session.steps["hfss_update"].selected_artifact_ids = [
            "hfss_project-hfss_project",
            "parameter_update-parameter_update_py",
        ]

        self.runner.get_environment_report = MagicMock(
            return_value={
                "platform": "nt",
                "cst_path": "",
                "cst_path_ok": "no",
                "cst_path_message": "",
                "cst_interface_ok": "no",
                "cst_python_libraries_path": "",
                "cst_available": False,
                "cst_available_message": "",
                "hfss_path": "C:\\AnsysEM",
                "hfss_path_ok": "yes",
                "hfss_path_message": "",
                "pyaedt_ok": "yes",
                "hfss_available": True,
                "hfss_available_message": "",
                "unsafe_execution_enabled": True,
                "unsafe_execution_message": "",
                "available_backends": ["hfss"],
                "all_backends_unavailable": False,
            }
        )

        with patch("leam.backends.hfss.tools.hfss_runner.HfssRunner") as runner_cls:
            result = self.runner.run(definition, self.session)

        self.assertEqual(result.status, "success")
        runner_cls.assert_called_once_with(
            project_path=str(project_path),
            new_desktop=True,
            non_graphical=False,
            allow_unsafe_execution=True,
        )
        instance = runner_cls.return_value
        instance.set_parameter_tasks.assert_called_once()
        instance.apply_parameter_updates.assert_called_once()


if __name__ == "__main__":
    unittest.main()
