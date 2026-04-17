import sys
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


class PackagingMetadataTests(unittest.TestCase):
    @staticmethod
    def _load_pyproject() -> dict:
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as source:
            return tomllib.load(source)

    def test_base_dependencies_include_desktop_runtime_stack(self) -> None:
        payload = self._load_pyproject()
        dependencies = payload["project"]["dependencies"]

        self.assertTrue(any(item.startswith("openai") for item in dependencies))
        self.assertTrue(any(item.startswith("PySide6") for item in dependencies))
        self.assertTrue(any(item.startswith("pyaedt") for item in dependencies))
        self.assertTrue(any(item.startswith("pandas") for item in dependencies))

    def test_only_dev_extra_remains(self) -> None:
        payload = self._load_pyproject()
        optional_dependencies = payload["project"]["optional-dependencies"]

        self.assertEqual(set(optional_dependencies), {"dev"})


if __name__ == "__main__":
    unittest.main()
