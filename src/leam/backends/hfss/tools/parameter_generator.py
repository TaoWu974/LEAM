import ast
import json
import os
import re
from typing import List, Optional

from leam.backends.hfss.paths import prompt_path
from leam.core.errors import InputValidationError
from leam.core.python_script_generator import PythonScriptGenerator
from leam.utils.constants import DEFAULT_MODEL
from leam.utils.file_io import prepare_output_path, resolve_save_dir
from leam.utils.json_utils import ensure_json_filename

_PARAMETER_TOOLS = [
    {"type": "code_interpreter", "container": {"type": "auto"}}
]
_PARAMETER_TOOL_CHOICE = "auto"
PARAMETER_COMMENT_RE = re.compile(
    r"\s+#\s*(.*)$"
)
VALID_PARAMETER_OWNERS = {"hfss", "aedtapp", "app"}


class ParameterGenerator:
    """Generate HFSS parameter scripts and companion parameter JSON."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        save_dir: Optional[str] = None,
    ):
        self.script_generator = PythonScriptGenerator(default_model=model)
        self.script_generator.configure_llm_tools(
            tools=_PARAMETER_TOOLS,
            tool_choice=_PARAMETER_TOOL_CHOICE,
        )
        self.reasoning_effort = "medium"
        self.default_prompt_file = prompt_path("parameter_prompt.md")
        self.save_dir = resolve_save_dir(save_dir)

    @staticmethod
    def extract_parameters_from_script(code: str) -> dict:
        """Parse one generated HFSS parameter script into canonical JSON."""
        lines = str(code or "").splitlines()
        try:
            tree = ast.parse(str(code or ""))
        except SyntaxError:
            tree = None

        items = []
        seen = set()

        def _inline_comment_for_lineno(lineno: int) -> str:
            if lineno <= 0 or lineno > len(lines):
                return ""
            match = PARAMETER_COMMENT_RE.search(lines[lineno - 1])
            return str(match.group(1) or "").strip() if match else ""

        def _append_item(name: str, value: str, notes: str) -> None:
            normalized_name = str(name or "").strip()
            normalized_value = str(value or "").strip()
            normalized_notes = str(notes or "").strip()
            if not normalized_name:
                return
            key = (normalized_name, normalized_value, normalized_notes)
            if key in seen:
                return
            seen.add(key)
            items.append(
                {
                    "name": normalized_name,
                    "value": normalized_value,
                    "notes": normalized_notes,
                }
            )

        def _extract_string(node) -> Optional[str]:
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return node.value
            return None

        def _extract_subscript_key(node) -> Optional[str]:
            if isinstance(node, ast.Subscript):
                owner = getattr(node.value, "id", None)
                if owner not in VALID_PARAMETER_OWNERS:
                    return None
                if isinstance(node.slice, ast.Constant) and isinstance(
                    node.slice.value, str
                ):
                    return node.slice.value
            return None

        def _extract_set_variable(call: ast.Call) -> Optional[tuple[str, str]]:
            func = call.func
            if not isinstance(func, ast.Attribute) or func.attr != "set_variable":
                return None
            owner = getattr(getattr(func, "value", None), "value", None)
            if getattr(owner, "id", None) not in VALID_PARAMETER_OWNERS:
                return None

            name = None
            value = None
            if call.args:
                name = _extract_string(call.args[0])
            if len(call.args) >= 2:
                value = _extract_string(call.args[1])
            for keyword in call.keywords:
                if keyword.arg in {"name", "variable"} and name is None:
                    name = _extract_string(keyword.value)
                if keyword.arg == "expression" and value is None:
                    value = _extract_string(keyword.value)
            if name is None or value is None:
                return None
            return name, value

        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    name = _extract_subscript_key(node.targets[0])
                    value = _extract_string(node.value)
                    if name is not None and value is not None:
                        _append_item(
                            name,
                            value,
                            _inline_comment_for_lineno(getattr(node, "lineno", 0)),
                        )
                elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    extracted = _extract_set_variable(node.value)
                    if extracted is not None:
                        _append_item(
                            extracted[0],
                            extracted[1],
                            _inline_comment_for_lineno(getattr(node, "lineno", 0)),
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
        """Persist parsed parameter metadata next to the generated script."""
        output_path = os.path.join(
            self.save_dir,
            ensure_json_filename(json_file),
        )
        output_path = prepare_output_path(output_path)
        with open(output_path, "w", encoding="utf-8") as output_file:
            json.dump(parameters, output_file, indent=2)
            output_file.write("\n")
        return output_path

    def generate_parameters(
        self,
        description: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        output_file: str = "parameters.py",
        json_file: str = "parameters.json",
        prompt_file: Optional[str] = None,
        additional_prompt_files: Optional[List[str]] = None,
        pdf_paths: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Generate HFSS parameters and companion JSON from descriptions and images."""
        prompt_files = [self.default_prompt_file]
        if additional_prompt_files:
            prompt_files.extend(additional_prompt_files)
        if prompt_file:
            if not os.path.exists(prompt_file):
                raise InputValidationError(
                    f"Prompt file not found: {prompt_file}"
                )
            prompt_files.append(prompt_file)

        code = self.script_generator.generate_script(
            prompt_files=prompt_files,
            filename=os.path.join(self.save_dir, output_file),
            description=description,
            image_paths=image_paths,
            reasoning_effort=self.reasoning_effort,
            pdf_paths=pdf_paths,
        )
        parameters = self.extract_parameters_from_script(code)
        self.save_parameters_json(parameters, json_file)
        return code
