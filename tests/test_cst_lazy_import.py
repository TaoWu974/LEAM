import builtins
import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


class CstLazyImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._clear_cst_modules()

    def tearDown(self) -> None:
        self._clear_cst_modules()

    @staticmethod
    def _clear_cst_modules() -> None:
        for module_name in (
            "leam.backends.cst",
            "leam.backends.cst.tools",
            "leam.backends.cst.tools.cst_runner",
        ):
            sys.modules.pop(module_name, None)

    def test_importing_cst_package_does_not_load_cst_runner(self) -> None:
        package = importlib.import_module("leam.backends.cst")

        self.assertTrue(hasattr(package, "ParameterGenerator"))
        self.assertNotIn("leam.backends.cst.tools.cst_runner", sys.modules)

    def test_importing_cst_runner_module_does_not_require_cst_until_use(self) -> None:
        original_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.startswith("cst"):
                raise ModuleNotFoundError(name)
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=guarded_import):
            module = importlib.import_module("leam.backends.cst.tools.cst_runner")

        self.assertTrue(hasattr(module, "CstRunner"))


if __name__ == "__main__":
    unittest.main()
