import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
except ModuleNotFoundError:  # pragma: no cover - optional desktop dependency
    QApplication = None
    QMessageBox = None
    Qt = None
    QPushButton = None

from leam.desktop.storage.session_store import DesktopSessionStore, RecentSessionStore
from leam.desktop.workflow.engine import WorkflowEngine
from leam.desktop.workflow.models import ArtifactRef

if QApplication is not None:
    from leam.desktop.app.main_window import MainWindow, ProjectEntryDialog


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class DesktopMainWindowTests(unittest.TestCase):
    @staticmethod
    def _make_environment_report(
        *,
        cst: bool = True,
        hfss: bool = True,
        unsafe_execution: bool = True,
    ):
        available_backends = []
        if cst:
            available_backends.append("cst")
        if hfss:
            available_backends.append("hfss")
        return {
            "platform": "nt",
            "cst_path": "C:\\CST" if cst else "",
            "cst_path_ok": "yes" if cst else "no",
            "cst_path_message": "" if cst else "CST path not configured.",
            "cst_interface_ok": "yes" if cst else "no",
            "cst_python_libraries_path": (
                "C:\\CST\\AMD64\\python_cst_libraries" if cst else ""
            ),
            "cst_available": cst,
            "cst_available_message": (
                "" if cst else "CST path not configured."
            ),
            "hfss_path": "C:\\AnsysEM" if hfss else "",
            "hfss_path_ok": "yes" if hfss else "no",
            "hfss_path_message": "" if hfss else "HFSS path not configured.",
            "pyaedt_ok": "yes" if hfss else "no",
            "hfss_available": hfss,
            "hfss_available_message": (
                "" if hfss else "HFSS path not configured."
            ),
            "unsafe_execution_enabled": unsafe_execution,
            "unsafe_execution_message": (
                ""
                if unsafe_execution
                else "Generated HFSS/CST execution is disabled."
            ),
            "available_backends": available_backends,
            "all_backends_unavailable": not available_backends,
        }

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.workspace_path = Path(self.tempdir.name) / "demo_workspace"
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        self.store = DesktopSessionStore()
        self.engine = WorkflowEngine()
        self.session = self.engine.create_session(str(self.workspace_path))
        self.session.title = "Demo Workspace"
        payload = self.engine.serialise_session(self.session)
        self.store.save_session(
            self.session,
            payload,
            str(self.workspace_path / "session.json"),
        )
        self.recents_path = Path(self.tempdir.name) / "recents.json"
        self.environment_report = self._make_environment_report()
        self.warning_patcher = patch(
            "leam.desktop.app.main_window.QMessageBox.warning"
        )
        self.environment_patcher = patch(
            "leam.desktop.services.runner.DesktopWorkflowRunner.get_environment_report",
            return_value=self.environment_report,
        )
        self.warning_mock = self.warning_patcher.start()
        self.environment_patcher.start()

        self.window = MainWindow()
        self.window.recent_store = RecentSessionStore(str(self.recents_path))
        self.window._rebuild_recent_menu()
        self.window._refresh_launchpad()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.environment_patcher.stop()
        self.warning_patcher.stop()
        self.tempdir.cleanup()

    def test_window_starts_on_launchpad_without_session(self):
        self.assertIs(self.window.main_stack.currentWidget(), self.window.launchpad_page)
        self.assertTrue(self.window.command_bar.isHidden())
        self.assertTrue(self.window.run_button.isHidden())
        self.assertEqual(self.window.run_button.text(), "Create Workspace First")
        self.assertEqual(self.window.action_step_label.text(), "Workspace Required")

    def test_launchpad_recent_list_renders_saved_workspaces(self):
        self.window.recent_store.add(str(self.workspace_path))
        self.window._rebuild_recent_menu()
        self.app.processEvents()

        self.assertEqual(self.window.launch_recent_list.count(), 1)
        item = self.window.launch_recent_list.item(0)
        self.assertEqual(item.data(Qt.UserRole), str(self.workspace_path.resolve()))
        self.assertTrue(self.window.launch_recent_button.isEnabled())
        self.assertTrue(self.window.launch_recent_remove_button.isEnabled())

    def test_launchpad_remove_selected_recent_workspace_updates_store(self):
        self.window.recent_store.add(str(self.workspace_path))
        self.window._rebuild_recent_menu()
        self.app.processEvents()

        self.window._remove_selected_recent_workspace()
        self.app.processEvents()

        self.assertEqual(self.window.launch_recent_list.count(), 1)
        item = self.window.launch_recent_list.item(0)
        self.assertIn("No recent workspaces yet.", item.text())
        self.assertFalse(self.window.launch_recent_button.isEnabled())
        self.assertFalse(self.window.launch_recent_remove_button.isEnabled())
        self.assertEqual(self.window.recent_store.load(), [])

    def test_open_recent_removes_missing_workspace_from_recents(self):
        missing_workspace = Path(self.tempdir.name) / "missing_workspace"
        valid_workspace = Path(self.tempdir.name) / "valid_workspace"
        valid_workspace.mkdir()
        self.store.save_session(
            self.session,
            self.engine.serialise_session(self.session),
            str(valid_workspace / "session.json"),
        )
        self.window.recent_store.add(str(valid_workspace))
        recents = json.loads(self.recents_path.read_text(encoding="utf-8"))
        recents.insert(0, str(missing_workspace))
        self.recents_path.write_text(json.dumps(recents), encoding="utf-8")
        self.window._rebuild_recent_menu()
        self.app.processEvents()

        self.window._open_recent(str(missing_workspace))
        self.app.processEvents()

        self.warning_mock.assert_called()
        self.assertEqual(self.window.recent_store.load(), [str(valid_workspace.resolve())])
        self.assertEqual(self.window.launch_recent_list.count(), 1)
        item = self.window.launch_recent_list.item(0)
        self.assertEqual(item.data(Qt.UserRole), str(valid_workspace.resolve()))

    def test_loading_workspace_switches_to_workspace_console(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.app.processEvents()

        self.assertIs(self.window.main_stack.currentWidget(), self.window.workspace_page)
        self.assertFalse(self.window.command_bar.isHidden())
        self.assertEqual(self.window.left_pane_widget.minimumWidth(), 210)
        self.assertEqual(self.window.middle_pane_widget.minimumWidth(), 560)
        self.assertEqual(self.window.right_pane_widget.minimumWidth(), 320)
        self.assertGreater(
            self.window.middle_pane_widget.minimumWidth(),
            self.window.left_pane_widget.minimumWidth(),
        )
        self.assertGreater(
            self.window.middle_pane_widget.minimumWidth(),
            self.window.right_pane_widget.minimumWidth(),
        )
        self.assertIs(self.window.workflow_config_group.parentWidget(), self.window.session_title_label.parentWidget())
        self.assertEqual(self.window.run_button.text(), "Run This Step")
        self.assertEqual(self.window.action_step_label.text(), "Parameters")
        self.assertEqual(self.window.session_title_label.text(), "Demo Workspace")
        self.assertNotIn("input", self.window._step_item_widgets)
        self.assertIn(
            "Waiting for upstream outputs.",
            self.window._step_item_widgets["parameters"].meta_label.text(),
        )
        self.assertTrue(self.window.workflow_apply_button.isEnabled())
        self.assertFalse(self.window._step_item_widgets["parameters"].action_button.isHidden())
        button_texts = [
            button.text()
            for button in self.window.command_bar.findChildren(QPushButton)
        ]
        self.assertNotIn("Save Snapshot", button_texts)
        self.assertNotIn("Export JSON", button_texts)
        prompt_layout = self.window.prompt_scroll.widget().layout()
        self.assertLess(
            prompt_layout.indexOf(self.window.description_group),
            prompt_layout.indexOf(self.window.attachments_group),
        )
        self.assertLess(
            prompt_layout.indexOf(self.window.attachments_group),
            prompt_layout.indexOf(self.window.artifacts_group),
        )
        self.assertEqual(self.window.attachments_group.title(), "Attachments and Preview")

    def test_running_state_prevents_step_switching(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.app.processEvents()

        original_step_id = self.window.current_step_id
        target_step_id = "materials" if original_step_id != "materials" else "solids"
        target_item = self.window._step_items[target_step_id]

        self.window._set_running_state(True, "Parameters")
        self.app.processEvents()

        self.window._select_step(target_step_id)
        self.app.processEvents()
        self.assertEqual(self.window.current_step_id, original_step_id)
        self.assertEqual(
            self.window.step_list.currentItem().data(Qt.UserRole),
            original_step_id,
        )

        self.window.step_list.setCurrentItem(target_item)
        self.app.processEvents()
        self.assertEqual(self.window.current_step_id, original_step_id)
        self.assertEqual(
            self.window.step_list.currentItem().data(Qt.UserRole),
            original_step_id,
        )

        self.window._set_running_state(False)
        self.assertEqual(self.window.artifacts_group.title(), "Select Artifacts and Preview")
        self.assertFalse(hasattr(self.window, "prompt_overview_view"))

    def test_chrome_create_button_returns_to_launchpad(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.app.processEvents()

        self.window.chrome_create_button.click()
        self.app.processEvents()

        self.assertIsNone(self.window.session)
        self.assertIs(
            self.window.main_stack.currentWidget(),
            self.window.launchpad_page,
        )
        self.assertTrue(self.window.command_bar.isHidden())
        self.assertGreaterEqual(self.window.launch_recent_list.count(), 1)
        first_item = self.window.launch_recent_list.item(0)
        self.assertEqual(first_item.data(Qt.UserRole), str(self.workspace_path.resolve()))

    def test_project_entry_dialog_enables_backend_selector_when_multiple_backends_exist(self):
        dialog = ProjectEntryDialog(
            output_root=self.tempdir.name,
            default_name="demo",
            default_backend="cst",
            available_backends=["cst", "hfss"],
        )
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.backend_combo.count(), 2)
        self.assertTrue(dialog.backend_combo.isEnabled())

    def test_project_entry_dialog_disables_backend_selector_when_single_backend_exists(self):
        dialog = ProjectEntryDialog(
            output_root=self.tempdir.name,
            default_name="demo",
            default_backend="hfss",
            available_backends=["hfss"],
        )
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.backend_combo.count(), 1)
        self.assertFalse(dialog.backend_combo.isEnabled())
        self.assertEqual(dialog.backend(), "hfss")

    def test_project_entry_dialog_preview_tracks_selected_backend(self):
        dialog = ProjectEntryDialog(
            output_root=self.tempdir.name,
            default_name="demo",
            default_backend="cst",
            available_backends=["cst", "hfss"],
        )
        self.addCleanup(dialog.close)

        dialog.backend_combo.setCurrentIndex(dialog.backend_combo.findData("hfss"))
        self.app.processEvents()

        self.assertIn("_hfss_", dialog.preview_label.text())

    def test_launchpad_blocks_all_entry_when_no_backends_are_available(self):
        self.window._environment_report = MagicMock(
            return_value=self._make_environment_report(cst=False, hfss=False)
        )

        self.window._refresh_launchpad()
        self.app.processEvents()

        self.assertIs(self.window.main_stack.currentWidget(), self.window.launchpad_page)
        self.assertFalse(self.window.launch_new_button.isEnabled())
        self.assertFalse(self.window.launch_open_button.isEnabled())
        self.assertTrue(all(not button.isEnabled() for button in self.window._launch_example_buttons))
        self.warning_mock.assert_called()
        self.assertIn(
            "needs at least one local CST or HFSS installation",
            self.window.launchpad_subtitle_label.text(),
        )
        warning_text = self.warning_mock.call_args[0][2]
        self.assertIn("needs at least one local CST or HFSS installation", warning_text)
        self.assertIn("CST:", warning_text)
        self.assertIn("HFSS:", warning_text)

    def test_unavailable_workspace_backend_stays_selected_and_warns(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.window._environment_report = MagicMock(
            return_value=self._make_environment_report(cst=False, hfss=True)
        )

        self.window._refresh_workflow_config()
        self.window._refresh_workflow_warning()
        self.app.processEvents()

        self.assertEqual(self.window.session.steps["input"].settings["backend"], "cst")
        self.assertEqual(self.window.backend_combo.currentData(), "cst")
        self.assertIn("CST:", self.window.workflow_warning_label.text())

    def test_execution_warning_appears_when_workspace_execution_is_enabled_but_not_opted_in(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.window.session.steps["input"].settings["enable_execution"] = True
        self.window.engine.refresh_session(self.window.session)
        self.window._environment_report = MagicMock(
            return_value=self._make_environment_report(unsafe_execution=False)
        )

        self.window._refresh_workflow_warning()
        self.app.processEvents()

        self.assertIn(
            "Generated HFSS/CST execution is disabled.",
            self.window.workflow_warning_label.text(),
        )

    def test_workflow_config_backend_choices_follow_runtime_availability(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.window.session.steps["input"].settings["backend"] = "hfss"
        self.window.engine.refresh_session(self.window.session)
        self.window._environment_report = MagicMock(
            return_value=self._make_environment_report(cst=False, hfss=True)
        )

        self.window._refresh_workflow_config()
        self.app.processEvents()

        model = self.window.backend_combo.model()
        cst_item = model.item(self.window.backend_combo.findData("cst"))
        hfss_item = model.item(self.window.backend_combo.findData("hfss"))
        self.assertFalse(cst_item.isEnabled())
        self.assertTrue(hfss_item.isEnabled())
        self.assertEqual(self.window.backend_combo.currentData(), "hfss")

    def test_workflow_config_locks_into_summary_after_setup(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.window.engine.run_step(self.window.session, "input")
        self.window._refresh_all()
        self.app.processEvents()

        self.assertIs(
            self.window.workflow_config_stack.currentWidget(),
            self.window.workflow_config_locked_page,
        )
        self.assertFalse(self.window.workflow_template_combo.isEnabled())
        self.assertEqual(self.window.current_step_id, "parameters")
        self.assertEqual(self.window.run_button.text(), "Run This Step")
        self.assertTrue(self.window.run_button.isEnabled())
        self.assertEqual(self.window.action_state_badge.text(), "READY")
        self.assertFalse(self.window.workflow_apply_button.isEnabled())
        self.assertFalse(self.window._step_item_widgets["parameters"].action_button.isHidden())

    def test_workspace_setup_renames_workspace_folder_to_backend(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.window.session.title = "Demo Workspace"
        self.window.session.steps["input"].settings["backend"] = "hfss"
        original_workspace = Path(self.window.session.workspace_dir)

        self.window._running_step_id = "input"
        result = self.window.engine.run_step(self.window.session, "input")
        self.window._on_step_run_success(result)
        self.app.processEvents()

        renamed_workspace = Path(self.window.session.workspace_dir)
        self.assertNotEqual(renamed_workspace, original_workspace)
        self.assertTrue(renamed_workspace.name.startswith("Demo_Workspace_hfss_"))
        self.assertTrue(renamed_workspace.exists())
        self.assertFalse(original_workspace.exists())

    def test_execution_checkbox_defaults_to_enabled(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.app.processEvents()

        self.assertTrue(self.window.enable_execution_checkbox.isChecked())
        self.assertTrue(
            self.window.session.steps["input"].settings["enable_execution"]
        )

    def test_enabling_execution_requires_confirmation(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.window.session.steps["input"].settings["enable_execution"] = False
        self.window.engine.refresh_session(self.window.session)
        self.window._refresh_all()
        self.app.processEvents()
        self.warning_mock.reset_mock()
        self.warning_mock.return_value = QMessageBox.Yes

        self.window.enable_execution_checkbox.setChecked(True)
        self.app.processEvents()

        self.assertTrue(self.window.enable_execution_checkbox.isChecked())
        self.assertTrue(
            self.window.session.steps["input"].settings["enable_execution"]
        )
        self.assertTrue(
            self.window.session.steps["input"].settings[
                "execution_warning_acknowledged"
            ]
        )
        self.warning_mock.assert_called()

    def test_cancelling_execution_confirmation_reverts_checkbox(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.window.session.steps["input"].settings["enable_execution"] = False
        self.window.engine.refresh_session(self.window.session)
        self.window._refresh_all()
        self.app.processEvents()
        self.warning_mock.reset_mock()
        self.warning_mock.return_value = QMessageBox.Cancel

        self.window.enable_execution_checkbox.setChecked(True)
        self.app.processEvents()

        self.assertFalse(self.window.enable_execution_checkbox.isChecked())
        self.assertFalse(
            self.window.session.steps["input"].settings["enable_execution"]
        )

    def test_execution_confirmation_is_only_shown_once_per_workspace(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.window.session.steps["input"].settings["enable_execution"] = False
        self.window.engine.refresh_session(self.window.session)
        self.window._refresh_all()
        self.app.processEvents()
        self.warning_mock.reset_mock()
        self.warning_mock.return_value = QMessageBox.Yes

        self.window.enable_execution_checkbox.setChecked(True)
        self.app.processEvents()
        self.window.enable_execution_checkbox.setChecked(False)
        self.app.processEvents()
        self.warning_mock.reset_mock()

        self.window.enable_execution_checkbox.setChecked(True)
        self.app.processEvents()

        self.warning_mock.assert_not_called()

    def test_refill_notes_render_inline_under_description(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.window.session.steps["parameters"].refill_notes = "Auto feedback from check_solid."
        self.window.current_step_id = "parameters"
        self.window._refresh_all()
        self.app.processEvents()

        self.assertFalse(self.window.description_append_label.isHidden())
        self.assertFalse(self.window.description_append_preview.isHidden())
        self.assertEqual(
            self.window.description_append_preview.toPlainText(),
            "Auto feedback from check_solid.",
        )

    def test_results_tabs_replace_resources_tab(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.window.engine.run_step(self.window.session, "input")
        self.window._refresh_all()
        self.app.processEvents()

        tab_labels = [
            self.window.tabs.tabText(index) for index in range(self.window.tabs.count())
        ]
        self.assertEqual(tab_labels, ["Structure", "Outputs", "Review"])
        self.assertEqual(self.window.tabs.count(), 3)

    def test_prompt_cards_track_live_inputs(self):
        self.window._load_workspace_path(str(self.workspace_path))
        self.window.engine.run_step(self.window.session, "input")

        self.window.session.steps["input"].description = "Base workspace brief."
        dimensions_state = self.window.session.steps["dimensions"]
        dimensions_state.description = "Derive exact dimensions."
        dimensions_state.refill_notes = "Carry over the validation deltas."
        attachment = self.store.add_text_attachment(
            self.window.session,
            "dimensions",
            "notes",
            "Attachment body",
        )
        dimensions_state.attachments.append(attachment)

        artifact_path = self.workspace_path / "artifacts" / "solids.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text('{"solids": []}', encoding="utf-8")
        artifact = ArtifactRef(
            id="artifact-solids-json",
            step_id="solids",
            label="solids_json",
            path=str(artifact_path),
            kind="json",
        )
        self.window.session.artifacts[artifact.id] = artifact
        self.window.session.steps["solids"].artifact_ids = [artifact.id]
        dimensions_state.selected_artifact_ids = [artifact.id]
        dimensions_state.settings["artifact_selection_touched"] = True

        self.window.current_step_id = "dimensions"
        self.window._refresh_all()
        self.app.processEvents()

        attachment_labels = [
            self.window.attachments_list.item(index).text()
            for index in range(self.window.attachments_list.count())
        ]
        self.assertTrue(any(attachment.name in label for label in attachment_labels))
        self.assertFalse(any(str(attachment.path) in label for label in attachment_labels))
        self.window.attachments_list.setCurrentRow(self.window.attachments_list.count() - 1)
        self.app.processEvents()
        self.assertIn("Attachment body", self.window.attachment_editor.toPlainText())
        self.assertEqual(self.window.artifact_selection_list.count(), 1)
        artifact_label = self.window.artifact_selection_list.item(0).text()
        self.assertIn(Path(artifact_path).name, artifact_label)
        self.assertNotIn(str(artifact_path), artifact_label)
        self.assertIn('{"solids": []}', self.window.artifact_selection_preview.toPlainText())
        self.assertFalse(hasattr(self.window, "prompt_overview_view"))


if __name__ == "__main__":
    unittest.main()
