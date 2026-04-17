import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from leam.desktop.services.structure import (
    load_materials_preview,
    load_parameters_preview,
    load_solids_preview,
)


class DesktopStructurePreviewTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_parameters_preview_parses_rows(self):
        path = Path(self.tempdir.name) / "parameters.json"
        path.write_text(
            json.dumps(
                {
                    "representation": "parameters",
                    "items": [
                        {"name": "Wsub", "value": "30", "notes": "Substrate width"},
                        {"name": "Lsub", "value": "20", "notes": "Substrate length"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        preview = load_parameters_preview(str(path))

        self.assertEqual(preview.kind, "parameters")
        self.assertEqual(preview.summary, "2 parameters")
        self.assertEqual(preview.rows[0], ["Wsub", "30", "Substrate width"])

    def test_materials_preview_parses_rows(self):
        path = Path(self.tempdir.name) / "materials.json"
        path.write_text(
            json.dumps(
                {
                    "representation": "materials",
                    "items": [
                        {
                            "name": "Rogers RO4003C (lossy)",
                            "file": "Rogers RO4003C (lossy).mtd",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        preview = load_materials_preview(str(path))

        self.assertEqual(preview.kind, "materials")
        self.assertEqual(preview.summary, "1 material")
        self.assertEqual(
            preview.rows[0],
            ["Rogers RO4003C (lossy)", "Rogers RO4003C (lossy).mtd"],
        )

    def test_materials_preview_parses_resolved_hfss_rows(self):
        path = Path(self.tempdir.name) / "materials.json"
        path.write_text(
            json.dumps(
                {
                    "representation": "materials",
                    "items": [
                        {
                            "name": "Rogers RO4003C (lossy)",
                            "source": "hfss_library",
                            "builtin": False,
                            "notes": "",
                        },
                        {
                            "name": "pec",
                            "source": "builtin",
                            "builtin": True,
                            "notes": "",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        preview = load_materials_preview(str(path))

        self.assertEqual(preview.kind, "materials")
        self.assertEqual(preview.summary, "2 materials")
        self.assertEqual(preview.headers, ["Name", "Source", "Builtin", "Notes"])
        self.assertEqual(
            preview.rows[0],
            ["Rogers RO4003C (lossy)", "hfss_library", "False", ""],
        )
        self.assertEqual(preview.rows[1], ["pec", "builtin", "True", ""])

    def test_solids_preview_parses_list_and_detail_fields(self):
        path = Path(self.tempdir.name) / "solids.json"
        path.write_text(
            json.dumps(
                {
                    "solids": [
                        {
                            "Type": "2.5D",
                            "name": "slot",
                            "Role": "Cutout",
                            "material": "Copper",
                            "dimensions": {
                                "shape": "Closed spline",
                                "z_range": ["ts", "ts+tp"],
                            },
                            "operations": ["subtract from patch"],
                            "notes": "Slot profile",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        preview = load_solids_preview(str(path))

        self.assertEqual(preview.kind, "solids")
        self.assertEqual(preview.summary, "1 solid")
        self.assertEqual(preview.solids[0].name, "slot")
        self.assertEqual(preview.solids[0].solid_type, "2.5D")
        self.assertIn("shape: Closed spline", preview.solids[0].dimensions_text)
        self.assertEqual(preview.solids[0].operations_text, "subtract from patch")


if __name__ == "__main__":
    unittest.main()
