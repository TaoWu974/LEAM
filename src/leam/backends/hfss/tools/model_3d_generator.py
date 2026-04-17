import os
from typing import List, Optional

from leam.backends.hfss.paths import prompt_path, resource_path
from leam.core.errors import InputValidationError
from leam.core.python_script_generator import PythonScriptGenerator
from leam.utils.constants import DEFAULT_MODEL
from leam.utils.file_io import resolve_save_dir


class Model3DGenerator:
    """Generate 3D HFSS model scripts."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        save_dir: Optional[str] = None,
    ):
        self.script_generator = PythonScriptGenerator(default_model=model)
        self.prompt_files = [
            prompt_path("modeling_3d_prompt.md"),
            resource_path("modeling_3d.md"),
        ]
        self.save_dir = resolve_save_dir(save_dir)

    def _build_prompt_files(
        self,
        additional_prompt_files: Optional[List[str]] = None,
        materials_file: Optional[str] = None,
    ) -> List[str]:
        """Merge base prompts with optional context files for model generation."""
        prompt_files = list(self.prompt_files)
        seen = {os.path.normcase(os.path.abspath(path)) for path in prompt_files}

        for path in list(additional_prompt_files or []) + [materials_file]:
            if not path:
                continue
            if path == materials_file and not os.path.isfile(path):
                raise InputValidationError(
                    f"HFSS materials file not found: {materials_file}"
                )
            normalized = os.path.normcase(os.path.abspath(path))
            if normalized in seen:
                continue
            prompt_files.append(path)
            seen.add(normalized)

        return prompt_files

    def generate_model(
        self,
        description: Optional[str] = None,
        additional_prompt_files: Optional[List[str]] = None,
        materials_file: Optional[str] = None,
        save_as: str = "model_3d.py",
    ) -> Optional[str]:
        """Generate a 3D HFSS model script from description and material context."""
        prompt_files = self._build_prompt_files(
            additional_prompt_files=additional_prompt_files,
            materials_file=materials_file,
        )
        return self.script_generator.generate_script(
            prompt_files=prompt_files,
            filename=os.path.join(self.save_dir, save_as),
            description=description,
        )
