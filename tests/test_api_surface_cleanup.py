import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


class ApiSurfaceCleanupTests(unittest.TestCase):
    def test_legacy_main_module_removed(self) -> None:
        self.assertIsNone(importlib.util.find_spec("leam.main"))
        self.assertIsNone(importlib.util.find_spec("leam.cli"))
        self.assertIsNone(importlib.util.find_spec("leam.__main__"))

    def test_removed_config_functions_are_not_exposed(self) -> None:
        config = importlib.import_module("leam.config")
        self.assertFalse(hasattr(config, "save_config"))
        self.assertFalse(hasattr(config, "_ensure_pythonpath"))
        self.assertFalse(hasattr(config, "get_paths"))

    def test_removed_utils_exports_and_module(self) -> None:
        utils = importlib.import_module("leam.utils")
        self.assertFalse(hasattr(utils, "resolve_output_dir"))
        self.assertFalse(hasattr(utils, "prompt_path"))
        self.assertFalse(hasattr(utils, "resource_path"))

        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("leam.utils.paths")

    def test_hfss_runner_does_not_expose_cst_history_aliases(self) -> None:
        hfss_runner = importlib.import_module("leam.backends.hfss.tools.hfss_runner")
        self.assertFalse(hasattr(hfss_runner.HfssRunner, "set_history_tasks"))
        self.assertFalse(hasattr(hfss_runner.HfssRunner, "run_history_tasks"))

    def test_top_level_package_exports_are_reduced(self) -> None:
        package = importlib.import_module("leam")
        self.assertTrue(hasattr(package, "LLMCaller"))
        self.assertTrue(hasattr(package, "VBAGenerator"))
        self.assertFalse(hasattr(package, "PythonScriptGenerator"))


if __name__ == "__main__":
    unittest.main()
