import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from leam.desktop.examples import (
    EXAMPLE_PRESETS,
    apply_example_preset,
    available_example_presets,
)
from leam.desktop.storage.session_store import DesktopSessionStore
from leam.desktop.workflow.engine import WorkflowEngine


class DesktopExamplesTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = DesktopSessionStore()
        self.engine = WorkflowEngine()
        self.session = self.engine.create_session(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_vivaldi_example_enables_update_and_25d(self):
        preset = apply_example_preset(
            self.session,
            self.engine,
            self.store,
            "vivaldi",
        )

        self.assertEqual(preset.title, "Vivaldi Antenna")
        self.assertEqual(self.session.template, "strong_description")
        self.assertEqual(preset.backend, "cst")
        self.assertTrue(preset.enable_execution)
        self.assertEqual(self.session.steps["input"].settings["backend"], "cst")
        self.assertTrue(self.session.steps["input"].settings["enable_execution"])
        self.assertTrue(self.session.flags["has_25d"])
        self.assertTrue(self.session.steps["input"].settings["enable_25d"])
        self.assertTrue(
            self.session.steps["input"].settings["enable_parameter_update"]
        )
        self.assertIn("parameter_update", self.session.steps)
        self.assertIn("model_2d", self.session.steps)
        self.assertIn(
            "change spline definition's X_1",
            self.session.steps["parameter_update"].description,
        )

    def test_monopole_example_imports_images_and_step_text(self):
        preset = apply_example_preset(
            self.session,
            self.engine,
            self.store,
            "monopole",
        )

        self.assertEqual(preset.title, "Slotted Monopole")
        self.assertEqual(self.session.template, "paper_reconstruction")
        self.assertEqual(self.session.steps["input"].settings["backend"], "cst")
        self.assertTrue(self.session.steps["input"].settings["enable_execution"])
        self.assertEqual(len(self.session.steps["input"].attachments), 1)
        self.assertEqual(len(self.session.steps["parameters"].attachments), 1)
        self.assertEqual(
            self.session.steps["input"].attachments[0].kind,
            "image",
        )
        self.assertIn(
            "There are two errors",
            self.session.steps["parameters"].description,
        )
        self.assertIn(
            "We need add the feed to the patch",
            self.session.steps["boolean"].description,
        )

    def test_all_examples_are_registered(self):
        self.assertEqual(
            set(EXAMPLE_PRESETS),
            {"vivaldi", "slotted_patch", "monopole"},
        )

    def test_available_examples_skip_presets_with_missing_repo_assets(self):
        missing_asset = Path(self.tempdir.name) / "missing.png"
        patched_presets = dict(EXAMPLE_PRESETS)
        patched_presets["monopole"] = replace(
            EXAMPLE_PRESETS["monopole"],
            input_attachments=[missing_asset],
            step_attachments={},
        )

        with patch("leam.desktop.examples.EXAMPLE_PRESETS", patched_presets):
            available = available_example_presets()

        self.assertEqual(set(available), {"vivaldi", "slotted_patch"})

    def test_apply_example_preset_rejects_missing_repo_assets(self):
        missing_asset = Path(self.tempdir.name) / "missing.png"
        patched_presets = dict(EXAMPLE_PRESETS)
        patched_presets["monopole"] = replace(
            EXAMPLE_PRESETS["monopole"],
            input_attachments=[missing_asset],
            step_attachments={},
        )

        with patch("leam.desktop.examples.EXAMPLE_PRESETS", patched_presets):
            with self.assertRaises(ValueError):
                apply_example_preset(
                    self.session,
                    self.engine,
                    self.store,
                    "monopole",
                )


if __name__ == "__main__":
    unittest.main()
