"""CST parameter update macro generator."""

from typing import List, Optional

from leam.backends.cst.paths import prompt_path
from leam.utils.constants import DEFAULT_MODEL

from ._vba_tool_base import CstVbaToolBase


class ParameterUpdater(CstVbaToolBase):
    """Generate VBA macros that update CST parameters."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        save_dir: Optional[str] = None,
    ):
        """Bind update prompt and enable code interpreter defaults."""
        super().__init__(
            prompt_files=[prompt_path("parameter_update_prompt.md")],
            model=model,
            save_dir=save_dir,
            enable_code_interpreter=True,
        )

    def generate_update(
        self,
        description: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        additional_prompt_files: Optional[List[str]] = None,
        save_as: str = "parameter_update.bas",
        pdf_paths: Optional[List[str]] = None,
    ) -> str:
        """Generate one parameter-update macro file."""
        return self._generate_vba(
            save_as=save_as,
            description=description,
            image_paths=image_paths,
            additional_prompt_files=additional_prompt_files,
            pdf_paths=pdf_paths,
        )
