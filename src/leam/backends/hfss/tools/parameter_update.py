import os
from typing import List, Optional

from leam.backends.hfss.paths import prompt_path
from leam.core.python_script_generator import PythonScriptGenerator
from leam.utils.constants import DEFAULT_MODEL
from leam.utils.file_io import resolve_save_dir

_PARAMETER_TOOLS = [
    {"type": "code_interpreter", "container": {"type": "auto"}}
]
_PARAMETER_TOOL_CHOICE = "auto"


class ParameterUpdater:
    """Generate scripts that update HFSS parameters."""

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
        self.parameter_prompt = prompt_path("parameter_update_prompt.md")
        self.save_dir = resolve_save_dir(save_dir)

    def generate_update(
        self,
        description: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        additional_prompt_files: Optional[List[str]] = None,
        save_as: str = "parameter_update.py",
        pdf_paths: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Generate Python code for parameter updates."""
        prompt_files = [self.parameter_prompt]
        if additional_prompt_files:
            prompt_files.extend(additional_prompt_files)

        return self.script_generator.generate_script(
            prompt_files=prompt_files,
            filename=os.path.join(self.save_dir, save_as),
            image_paths=image_paths,
            description=description,
            pdf_paths=pdf_paths,
        )
