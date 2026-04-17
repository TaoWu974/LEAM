"""CST 2.5D model macro generator."""

from typing import List, Optional

from leam.backends.cst.paths import prompt_path, resource_path
from leam.utils.constants import DEFAULT_MODEL

from ._vba_tool_base import CstVbaToolBase


class Model2DGenerator(CstVbaToolBase):
    """Generate 2.5D CST model VBA macros."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        save_dir: Optional[str] = None,
    ):
        """Register 2.5D prompts/resources for CST macro generation."""
        super().__init__(
            prompt_files=[
                prompt_path("modeling_2d_prompt.md"),
                resource_path("modeling_2d.md"),
                resource_path("extrude_and_rotate.md"),
            ],
            model=model,
            save_dir=save_dir,
        )

    def generate_model(
        self,
        description: Optional[str] = None,
        additional_prompt_files: Optional[List[str]] = None,
        save_as: str = "model_2d.bas",
    ) -> str:
        """Generate one 2.5D model macro from free-form description."""
        return self._generate_vba(
            save_as=save_as,
            description=description,
            additional_prompt_files=additional_prompt_files,
        )
