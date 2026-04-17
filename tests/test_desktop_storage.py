import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from leam.desktop.storage.session_store import (
    DesktopSessionStore,
    RecentSessionStore,
)
from leam.desktop.workflow.engine import WorkflowEngine
from leam.desktop.workflow.models import ArtifactRef, IssueRefill


class DesktopStorageTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.output_root = Path(self.tempdir.name) / "workspaces"
        self.recents_path = Path(self.tempdir.name) / "desktop_recent_sessions.json"
        self.output_root_patcher = patch(
            "leam.desktop.storage.session_store.DEFAULT_OUTPUT_ROOT",
            self.output_root,
        )
        self.recents_patcher = patch(
            "leam.desktop.storage.session_store.DEFAULT_RECENTS_PATH",
            self.recents_path,
        )
        self.output_root_patcher.start()
        self.recents_patcher.start()
        self.store = DesktopSessionStore()
        self.engine = WorkflowEngine()
        self.session = self.engine.create_session(self.tempdir.name)

    def tearDown(self):
        self.output_root_patcher.stop()
        self.recents_patcher.stop()
        self.tempdir.cleanup()

    def test_save_and_load_session_round_trip(self):
        attachment = self.store.add_text_attachment(
            self.session,
            "input",
            "notes",
            "hello desktop",
        )
        self.session.steps["input"].attachments.append(attachment)
        self.session.steps["input"].description = "base description"
        payload = self.engine.serialise_session(self.session)
        path = self.store.save_session(
            self.session,
            payload,
            str(Path(self.tempdir.name) / "session.json"),
        )

        loaded = self.store.load_session(path)

        self.assertEqual(loaded.steps["input"].description, "base description")
        self.assertEqual(len(loaded.steps["input"].attachments), 1)
        self.assertEqual(
            loaded.steps["input"].attachments[0].kind,
            "text",
        )

    def test_save_session_serializes_workspace_paths_relatively(self):
        attachment = self.store.add_text_attachment(
            self.session,
            "input",
            "notes",
            "hello desktop",
        )
        artifact_path = (
            Path(self.tempdir.name)
            / "artifacts"
            / "parameters"
            / "run_001"
            / "parameters.json"
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("{}", encoding="utf-8")
        self.session.steps["input"].attachments.append(attachment)
        self.session.artifacts["parameters-parameters_json"] = ArtifactRef(
            id="parameters-parameters_json",
            step_id="parameters",
            label="parameters_json",
            path=str(artifact_path),
            kind="json",
        )
        self.session.steps["parameters"].artifact_ids = ["parameters-parameters_json"]
        self.session.steps["parameters"].settings["last_run_dir"] = str(
            artifact_path.parent
        )
        issue = IssueRefill(
            id="issue-1",
            source_step_id="check_solid",
            target_step_id="parameters",
            category="parameters",
            severity="error",
            message="Fix parameter mismatch.",
            issue_path=str(artifact_path),
        )
        self.session.issues.append(issue)
        self.session.steps["parameters"].issues = [issue]
        self.session.steps["parameters"].raw_issues = [
            {"path": str(artifact_path), "issue_path": str(artifact_path)}
        ]

        payload = self.engine.serialise_session(self.session)
        saved_path = self.store.save_session(
            self.session,
            payload,
            str(Path(self.tempdir.name) / "session.json"),
        )
        stored = json.loads(Path(saved_path).read_text(encoding="utf-8"))

        self.assertEqual(stored["workspace_dir"], ".")
        self.assertEqual(stored["session_file"], "session.json")
        self.assertEqual(
            stored["steps"]["input"]["attachments"][0]["path"],
            str(Path("attachments") / "input" / Path(attachment.path).name),
        )
        self.assertEqual(
            stored["artifacts"]["parameters-parameters_json"]["path"],
            str(Path("artifacts") / "parameters" / "run_001" / "parameters.json"),
        )
        self.assertEqual(
            stored["steps"]["parameters"]["settings"]["last_run_dir"],
            str(Path("artifacts") / "parameters" / "run_001"),
        )
        self.assertEqual(
            stored["issues"][0]["issue_path"],
            str(Path("artifacts") / "parameters" / "run_001" / "parameters.json"),
        )
        self.assertEqual(
            stored["steps"]["parameters"]["raw_issues"][0]["path"],
            str(Path("artifacts") / "parameters" / "run_001" / "parameters.json"),
        )

        loaded = self.store.load_session(saved_path)

        self.assertEqual(loaded.workspace_dir, self.tempdir.name)
        self.assertEqual(loaded.session_file, saved_path)
        self.assertEqual(loaded.steps["input"].attachments[0].path, attachment.path)
        self.assertEqual(
            loaded.artifacts["parameters-parameters_json"].path,
            str(artifact_path),
        )
        self.assertEqual(
            loaded.steps["parameters"].settings["last_run_dir"],
            str(artifact_path.parent),
        )

    def test_load_session_accepts_legacy_absolute_workspace_paths(self):
        workspace = Path(self.tempdir.name)
        attachment_path = workspace / "attachments" / "input" / "legacy.mtd"
        attachment_path.parent.mkdir(parents=True, exist_ok=True)
        attachment_path.write_text("legacy", encoding="utf-8")
        artifact_path = (
            workspace / "artifacts" / "parameters" / "run_001" / "parameters.json"
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("{}", encoding="utf-8")
        payload = asdict(self.session)
        payload["workspace_dir"] = str(workspace)
        payload["session_file"] = str(workspace / "session.json")
        payload["steps"]["input"]["attachments"] = [
            {
                "id": "attachment-input-legacy",
                "name": "legacy.mtd",
                "path": str(attachment_path),
                "kind": "file",
                "enabled": True,
                "editable": False,
                "origin": "user",
            }
        ]
        payload["artifacts"] = {
            "parameters-parameters_json": {
                "id": "parameters-parameters_json",
                "step_id": "parameters",
                "label": "parameters_json",
                "path": str(artifact_path),
                "kind": "json",
                "enabled": True,
                "created_at": None,
            }
        }
        payload["steps"]["parameters"]["artifact_ids"] = ["parameters-parameters_json"]
        payload["steps"]["parameters"]["settings"]["last_run_dir"] = str(
            artifact_path.parent
        )

        session_path = workspace / "session.json"
        session_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        loaded = self.store.load_session(str(session_path))

        self.assertEqual(loaded.workspace_dir, str(workspace))
        self.assertEqual(loaded.session_file, str(session_path))
        self.assertEqual(loaded.steps["input"].attachments[0].path, str(attachment_path))
        self.assertEqual(loaded.steps["input"].attachments[0].kind, "text")
        self.assertTrue(loaded.steps["input"].attachments[0].editable)
        self.assertEqual(
            loaded.artifacts["parameters-parameters_json"].path,
            str(artifact_path),
        )
        self.assertEqual(
            loaded.steps["parameters"].settings["last_run_dir"],
            str(artifact_path.parent),
        )

    def test_load_workspace_prefers_workspace_session_snapshot(self):
        self.session.title = "Saved Workspace"
        self.session.steps["input"].description = "persisted description"
        payload = self.engine.serialise_session(self.session)
        saved_path = self.store.save_session(
            self.session,
            payload,
            str(Path(self.tempdir.name) / "session.json"),
        )

        loaded = self.store.load_workspace(self.tempdir.name)

        self.assertEqual(loaded.title, "Saved Workspace")
        self.assertEqual(loaded.steps["input"].description, "persisted description")
        self.assertEqual(loaded.session_file, saved_path)

    def test_load_workspace_reconstructs_legacy_artifacts_and_attachments(self):
        workspace = Path(self.tempdir.name)
        (workspace / "artifacts" / "parameters" / "run_001_20260403_170619").mkdir(
            parents=True, exist_ok=True
        )
        (workspace / "artifacts" / "materials" / "run_001_20260403_170732").mkdir(
            parents=True, exist_ok=True
        )
        (workspace / "artifacts" / "solids" / "run_001_20260403_170803").mkdir(
            parents=True, exist_ok=True
        )
        (workspace / "artifacts" / "check_solid" / "run_001_20260403_171117").mkdir(
            parents=True, exist_ok=True
        )
        (workspace / "artifacts" / "dimensions" / "run_001_20260403_171207").mkdir(
            parents=True, exist_ok=True
        )
        (workspace / "artifacts" / "model_3d" / "run_001_20260403_171413").mkdir(
            parents=True, exist_ok=True
        )
        (workspace / "artifacts" / "model_2d" / "run_001_20260403_171511").mkdir(
            parents=True, exist_ok=True
        )
        (workspace / "attachments" / "input").mkdir(parents=True, exist_ok=True)
        (workspace / "attachments" / "parameter_update").mkdir(
            parents=True, exist_ok=True
        )

        (workspace / "artifacts" / "parameters" / "run_001_20260403_170619" / "parameters.py").write_text(
            'hfss["$w1"] = "1mm"\n',
            encoding="utf-8",
        )
        (workspace / "artifacts" / "parameters" / "run_001_20260403_170619" / "parameters.json").write_text(
            json.dumps({"representation": "parameters", "items": []}),
            encoding="utf-8",
        )
        (workspace / "artifacts" / "materials" / "run_001_20260403_170732" / "materials.json").write_text(
            json.dumps({"representation": "materials", "items": [{"name": "pec"}]}),
            encoding="utf-8",
        )
        (workspace / "artifacts" / "solids" / "run_001_20260403_170803" / "solids.json").write_text(
            json.dumps({"solids": [{"Type": "2.5D", "Name": "Slot"}]}),
            encoding="utf-8",
        )
        (workspace / "artifacts" / "check_solid" / "run_001_20260403_171117" / "solids_check.json").write_text(
            json.dumps(
                {
                    "status": "issues",
                    "issues": [
                        {
                            "category": "materials",
                            "severity": "error",
                            "route_to": "materials",
                            "issue": "Use the matched HFSS material name.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (workspace / "artifacts" / "dimensions" / "run_001_20260403_171207" / "dimensions.json").write_text(
            json.dumps({"items": []}),
            encoding="utf-8",
        )
        (workspace / "artifacts" / "model_3d" / "run_001_20260403_171413" / "model_3d.py").write_text(
            "hfss.modeler.create_box([0,0,0],[1,1,1])\n",
            encoding="utf-8",
        )
        (workspace / "artifacts" / "model_2d" / "run_001_20260403_171511" / "model_2d.py").write_text(
            "hfss.modeler.thicken_sheet('Sheet1', '1mm')\n",
            encoding="utf-8",
        )
        (workspace / "attachments" / "input" / "description.txt").write_text(
            "workspace description",
            encoding="utf-8",
        )
        (workspace / "attachments" / "parameter_update" / "description.txt").write_text(
            "adjust taper",
            encoding="utf-8",
        )

        loaded = self.store.load_workspace(self.tempdir.name)

        self.engine.refresh_session(loaded)

        self.assertEqual(loaded.title, Path(self.tempdir.name).name.replace("_", " "))
        self.assertEqual(loaded.workspace_dir, self.tempdir.name)
        self.assertEqual(
            loaded.session_file,
            str(Path(self.tempdir.name) / "session.json"),
        )
        self.assertEqual(loaded.steps["input"].description, "workspace description")
        self.assertEqual(
            loaded.steps["parameter_update"].description,
            "adjust taper",
        )
        self.assertEqual(loaded.steps["input"].settings["backend"], "hfss")
        self.assertTrue(loaded.steps["input"].settings["enable_execution"])
        self.assertTrue(loaded.steps["input"].settings["enable_25d"])
        self.assertTrue(loaded.steps["input"].settings["enable_parameter_update"])
        self.assertNotIn("execution_project_path", loaded.steps["input"].settings)
        self.assertNotIn(
            "overwrite_execution_project",
            loaded.steps["input"].settings,
        )
        self.assertTrue(loaded.flags["has_25d"])
        self.assertEqual(loaded.steps["check_solid"].status, "issues")
        self.assertEqual(len(loaded.steps["check_solid"].raw_issues), 1)
        self.assertIn("parameters-parameters_py", loaded.artifacts)
        self.assertIn("parameters-parameters_json", loaded.artifacts)
        self.assertIn("model_3d-model_3d_py", loaded.artifacts)
        self.assertIn("model_2d-model_2d_py", loaded.artifacts)

    def test_default_workspace_root_points_to_user_workspace_directory(self):
        root = self.store.default_workspace_root()

        self.assertEqual(Path(root), self.output_root)
        self.assertTrue(Path(root).exists())

    def test_workspace_name_uses_project_name_plus_timestamp(self):
        workspace = Path(self.store.create_workspace("demo_project"))

        self.assertEqual(workspace.parent, self.output_root)
        self.assertTrue(workspace.name.startswith("demo_project_cst_"))
        self.assertTrue((workspace / "artifacts").exists())
        self.assertTrue((workspace / "attachments").exists())

    def test_workspace_name_replaces_spaces_with_underscores(self):
        workspace = Path(self.store.create_workspace("demo project with spaces"))

        self.assertNotIn(" ", workspace.name)
        self.assertTrue(workspace.name.startswith("demo_project_with_spaces_cst_"))

    def test_workspace_name_can_include_hfss_backend_marker(self):
        workspace = Path(self.store.create_workspace("demo_project", backend="hfss"))

        self.assertTrue(workspace.name.startswith("demo_project_hfss_"))

    def test_workspace_can_use_custom_output_root(self):
        custom_root = Path(self.tempdir.name) / "custom_output"
        workspace = Path(
            self.store.create_workspace(
                "custom_project",
                output_root=str(custom_root),
            )
        )

        self.assertEqual(workspace.parent, custom_root)
        self.assertTrue(workspace.name.startswith("custom_project_cst_"))
        self.assertTrue((workspace / "artifacts").exists())
        self.assertTrue((workspace / "attachments").exists())

    def test_workspace_folder_can_be_renamed_to_match_backend(self):
        workspace = Path(self.store.create_workspace("backend_switch", output_root=self.tempdir.name))
        session = self.engine.create_session(str(workspace))
        session.title = "backend_switch"
        self.store.sync_description_attachment(session, "input", "hello")
        session.steps["input"].settings["backend"] = "hfss"
        payload = self.engine.serialise_session(session)
        self.store.save_session(session, payload)

        updated_workspace = Path(
            self.store.ensure_workspace_backend_name(session, "hfss")
        )

        self.assertTrue(updated_workspace.name.startswith("backend_switch_hfss_"))
        self.assertTrue(updated_workspace.exists())
        self.assertFalse(workspace.exists())
        self.assertEqual(Path(session.workspace_dir), updated_workspace)
        self.assertEqual(
            Path(session.steps["input"].attachments[0].path).parent.parent,
            updated_workspace / "attachments",
        )

    def test_attachment_import_and_text_creation_replace_spaces_with_underscores(self):
        source_file = Path(self.tempdir.name) / "my example figure .png"
        source_file.write_bytes(b"png")

        imported = self.store.import_attachment(
            self.session,
            "input",
            str(source_file),
        )
        created = self.store.add_text_attachment(
            self.session,
            "input",
            "notes for review",
            "hello",
        )

        self.assertNotIn(" ", Path(imported.path).name)
        self.assertIn("my_example_figure", Path(imported.path).name)
        self.assertNotIn(" ", Path(created.path).name)
        self.assertIn("notes_for_review", Path(created.path).name)

    def test_import_attachment_classifies_pdf_textlike_and_binary_files_safely(self):
        pdf_source = Path(self.tempdir.name) / "reference.pdf"
        pdf_source.write_bytes(b"%PDF-1.4\n")
        text_source = Path(self.tempdir.name) / "library.mtd"
        text_source.write_text("material library entry", encoding="utf-8")
        binary_source = Path(self.tempdir.name) / "model.aedt"
        binary_source.write_bytes(b"binary")

        imported_pdf = self.store.import_attachment(
            self.session,
            "input",
            str(pdf_source),
        )
        imported_text = self.store.import_attachment(
            self.session,
            "input",
            str(text_source),
        )
        imported_binary = self.store.import_attachment(
            self.session,
            "input",
            str(binary_source),
        )

        self.assertEqual(imported_pdf.kind, "pdf")
        self.assertFalse(imported_pdf.editable)
        self.assertEqual(imported_text.kind, "text")
        self.assertTrue(imported_text.editable)
        self.assertEqual(imported_binary.kind, "file")
        self.assertFalse(imported_binary.editable)

    def test_sync_description_attachment_creates_editable_text_file(self):
        attachment = self.store.sync_description_attachment(
            self.session,
            "input",
            "primary case description",
        )

        self.assertIsNotNone(attachment)
        self.assertEqual(attachment.origin, "description")
        self.assertTrue(attachment.editable)
        self.assertTrue(Path(attachment.path).exists())
        self.assertEqual(
            Path(attachment.path).read_text(encoding="utf-8"),
            "primary case description",
        )

    def test_recent_session_store_keeps_existing_files(self):
        recent_path = Path(self.tempdir.name) / "recents.json"
        workspace = Path(self.tempdir.name) / "workspace"
        workspace.mkdir()
        session_path = workspace / "session.json"
        session_path.write_text("{}", encoding="utf-8")
        recents = RecentSessionStore(str(recent_path))

        recents.add(str(workspace))

        self.assertEqual(recents.load(), [str(workspace.resolve())])

    def test_recent_session_store_filters_and_rewrites_invalid_entries(self):
        recent_path = Path(self.tempdir.name) / "recents.json"
        valid_workspace = Path(self.tempdir.name) / "valid_workspace"
        valid_workspace.mkdir()
        (valid_workspace / "session.json").write_text("{}", encoding="utf-8")
        invalid_workspace = Path(self.tempdir.name) / "invalid_workspace"
        invalid_workspace.mkdir()
        recent_path.write_text(
            json.dumps(
                [
                    str(valid_workspace),
                    str(invalid_workspace),
                    ".",
                    str(valid_workspace / "session.json"),
                ]
            ),
            encoding="utf-8",
        )
        recents = RecentSessionStore(str(recent_path))

        loaded = recents.load()

        self.assertEqual(loaded, [str(valid_workspace.resolve())])
        self.assertEqual(
            json.loads(recent_path.read_text(encoding="utf-8")),
            [str(valid_workspace.resolve())],
        )

    def test_recent_session_store_remove_deletes_matching_workspace_entry(self):
        recent_path = Path(self.tempdir.name) / "recents.json"
        workspace = Path(self.tempdir.name) / "workspace"
        workspace.mkdir()
        session_path = workspace / "session.json"
        session_path.write_text("{}", encoding="utf-8")
        recents = RecentSessionStore(str(recent_path))
        recents.add(str(workspace))

        loaded = recents.remove(str(session_path))

        self.assertEqual(loaded, [])
        self.assertEqual(json.loads(recent_path.read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
