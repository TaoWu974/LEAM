"""Solid generator that expects detailed design descriptions."""

from typing import Optional

from leam.backends.cst.paths import prompt_path
from leam.utils.constants import DEFAULT_MODEL

from .solids_generator import SolidsGeneratorBase


class StrongDescriptionToSolids(SolidsGeneratorBase):
    """Generate solids from detailed descriptions and images."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        save_dir: Optional[str] = None,
    ):
        """Bind strong-description prompt resources."""
        prompt_files = [prompt_path("strong_description_to_solids.md")]
        super().__init__(
            prompt_files=prompt_files,
            model=model,
            save_dir=save_dir,
        )
