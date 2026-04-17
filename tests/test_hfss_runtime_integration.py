import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from leam.backends.hfss.tools.hfss_runner import HfssRunner
from leam.config import resolve_hfss_path, validate_hfss_path


@unittest.skipUnless(
    os.environ.get("LEAM_RUN_HFSS_INTEGRATION") == "1",
    "Set LEAM_RUN_HFSS_INTEGRATION=1 to run the real HFSS smoke test.",
)
class HfssRuntimeIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            import ansys.aedt.core  # noqa: F401
        except Exception as exc:
            self.skipTest(f"PyAEDT import failed: {exc}")

        hfss_path = resolve_hfss_path({})
        is_valid, message = validate_hfss_path(hfss_path)
        if not is_valid:
            self.skipTest(message)

        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        if hasattr(self, "tempdir"):
            self.tempdir.cleanup()

    def _write_script(self, name: str, content: str) -> str:
        path = Path(self.tempdir.name) / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_runner_builds_minimal_real_project(self) -> None:
        project_path = Path(self.tempdir.name) / "hfss_smoke.aedt"
        parameters = self._write_script(
            "parameters.py",
            'hfss["$box_w"] = "1mm"\n',
        )
        model_3d = self._write_script(
            "model_3d.py",
            'hfss.modeler.create_box(\n'
            '    origin=["0mm", "0mm", "0mm"],\n'
            '    sizes=["$box_w", "1mm", "1mm"],\n'
            '    name="SmokeBox",\n'
            '    material="vacuum",\n'
            ')\n',
        )

        runner = HfssRunner(
            project_path=str(project_path),
            design_name="LEAMSmoke",
            non_graphical=True,
            new_desktop=True,
            allow_unsafe_execution=True,
        )
        try:
            runner.set_build_tasks(
                {
                    "Parameters": parameters,
                    "3D Model": model_3d,
                }
            )
            created = runner.create_project(
                save_path=str(project_path),
                close_project_after_save=False,
            )

            self.assertTrue(Path(created).is_file())
        finally:
            runner.close_project()


if __name__ == "__main__":
    unittest.main()
