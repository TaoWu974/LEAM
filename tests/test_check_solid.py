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

from leam.backends.cst.tools.check_solid import CheckSolid


class CheckSolidTests(unittest.TestCase):
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

    def _write_json_file(self, directory: str, name: str, payload: object) -> str:
        path = Path(directory) / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_check_defaults_to_llm_only(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            solids_file = self._write_json_file(
                tempdir,
                "solids.json",
                {"solids": []},
            )
            parameters_file = self._write_json_file(
                tempdir,
                "parameters.json",
                {"items": []},
            )
            materials_file = self._write_json_file(
                tempdir,
                "materials.json",
                {"items": []},
            )
            checker = CheckSolid()
            checker._run_local_checks = MagicMock(
                return_value=[checker._issue("json", "local issue")]
            )
            checker._run_llm_alignment_check = MagicMock(return_value=[])

            result = checker.check(
                description="demo",
                solids_file=solids_file,
                parameters_file=parameters_file,
                materials_file=materials_file,
            )

            checker._run_local_checks.assert_not_called()
            checker._run_llm_alignment_check.assert_called_once()
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["issue_counts"]["total"], 0)

    def test_check_can_opt_in_to_local_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            solids_file = self._write_json_file(
                tempdir,
                "solids.json",
                {"solids": []},
            )
            parameters_file = self._write_json_file(
                tempdir,
                "parameters.json",
                {"items": []},
            )
            materials_file = self._write_json_file(
                tempdir,
                "materials.json",
                {"items": []},
            )
            checker = CheckSolid()
            checker._run_local_checks = MagicMock(
                return_value=[checker._issue("json", "local issue")]
            )
            checker._run_llm_alignment_check = MagicMock(return_value=[])

            result = checker.check(
                description="demo",
                solids_file=solids_file,
                parameters_file=parameters_file,
                materials_file=materials_file,
                use_local_checks=True,
            )

            checker._run_local_checks.assert_called_once()
            checker._run_llm_alignment_check.assert_called_once()
            self.assertEqual(result["status"], "issues")
            self.assertEqual(result["issue_counts"]["errors"], 1)

    def test_llm_alignment_check_preserves_route_target(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            solids_file = self._write_json_file(
                tempdir,
                "solids.json",
                {"solids": []},
            )
            parameters_file = self._write_json_file(
                tempdir,
                "parameters.json",
                {"items": []},
            )
            materials_file = self._write_json_file(
                tempdir,
                "materials.json",
                {"items": []},
            )
            checker = CheckSolid()
            checker.llm_caller.call_llm = MagicMock(
                return_value=(
                    '{"issues":[{"category":"alignment","severity":"error",'
                    '"solid":"patch","path":"solids[0].material",'
                    '"route_to":"materials","issue":"Material is wrong."}]}'
                )
            )

            issues = checker._run_llm_alignment_check(
                description="demo",
                image_paths=None,
                solids_file=solids_file,
                parameters_file=parameters_file,
                materials_file=materials_file,
            )

            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["route_to"], "materials")

    def test_hfss_local_checks_accept_builtin_materials_and_dollar_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            solids_file = self._write_json_file(
                tempdir,
                "solids.json",
                {
                    "solids": [
                        {
                            "Type": "3D",
                            "name": "patch",
                            "Role": "radiator",
                            "material": "pec",
                            "dimensions": {
                                "xrange": ["0", "$w1"],
                                "yrange": ["0", "0.5*$w1"],
                                "zrange": ["0", "tp"],
                            },
                            "operations": [],
                            "notes": "",
                        }
                    ]
                },
            )
            parameters_file = self._write_json_file(
                tempdir,
                "parameters.json",
                {
                    "representation": "parameters",
                    "items": [
                        {"name": "$w1", "value": "10mm", "notes": ""},
                        {"name": "tp", "value": "0.035mm", "notes": ""},
                    ],
                },
            )
            materials_file = self._write_json_file(
                tempdir,
                "materials.json",
                {
                    "representation": "materials",
                    "items": [
                        {
                            "name": "vacuum",
                            "source": "builtin",
                            "builtin": True,
                            "notes": "",
                        }
                    ],
                },
            )
            checker = CheckSolid(backend="hfss")

            issues = checker._run_local_checks(
                solids_file=solids_file,
                parameters_file=parameters_file,
                materials_file=materials_file,
            )

            self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
