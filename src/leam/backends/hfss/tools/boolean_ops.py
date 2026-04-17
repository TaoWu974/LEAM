import os
from typing import List, Optional

from leam.backends.hfss.paths import prompt_path, resource_path
from leam.core.python_script_generator import PythonScriptGenerator
from leam.utils.constants import DEFAULT_MODEL
from leam.utils.file_io import resolve_save_dir


class BooleanOperationsGenerator:
    """Generate HFSS boolean operation scripts."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        save_dir: Optional[str] = None,
    ):
        self.script_generator = PythonScriptGenerator(default_model=model)
        self.prompt_files = [
            prompt_path("boolean_prompt.md"),
            resource_path("boolean_operations.md"),
        ]
        self.save_dir = resolve_save_dir(save_dir)

    def generate_operations(
        self,
        description: Optional[str] = None,
        additional_prompt_files: Optional[List[str]] = None,
        save_as: str = "boolean_ops.py",
    ) -> Optional[str]:
        """Generate HFSS boolean operations from a description."""
        prompt_files = self.prompt_files + (additional_prompt_files or [])
        filename = os.path.join(self.save_dir, save_as)
        return self.script_generator.generate_script(
            prompt_files=prompt_files,
            filename=filename,
            description=description,
        )
