"""Common CST VBA tool plumbing used by multiple generator classes."""

import os
from typing import List, Optional, Sequence

from leam.core.errors import InputValidationError
from leam.core.vba_generator import VBAGenerator
from leam.utils.constants import DEFAULT_MODEL
from leam.utils.file_io import prepare_output_path, resolve_save_dir

CODE_INTERPRETER_TOOLS = [
    {"type": "code_interpreter", "container": {"type": "auto"}}
]
CODE_INTERPRETER_TOOL_CHOICE = "auto"


class CstVbaToolBase:
    """Shared VBA generation workflow for CST tools.

    The base class centralizes prompt file composition, output-path handling,
    and optional default tool configuration for Responses API calls.
    """

    def __init__(
        self,
        prompt_files: Sequence[str],
        model: str = DEFAULT_MODEL,
        save_dir: Optional[str] = None,
        enable_code_interpreter: bool = False,
    ):
        """Initialize common CST tool dependencies and defaults."""
        self.vba_generator = VBAGenerator(default_model=model)
        if enable_code_interpreter:
            # Parameter flows opt-in to code interpreter by default.
            self.vba_generator.configure_llm_tools(
                tools=CODE_INTERPRETER_TOOLS,
                tool_choice=CODE_INTERPRETER_TOOL_CHOICE,
            )
        self.prompt_files = list(prompt_files)
        self.save_dir = resolve_save_dir(save_dir)

    def _resolve_output_path(self, save_as: str) -> str:
        """Resolve a generated file name against the configured save directory."""
        return prepare_output_path(os.path.join(self.save_dir, save_as))

    def _build_prompt_files(
        self,
        additional_prompt_files: Optional[Sequence[str]] = None,
    ) -> List[str]:
        """Return base prompt set plus optional one-off additions."""
        prompt_files = list(self.prompt_files)
        if additional_prompt_files:
            prompt_files.extend(additional_prompt_files)
        return prompt_files

    def _append_existing_prompt_file(
        self, prompt_files: List[str], prompt_file: Optional[str]
    ) -> None:
        """Validate and append an external prompt file path."""
        if not prompt_file:
            return
        if not os.path.exists(prompt_file):
            raise InputValidationError(f"Prompt file not found: {prompt_file}")
        prompt_files.append(prompt_file)

    def _generate_vba(
        self,
        save_as: str,
        description: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        additional_prompt_files: Optional[Sequence[str]] = None,
        json_schema_hint: Optional[str] = None,
        pdf_paths: Optional[List[str]] = None,
    ) -> str:
        """Generate and persist a VBA file for a CST tool operation."""
        prompt_files = self._build_prompt_files(additional_prompt_files)
        return self.vba_generator.generate_vba(
            prompt_files=prompt_files,
            filename=self._resolve_output_path(save_as),
            description=description,
            image_paths=image_paths,
            json_schema_hint=json_schema_hint,
            pdf_paths=pdf_paths,
        )
