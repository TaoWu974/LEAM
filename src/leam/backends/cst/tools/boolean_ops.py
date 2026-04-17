"""CST boolean-operation macro generator with post-processing cleanup."""

import re
from typing import List, Optional

from leam.backends.cst.paths import prompt_path, resource_path
from leam.utils.constants import DEFAULT_MODEL

from ._vba_tool_base import CstVbaToolBase


class BooleanOperationsGenerator(CstVbaToolBase):
    """Generate VBA macros for boolean operations."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        save_dir: Optional[str] = None,
    ):
        """Register boolean prompt resources for CST macro generation."""
        super().__init__(
            prompt_files=[
                prompt_path("boolean_prompt.md"),
                resource_path("boolean_operations.md"),
            ],
            model=model,
            save_dir=save_dir,
        )

    def generate_operations(
        self,
        description: Optional[str] = None,
        additional_prompt_files: Optional[List[str]] = None,
        save_as: str = "boolean_ops.bas",
    ) -> str:
        """Generate CST boolean operations and remove explicit delete calls."""
        filename = self._resolve_output_path(save_as)
        code = self._generate_vba(
            save_as=save_as,
            description=description,
            additional_prompt_files=additional_prompt_files,
        )

        # Remove explicit delete calls; subtraction tools are auto-deleted.
        filtered: List[str] = []
        for line in code.splitlines():
            if re.match(r"^\s*\.Delete\b", line, flags=re.IGNORECASE):
                continue
            if re.search(r"\bSolid\.Delete\b", line, flags=re.IGNORECASE):
                continue
            filtered.append(line)

        cleaned = self.vba_generator._clean_vba(
            "\n".join(filtered).strip() + "\n"
        )
        if cleaned != (code.strip() + "\n"):
            code = cleaned
            with open(filename, "w", encoding="utf-8") as output_file:
                output_file.write(code)

        return code
