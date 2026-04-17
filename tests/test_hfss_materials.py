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

from leam.backends.hfss.paths import prompt_path as hfss_prompt_path
from leam.backends.hfss.paths import resource_path as hfss_resource_path
from leam.backends.hfss.tools.materials import MaterialsProcessor
from leam.backends.hfss.tools.model_2d_generator import Model2DGenerator
from leam.backends.hfss.tools.model_3d_generator import Model3DGenerator
from leam.core.errors import InputValidationError


class HfssMaterialsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
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
        self.tempdir.cleanup()

    def _create_hfss_library(self) -> Path:
        hfss_root = Path(self.tempdir.name) / "hfss"
        syslib_dir = hfss_root / "syslib"
        syslib_dir.mkdir(parents=True, exist_ok=True)
        (syslib_dir / "materials.amat").write_text(
            "\n".join(
                [
                    "$begin 'Rogers RO4003C (lossy)'",
                    "permittivity='3.55'",
                    "$end 'Rogers RO4003C (lossy)'",
                    "$begin 'Copper (pure)'",
                    "conductivity='58000000'",
                    "$end 'Copper (pure)'",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return hfss_root

    def test_generate_materials_resolves_library_names_and_writes_json(self) -> None:
        hfss_root = self._create_hfss_library()
        processor = MaterialsProcessor(
            save_dir=self.tempdir.name,
            hfss_path=str(hfss_root),
        )
        processor.llm_caller.call_llm = MagicMock(
            return_value=json.dumps(
                {
                    "representation": "materials",
                    "items": [
                        {"name": "Rogers RO4003C lossy"},
                        {"name": "PEC"},
                        {"name": "vacuum"},
                    ],
                }
            )
        )

        resolved = processor.generate_materials(
            description="Substrate uses Rogers RO4003C and the ground is PEC.",
            save_as="materials.json",
        )

        self.assertEqual(
            resolved,
            ["Rogers RO4003C (lossy)", "pec", "vacuum"],
        )

        payload = json.loads(
            (Path(self.tempdir.name) / "materials.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["representation"], "materials")
        self.assertEqual(
            payload["items"],
            [
                {
                    "name": "Rogers RO4003C (lossy)",
                    "source": "syslibrary",
                    "builtin": False,
                    "notes": "",
                },
                {
                    "name": "pec",
                    "source": "builtin",
                    "builtin": True,
                    "notes": "",
                },
                {
                    "name": "vacuum",
                    "source": "builtin",
                    "builtin": True,
                    "notes": "",
                },
            ],
        )
        self.assertFalse((Path(self.tempdir.name) / "materials.py").exists())

    def test_process_material_files_skips_builtins_and_loads_custom_blocks(self) -> None:
        hfss_root = self._create_hfss_library()
        processor = MaterialsProcessor(
            save_dir=self.tempdir.name,
            hfss_path=str(hfss_root),
        )

        material_contents = processor.process_material_files(
            ["vacuum", "pec", "Rogers RO4003C (lossy)"]
        )

        self.assertIn("$begin 'Rogers RO4003C (lossy)'", material_contents)
        self.assertNotIn("$begin 'vacuum'", material_contents)
        self.assertNotIn("$begin 'pec'", material_contents)

    def test_material_discovery_only_reads_syslibrary(self) -> None:
        hfss_root = self._create_hfss_library()
        userlib_dir = hfss_root / "userlib"
        userlib_dir.mkdir(parents=True, exist_ok=True)
        (userlib_dir / "custom.amat").write_text(
            "\n".join(
                [
                    "$begin 'User Only Material'",
                    "permittivity='9.9'",
                    "$end 'User Only Material'",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        processor = MaterialsProcessor(
            save_dir=self.tempdir.name,
            hfss_path=str(hfss_root),
        )

        available = processor._list_available_materials()

        self.assertIn("Rogers RO4003C (lossy)", available)
        self.assertNotIn("User Only Material", available)

    def test_hfss_material_prompts_require_reusing_resolved_names(self) -> None:
        extract_prompt = Path(
            hfss_prompt_path("materials_extract_prompt.md")
        ).read_text(encoding="utf-8")
        custom_prompt = Path(
            hfss_prompt_path("materials_python_prompt.md")
        ).read_text(encoding="utf-8")
        modeling_2d_prompt = Path(
            hfss_prompt_path("modeling_2d_prompt.md")
        ).read_text(encoding="utf-8")
        modeling_3d_prompt = Path(
            hfss_prompt_path("modeling_3d_prompt.md")
        ).read_text(encoding="utf-8")

        self.assertIn("Do not invent new material names.", extract_prompt)
        self.assertIn("Do not write any material creation or import script.", extract_prompt)
        self.assertIn("canonical built-in names `vacuum` and `pec`", extract_prompt)

        self.assertIn("only for custom materials", custom_prompt)
        self.assertIn("Do not recreate built-in materials such as `vacuum` or `pec`.", custom_prompt)

        self.assertIn("Read the exact HFSS material name from each `items[].name` entry", modeling_2d_prompt)
        self.assertIn("Do not create, import, or redefine materials in this step.", modeling_2d_prompt)
        self.assertIn("support only extruded profiles", modeling_2d_prompt)
        self.assertNotIn("extrude/rotate", modeling_2d_prompt)
        self.assertIn("use the exact resolved material names from that file", modeling_3d_prompt)
        self.assertIn("Read the exact HFSS material name from each `items[].name` entry", modeling_3d_prompt)
        self.assertIn("Do not create, import, or redefine materials in this step.", modeling_3d_prompt)

    def test_model_generators_forward_materials_json_context(self) -> None:
        materials_path = Path(self.tempdir.name) / "materials.json"
        materials_path.write_text(
            json.dumps(
                {
                    "representation": "materials",
                    "items": [{"name": "Rogers RO4003C (lossy)"}],
                }
            ),
            encoding="utf-8",
        )

        model_2d = Model2DGenerator(save_dir=self.tempdir.name)
        model_2d.script_generator.generate_script = MagicMock(return_value="ok")
        model_2d.generate_model(
            description="2d",
            materials_file=str(materials_path),
            save_as="model_2d.py",
        )

        kwargs_2d = model_2d.script_generator.generate_script.call_args.kwargs
        self.assertEqual(
            kwargs_2d["filename"],
            str(Path(self.tempdir.name) / "model_2d.py"),
        )
        self.assertIn(str(materials_path), kwargs_2d["prompt_files"])
        self.assertIn(hfss_resource_path("extrude.md"), kwargs_2d["prompt_files"])
        self.assertIn(hfss_resource_path("transform.md"), kwargs_2d["prompt_files"])

        model_3d = Model3DGenerator(save_dir=self.tempdir.name)
        model_3d.script_generator.generate_script = MagicMock(return_value="ok")
        model_3d.generate_model(
            description="3d",
            materials_file=str(materials_path),
            save_as="model_3d.py",
        )

        kwargs_3d = model_3d.script_generator.generate_script.call_args.kwargs
        self.assertEqual(
            kwargs_3d["filename"],
            str(Path(self.tempdir.name) / "model_3d.py"),
        )
        self.assertIn(str(materials_path), kwargs_3d["prompt_files"])

    def test_model_generators_reject_missing_materials_json(self) -> None:
        missing_path = str(Path(self.tempdir.name) / "missing_materials.json")

        with self.assertRaises(InputValidationError):
            Model2DGenerator(save_dir=self.tempdir.name).generate_model(
                materials_file=missing_path
            )

        with self.assertRaises(InputValidationError):
            Model3DGenerator(save_dir=self.tempdir.name).generate_model(
                materials_file=missing_path
            )


if __name__ == "__main__":
    unittest.main()
