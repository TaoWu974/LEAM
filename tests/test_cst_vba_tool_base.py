import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from leam.backends.cst.tools.boolean_ops import BooleanOperationsGenerator
from leam.backends.cst.tools.model_2d_generator import Model2DGenerator
from leam.backends.cst.tools.parameter_generator import ParameterGenerator
from leam.core.errors import InputValidationError
from leam.core.script_generator import ScriptGenerator
from leam.core.vba_generator import VBAGenerator


class CstVbaToolBaseTests(unittest.TestCase):
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

    def _mktemp_file(self, suffix: str, content: str = "") -> str:
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        )
        handle.write(content)
        handle.flush()
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def test_parameter_generator_uses_output_path_and_prompt_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ParameterGenerator(save_dir=tmpdir)
            extra_prompt = self._mktemp_file(".md", "extra prompt")
            gen.vba_generator.generate_vba = MagicMock(return_value="ok")

            result = gen.generate_parameters(
                description="d",
                output_file="p.bas",
                prompt_file=extra_prompt,
            )

            self.assertEqual(result, "ok")
            kwargs = gen.vba_generator.generate_vba.call_args.kwargs
            self.assertEqual(kwargs["filename"], str(Path(tmpdir) / "p.bas"))
            self.assertIn(extra_prompt, kwargs["prompt_files"])
            self.assertGreaterEqual(len(kwargs["prompt_files"]), 2)

    def test_parameter_generator_rejects_missing_prompt_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ParameterGenerator(save_dir=tmpdir)
            with self.assertRaises(InputValidationError):
                gen.generate_parameters(prompt_file=str(Path(tmpdir) / "x.md"))

    def test_model2d_generator_forwards_additional_prompt_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = Model2DGenerator(save_dir=tmpdir)
            extra_prompt = self._mktemp_file(".md", "extra prompt")
            gen.vba_generator.generate_vba = MagicMock(return_value="ok")

            gen.generate_model(
                description="d",
                additional_prompt_files=[extra_prompt],
                save_as="m.bas",
            )

            kwargs = gen.vba_generator.generate_vba.call_args.kwargs
            self.assertEqual(kwargs["filename"], str(Path(tmpdir) / "m.bas"))
            self.assertIn(extra_prompt, kwargs["prompt_files"])

    def test_boolean_generator_filters_delete_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = BooleanOperationsGenerator(save_dir=tmpdir)
            gen.vba_generator.generate_vba = MagicMock(
                return_value=(
                    "With Solid\n"
                    ".Delete \"X\"\n"
                    "Solid.Delete \"Y\"\n"
                    ".Subtract \"A\", \"B\"\n"
                    "End With\n"
                )
            )

            output = gen.generate_operations(save_as="boolean.bas")
            output_path = Path(tmpdir) / "boolean.bas"
            saved = output_path.read_text(encoding="utf-8")

            self.assertIn(".Subtract", output)
            self.assertNotIn(".Delete", output)
            self.assertNotIn("Solid.Delete", output)
            self.assertEqual(saved, output)

    def test_vba_generator_strips_single_letter_before_member_call(self) -> None:
        generator = VBAGenerator()

        cleaned = generator._clean_vba(
            "a\nSolid.Subtract \"component1:patch\", \"component1:slot\"\n"
        )

        self.assertEqual(
            cleaned,
            'Solid.Subtract "component1:patch", "component1:slot"\n',
        )

    def test_default_save_dir_does_not_create_output_directory_on_init(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "leam.utils.file_io.os.getcwd",
            return_value=tmpdir,
        ):
            output_dir = Path(tmpdir) / "output"

            generator = ParameterGenerator()

            self.assertEqual(generator.save_dir, str(output_dir))
            self.assertFalse(output_dir.exists())

    def test_script_generator_creates_parent_directory_only_when_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "nested" / "artifact.py"
            generator = ScriptGenerator(extension=".py")

            generator._save_to_file("print('ok')\n", str(target))

            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "print('ok')\n")


if __name__ == "__main__":
    unittest.main()
