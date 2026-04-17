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

from leam.backends.hfss.paths import prompt_path
from leam.backends.hfss.tools import CheckSolid


class HfssCheckSolidTests(unittest.TestCase):
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

    def test_tools_package_exports_check_solid(self) -> None:
        checker = CheckSolid()
        self.assertIsInstance(checker, CheckSolid)

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

    def test_local_checks_accept_builtin_materials_and_dollar_parameters(self) -> None:
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
            checker = CheckSolid()

            issues = checker._run_local_checks(
                solids_file=solids_file,
                parameters_file=parameters_file,
                materials_file=materials_file,
            )

            self.assertEqual(issues, [])

    def test_check_solid_prompt_accepts_hfss_dollar_parameter_equivalence(self) -> None:
        prompt = Path(prompt_path("check_solid_prompt.md")).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "treat `name` and `$name` as equivalent identifiers",
            prompt,
        )
        self.assertIn(
            "Do not report a mismatch solely because `parameters.json` uses `$W_sub` while `solids.json` uses `W_sub`",
            prompt,
        )
        self.assertIn(
            "Do not report annotated dimension strings such as `(W_sub - W_patch)/2 = 6.35mm`",
            prompt,
        )

    def test_local_checks_report_material_parameter_and_operation_errors(self) -> None:
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
                            "material": "RogersMissing",
                            "dimensions": {
                                "xrange": ["0", "$w1"],
                                "yrange": ["0", "0.5*$undefined_len"],
                                "zrange": ["0", "tp"],
                            },
                            "operations": ["subtract: slot_cutout"],
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
                    "items": [],
                },
            )
            checker = CheckSolid()

            issues = checker._run_local_checks(
                solids_file=solids_file,
                parameters_file=parameters_file,
                materials_file=materials_file,
            )

            categories = {issue["category"] for issue in issues}
            messages = "\n".join(issue["issue"] for issue in issues)
            self.assertIn("materials", categories)
            self.assertIn("parameters", categories)
            self.assertIn("operations", categories)
            self.assertIn("RogersMissing", messages)
            self.assertIn("undefined_len", messages)
            self.assertIn("slot_cutout", messages)


if __name__ == "__main__":
    unittest.main()
