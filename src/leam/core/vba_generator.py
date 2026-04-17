"""VBA-focused wrapper around the generic script generator."""

import re
from typing import List, Optional

from ..utils.constants import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT
from ..utils.file_io import prepare_output_path
from .errors import GenerationError
from .script_generator import ScriptGenerator


class VBAGenerator:
    """Generate CST-compatible VBA macro files from LLM outputs."""

    def __init__(self, default_model: str = DEFAULT_MODEL):
        """Initialize the VBA generator."""
        self.generator = ScriptGenerator(
            default_model=default_model,
            extension=".bas",
            language_tags=["vb", "vba", "visualbasic"],
            json_keys=["vba_macro", "content", "macro"],
        )

    def configure_llm_tools(
        self,
        tools: Optional[List[dict]] = None,
        tool_choice: Optional[object] = None,
    ) -> None:
        """Configure default tools/tool choice for VBA generation calls."""
        self.generator.configure_llm_tools(tools=tools, tool_choice=tool_choice)

    def generate_vba(
        self,
        prompt_files: List[str],
        filename: str,
        model: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        description: Optional[str] = None,
        reasoning_effort: Optional[str] = DEFAULT_REASONING_EFFORT,
        json_schema_hint: Optional[str] = None,
        pdf_paths: Optional[List[str]] = None,
    ) -> str:
        """Generate VBA code, normalize headers, and persist final content."""
        code = self.generator.generate_script(
            prompt_files=prompt_files,
            filename=filename,
            model=model,
            image_paths=image_paths,
            description=description,
            reasoning_effort=reasoning_effort,
            json_schema_hint=json_schema_hint,
            pdf_paths=pdf_paths,
        )

        cleaned = self._clean_vba(code)
        if not cleaned.strip():
            raise GenerationError("Generated VBA code is empty.")
        if cleaned != code:
            self._rewrite_file(filename, cleaned)
        return cleaned

    def _clean_vba(self, code: str) -> str:
        """Normalize occasional malformed leading tokens in generated VBA."""
        text = (code or "").lstrip("\ufeff")
        lines = text.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        if len(lines) >= 2:
            first = lines[0].strip()
            second = lines[1].lstrip()
            if re.match(r"^[A-Za-z]$", first) and self._looks_like_vba_statement(
                second
            ):
                lines.pop(0)
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _looks_like_vba_statement(line: str) -> bool:
        """Return True when a line looks like a real VBA statement."""
        return bool(
            re.match(
                r"^(Dim|With|Sub|Function|StoreParameter|StoreParameters|Rebuild|End|If|For|While|Do|Set|Call)\b",
                line,
                flags=re.IGNORECASE,
            )
            or re.match(
                r"^(?:\.|[A-Za-z_][A-Za-z0-9_]*\.)[A-Za-z_][A-Za-z0-9_]*\b",
                line,
                flags=re.IGNORECASE,
            )
        )

    def _rewrite_file(self, filename: str, code: str) -> None:
        """Rewrite cleaned VBA code to the target file path."""
        target = filename
        if not target.lower().endswith(".bas"):
            target += ".bas"
        target = prepare_output_path(target)
        with open(target, "w", encoding="utf-8") as output_file:
            output_file.write(code)
