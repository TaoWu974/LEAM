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

from leam.backends.hfss.tools.parameter_generator import ParameterGenerator


class HfssParameterGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ensure_key_patcher = patch(
            "leam.core.llm_caller.ensure_openai_api_key",
            return_value="test-key",
        )
        self.openai_patcher = patch("leam.core.llm_caller.openai.OpenAI")
        self.ensure_key_patcher.start()
        self.mock_openai_cls = self.openai_patcher.start()
        self.mock_openai_cls.return_value = MagicMock()
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tempdir.cleanup()
        self.openai_patcher.stop()
        self.ensure_key_patcher.stop()

    def test_generate_parameters_writes_script_and_companion_json(self) -> None:
        generator = ParameterGenerator(save_dir=self.tempdir.name)
        script_path = Path(self.tempdir.name) / "parameters.py"
        extra_prompt = Path(self.tempdir.name) / "extra.md"
        extra_prompt.write_text("extra context", encoding="utf-8")

        def _fake_generate_script(**kwargs):
            script_path.write_text(
                'hfss["$w1"] = "1.39mm"\n'
                'hfss["$eps_sub"] = "4.3" # substrate\n',
                encoding="utf-8",
            )
            return script_path.read_text(encoding="utf-8")

        generator.script_generator.generate_script = _fake_generate_script

        code = generator.generate_parameters(
            description="demo",
            output_file="parameters.py",
            json_file="parameters.json",
            additional_prompt_files=[str(extra_prompt)],
        )

        self.assertIn('hfss["$w1"] = "1.39mm"', code)
        payload = json.loads(
            (Path(self.tempdir.name) / "parameters.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["representation"], "parameters")
        self.assertEqual(
            payload["items"],
            [
                {"name": "$w1", "value": "1.39mm", "notes": ""},
                {"name": "$eps_sub", "value": "4.3", "notes": "substrate"},
            ],
        )

    def test_extract_parameters_accepts_common_pyaedt_output_variants(self) -> None:
        payload = ParameterGenerator.extract_parameters_from_script(
            "aedtapp['$w1'] = '1.39mm'\n"
            "app.variable_manager.set_variable('$eps_sub', expression='4.3')\n"
            'hfss.variable_manager.set_variable("$slot_len", "0.5*$w1") # slot\n'
        )

        self.assertEqual(
            payload["items"],
            [
                {"name": "$w1", "value": "1.39mm", "notes": ""},
                {"name": "$eps_sub", "value": "4.3", "notes": ""},
                {"name": "$slot_len", "value": "0.5*$w1", "notes": "slot"},
            ],
        )

    def test_generate_parameters_uses_medium_reasoning_effort(self) -> None:
        generator = ParameterGenerator(save_dir=self.tempdir.name)
        generator.script_generator.generate_script = MagicMock(
            return_value='hfss["$w1"] = "1mm"\n'
        )

        generator.generate_parameters(description="demo")

        kwargs = generator.script_generator.generate_script.call_args.kwargs
        self.assertEqual(kwargs["reasoning_effort"], "medium")


if __name__ == "__main__":
    unittest.main()
