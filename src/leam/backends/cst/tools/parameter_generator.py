"""CST parameter generation tool."""

import json
import re
from typing import List, Optional

from leam.backends.cst.paths import prompt_path
from leam.utils.constants import DEFAULT_MODEL
from leam.utils.file_io import prepare_output_path
from leam.utils.json_utils import ensure_json_filename

from ._vba_tool_base import CstVbaToolBase

PARAMETER_NAME_RE = re.compile(
    r'^\s*names\((\d+)\)\s*=\s*"((?:[^"]|"")*)"\s*(?:\'\s*(.*))?$',
    re.IGNORECASE,
)
PARAMETER_VALUE_RE = re.compile(
    r'^\s*values\((\d+)\)\s*=\s*"((?:[^"]|"")*)"\s*(?:\'\s*(.*))?$',
    re.IGNORECASE,
)
STORE_PARAMETER_RE = re.compile(
    r'^\s*StoreParameter\s*\(?\s*"((?:[^"]|"")*)"\s*,\s*"((?:[^"]|"")*)"\s*\)?\s*(?:\'\s*(.*))?$',
    re.IGNORECASE,
)


def _unescape_vba_string(value: str) -> str:
    """Decode a VBA string literal payload."""
    return str(value or "").replace('""', '"').strip()


class ParameterGenerator(CstVbaToolBase):
    """Generate CST parameter VBA macros and companion parameters JSON."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        save_dir: Optional[str] = None,
    ):
        """Bind prompts and enable code interpreter defaults for parameters."""
        super().__init__(
            prompt_files=[prompt_path("parameter_prompt.md")],
            model=model,
            save_dir=save_dir,
            enable_code_interpreter=True,
        )

    def extract_parameters_from_macro(self, code: str) -> dict:
        """Parse a generated VBA parameter macro into canonical JSON payload."""
        indexed: dict[int, dict] = {}
        sequential_items: List[dict] = []

        for raw_line in str(code or "").splitlines():
            line = raw_line.rstrip()
            if not line:
                continue

            match = PARAMETER_NAME_RE.match(line)
            if match:
                index = int(match.group(1))
                entry = indexed.setdefault(
                    index,
                    {"name": "", "value": "", "notes": ""},
                )
                entry["name"] = _unescape_vba_string(match.group(2))
                notes = str(match.group(3) or "").strip()
                if notes:
                    entry["notes"] = notes
                continue

            match = PARAMETER_VALUE_RE.match(line)
            if match:
                index = int(match.group(1))
                entry = indexed.setdefault(
                    index,
                    {"name": "", "value": "", "notes": ""},
                )
                entry["value"] = _unescape_vba_string(match.group(2))
                notes = str(match.group(3) or "").strip()
                if notes and not entry.get("notes"):
                    entry["notes"] = notes
                continue

            match = STORE_PARAMETER_RE.match(line)
            if match:
                sequential_items.append(
                    {
                        "name": _unescape_vba_string(match.group(1)),
                        "value": _unescape_vba_string(match.group(2)),
                        "notes": str(match.group(3) or "").strip(),
                    }
                )

        items: List[dict] = []
        for index in sorted(indexed):
            entry = indexed[index]
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            items.append(
                {
                    "name": name,
                    "value": str(entry.get("value") or "").strip(),
                    "notes": str(entry.get("notes") or "").strip(),
                }
            )

        if not items:
            for entry in sequential_items:
                name = str(entry.get("name") or "").strip()
                if not name:
                    continue
                items.append(
                    {
                        "name": name,
                        "value": str(entry.get("value") or "").strip(),
                        "notes": str(entry.get("notes") or "").strip(),
                    }
                )

        return {
            "representation": "parameters",
            "items": items,
        }

    def save_parameters_json(
        self,
        parameters: dict,
        json_file: str = "parameters.json",
    ) -> str:
        """Persist parsed parameter metadata next to the VBA macro."""
        output_path = prepare_output_path(
            self._resolve_output_path(ensure_json_filename(json_file))
        )
        with open(output_path, "w", encoding="utf-8") as output_file:
            json.dump(parameters, output_file, indent=2)
            output_file.write("\n")
        return output_path

    def generate_parameters(
        self,
        description: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        output_file: str = "parameters.bas",
        json_file: str = "parameters.json",
        prompt_file: Optional[str] = None,
        additional_prompt_files: Optional[List[str]] = None,
        pdf_paths: Optional[List[str]] = None,
    ) -> str:
        """Generate a parameter macro and companion parameters JSON."""
        prompt_files = self._build_prompt_files(additional_prompt_files)
        self._append_existing_prompt_file(prompt_files, prompt_file)
        code = self.vba_generator.generate_vba(
            prompt_files=prompt_files,
            filename=self._resolve_output_path(output_file),
            description=description,
            image_paths=image_paths,
            pdf_paths=pdf_paths,
        )
        parameters = self.extract_parameters_from_macro(code)
        self.save_parameters_json(parameters, json_file)
        return code
