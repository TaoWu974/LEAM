"""Python-script specialization built on the generic script generator."""

from typing import List, Optional

from ..utils.constants import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT
from .script_generator import ScriptGenerator


class PythonScriptGenerator:
    """Generate Python files using the shared script extraction pipeline."""

    def __init__(self, default_model: str = DEFAULT_MODEL):
        """Initialize the Python script generator."""
        self.generator = ScriptGenerator(
            default_model=default_model,
            extension=".py",
            language_tags=["python", "py"],
            json_keys=["python_script", "script", "code", "content"],
        )

    def configure_llm_tools(
        self,
        tools: Optional[List[dict]] = None,
        tool_choice: Optional[object] = None,
    ) -> None:
        """Configure default tools/tool choice for Python generation calls."""
        self.generator.configure_llm_tools(
            tools=tools, tool_choice=tool_choice
        )

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
        """Generate and persist one Python script artifact."""
        return self.generator.generate_script(
            prompt_files=prompt_files,
            filename=filename,
            model=model,
            image_paths=image_paths,
            description=description,
            reasoning_effort=reasoning_effort,
            json_schema_hint=json_schema_hint,
            pdf_paths=pdf_paths,
        )
