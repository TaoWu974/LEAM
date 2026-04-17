"""Shared script-generation helpers for code-like LLM outputs."""

from typing import List, Optional, Sequence

from ..utils.constants import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT
from ..utils.file_io import prepare_output_path
from ..utils.json_utils import parse_json_maybe
from .errors import GenerationError
from .llm_caller import LLMCaller


class ScriptGenerator:
    """Generate text artifacts with fenced-code and JSON payload extraction."""

    def __init__(
        self,
        default_model: str = DEFAULT_MODEL,
        extension: str = ".txt",
        language_tags: Optional[Sequence[str]] = None,
        json_keys: Optional[Sequence[str]] = None,
    ):
        """Prepare extraction rules and a reusable low-level caller."""
        self.llm_caller = LLMCaller(default_model=default_model)
        self.extension = extension if extension.startswith(".") else f".{extension}"
        self.language_tags = {tag.lower() for tag in (language_tags or [])}
        self.json_keys = list(json_keys or [])

    def configure_llm_tools(
        self,
        tools: Optional[List[dict]] = None,
        tool_choice: Optional[object] = None,
    ) -> None:
        """Configure default tools/tool choice on the underlying LLM caller."""
        self.llm_caller.set_default_tools(tools)
        self.llm_caller.set_default_tool_choice(tool_choice)

    def _strip_language_tag_line(self, text: str) -> str:
        """Remove leading language tag line that some models emit."""
        candidate = (text or "").lstrip("\ufeff").lstrip()
        lines = candidate.splitlines()
        first_line = lines[0].strip().lower() if lines else ""
        if first_line in self.language_tags:
            return "\n".join(lines[1:]).lstrip()
        return candidate

    def _extract_from_fence(self, text: str) -> Optional[str]:
        """Extract code from a markdown fenced block if available."""
        for tag in self.language_tags:
            fence = f"```{tag}"
            if fence in text:
                try:
                    return text.split(fence, 1)[1].split("```", 1)[0].strip()
                except IndexError:
                    return None
        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return None

    def _extract_code(self, result: str) -> str:
        """Resolve model output into the final script body.

        Extraction order:
        1. Structured JSON keys (for schema-driven prompts).
        2. Markdown fenced code block.
        3. Raw output fallback.
        """
        sanitized = self._strip_language_tag_line(result or "")

        parsed = parse_json_maybe(sanitized)
        if isinstance(parsed, dict):
            for key in self.json_keys:
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    return self._strip_language_tag_line(value)

        fenced = self._extract_from_fence(sanitized)
        if fenced:
            return self._strip_language_tag_line(fenced)

        return self._strip_language_tag_line(sanitized)

    def _save_to_file(self, code: str, filename: str) -> None:
        """Persist generated script to disk with normalized extension."""
        if not filename.lower().endswith(self.extension):
            filename += self.extension

        cleaned = self._strip_language_tag_line(code or "")
        target = prepare_output_path(filename)
        with open(target, "w", encoding="utf-8") as output_file:
            output_file.write(cleaned)

    def generate_script(
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
        """Generate, validate, and save one script artifact."""
        result = self.llm_caller.call_llm(
            prompt_files=prompt_files,
            model=model,
            image_paths=image_paths,
            description=description,
            reasoning_effort=reasoning_effort,
            json_schema_hint=json_schema_hint,
            pdf_paths=pdf_paths,
        )

        code = self._extract_code(result)
        if not code.strip():
            raise GenerationError("LLM returned an empty script payload.")
        self._save_to_file(code, filename)
        return code
