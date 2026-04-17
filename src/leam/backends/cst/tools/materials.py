"""Material extraction and VBA import macro generation for CST."""

import difflib
import json
import os
import re
from typing import List, Optional

from leam.backends.cst.paths import prompt_path
from leam.config import load_config, resolve_cst_path
from leam.core.llm_caller import LLMCaller
from leam.core.vba_generator import VBAGenerator
from leam.utils.constants import DEFAULT_MODEL
from leam.utils.file_io import (
    prepare_output_path,
    process_text_files,
    resolve_save_dir,
)
from leam.utils.json_utils import ensure_json_filename, parse_json_maybe


class MaterialsProcessor:
    """Extract available CST materials and generate import macros."""

    EXTRACT_PROMPT_PATH = prompt_path("materials_extract_prompt.md")
    GENERATE_PROMPT_PATH = prompt_path("materials_vba_prompt.md")
    BUILTIN_MATERIALS = {
        "vacuum",
        "pec",
        "perfectelectricconductor",
    }

    def __init__(
        self,
        save_dir: Optional[str] = None,
        cst_path: Optional[str] = None,
    ):
        """Initialize material library location and generation dependencies."""
        config = load_config()
        self.cst_base_path = cst_path or resolve_cst_path(config)
        self.cst_material_path = (
            os.path.join(self.cst_base_path, "Library", "Materials")
            if self.cst_base_path
            else None
        )
        if self.cst_material_path and not os.path.isdir(self.cst_material_path):
            raise ValueError(
                f"Material library path not found: {self.cst_material_path}"
            )

        self.llm_caller = LLMCaller(default_model=DEFAULT_MODEL)
        self.vba_generator = VBAGenerator(default_model=DEFAULT_MODEL)
        self.save_dir = resolve_save_dir(save_dir)

    def _list_available_materials(self) -> List[str]:
        """List .mtd material filenames from the CST material library."""
        if not self.cst_material_path:
            return []

        if not os.path.isdir(self.cst_material_path):
            raise ValueError(
                f"Material library path not found: {self.cst_material_path}"
            )

        materials = []
        for entry in os.listdir(self.cst_material_path):
            full_path = os.path.join(self.cst_material_path, entry)
            if os.path.isfile(full_path) and entry.lower().endswith(".mtd"):
                materials.append(entry)

        materials.sort(key=str.casefold)
        return materials

    @staticmethod
    def _base_material_name(name: str) -> str:
        """Return a material name without the .mtd suffix."""
        value = str(name or "").strip().strip('"\'`')
        if value.lower().endswith(".mtd"):
            value = value[:-4]
        return value.strip()

    @staticmethod
    def _material_key(name: str) -> str:
        """Normalize material names for fuzzy matching and comparisons."""
        return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())

    def _is_builtin_material(self, name: str) -> bool:
        """Return True for built-in materials that do not need import macros."""
        base_name = self._base_material_name(name)
        return self._material_key(base_name) in self.BUILTIN_MATERIALS

    def _resolve_material_match(
        self,
        name: str,
        available_bases: List[str],
    ) -> Optional[str]:
        """Map a free-form material token to the closest CST library entry."""
        normalized = self._base_material_name(name)
        if not normalized:
            return None

        key = self._material_key(normalized)
        if key in self.BUILTIN_MATERIALS:
            return None

        by_lower = {base.lower(): base for base in available_bases}
        if normalized.lower() in by_lower:
            return by_lower[normalized.lower()]

        by_key = {self._material_key(base): base for base in available_bases}
        if key in by_key:
            return by_key[key]

        match = difflib.get_close_matches(
            normalized,
            available_bases,
            n=1,
            cutoff=0.6,
        )
        if match:
            return match[0]

        key_match = difflib.get_close_matches(
            key,
            list(by_key.keys()),
            n=1,
            cutoff=0.6,
        )
        if key_match:
            return by_key[key_match[0]]

        return None

    def _load_context_blocks(
        self,
        prompt_file: Optional[str],
        description: Optional[str],
        additional_prompt_files: Optional[List[str]],
    ) -> str:
        """Merge free-form text context and optional prompt files into one block."""
        blocks: List[str] = []
        if description:
            blocks.append(str(description).strip())

        if prompt_file:
            if not os.path.isfile(prompt_file):
                raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
            blocks.append(process_text_files([prompt_file]))

        existing_files = [
            path
            for path in (additional_prompt_files or [])
            if path and os.path.isfile(path)
        ]
        if existing_files:
            blocks.append(process_text_files(existing_files))

        return "\n\n".join(block for block in blocks if block)

    def extract_materials(
        self,
        prompt_file: Optional[str] = None,
        save_as: Optional[str] = None,
        description: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        additional_prompt_files: Optional[List[str]] = None,
        pdf_paths: Optional[List[str]] = None,
    ) -> List[str]:
        """Extract material names from text/image context."""
        material_names = self._list_available_materials()
        if not material_names:
            if save_as:
                self._save_materials_json([], save_as)
            return []

        available_bases = [self._base_material_name(name) for name in material_names]
        file_by_base = {
            base.lower(): file_name
            for base, file_name in zip(available_bases, material_names)
        }
        available_materials = "\n".join(material_names)
        context_text = self._load_context_blocks(
            prompt_file=prompt_file,
            description=description,
            additional_prompt_files=additional_prompt_files,
        )

        schema_hint = (
            "Return JSON with shape: "
            '{ "representation": "materials", '
            '"items": [ { "name": string, "file": string|null, '
            '"notes": string } ] }'
        )
        response = self.llm_caller.call_llm(
            prompt_files=[self.EXTRACT_PROMPT_PATH],
            description=(
                f"{context_text}\n\nAvailable materials:\n{available_materials}".strip()
            ),
            image_paths=image_paths,
            json_schema_hint=schema_hint,
            pdf_paths=pdf_paths,
        )

        materials: List[str] = []
        parsed = parse_json_maybe(response)
        if isinstance(parsed, dict):
            for item in parsed.get("items", []) or []:
                raw_name = str(item.get("file") or item.get("name") or "").strip()
                if not raw_name or self._is_builtin_material(raw_name):
                    continue

                matched = self._resolve_material_match(raw_name, available_bases)
                if matched:
                    file_name = file_by_base.get(matched.lower())
                    if file_name:
                        materials.append(file_name)
                        continue

                if raw_name.lower().endswith(".mtd"):
                    materials.append(raw_name)
                else:
                    materials.append(f"{raw_name}.mtd")
        elif isinstance(response, str):
            for name in response.splitlines():
                raw_name = name.strip()
                if not raw_name or self._is_builtin_material(raw_name):
                    continue
                matched = self._resolve_material_match(raw_name, available_bases)
                if matched:
                    file_name = file_by_base.get(matched.lower())
                    if file_name:
                        materials.append(file_name)
                        continue
                if raw_name.lower().endswith(".mtd"):
                    materials.append(raw_name)
                else:
                    materials.append(f"{raw_name}.mtd")

        deduped: List[str] = []
        seen = set()
        for name in materials:
            key = self._material_key(name)
            if not key or key in seen:
                continue
            deduped.append(name)
            seen.add(key)

        if save_as:
            self._save_materials_json(deduped, save_as)

        return deduped

    def _save_materials_json(
        self,
        materials: List[str],
        save_as: str,
    ) -> None:
        """Write normalized material names to the configured output directory."""
        save_path = prepare_output_path(
            os.path.join(self.save_dir, ensure_json_filename(save_as))
        )
        filtered = [
            name for name in materials if not self._is_builtin_material(name)
        ]
        payload = {
            "representation": "materials",
            "items": [
                {
                    "name": self._base_material_name(name),
                    "file": name,
                }
                for name in filtered
            ],
        }
        with open(save_path, "w", encoding="utf-8") as output_file:
            json.dump(payload, output_file, indent=2)
            output_file.write("\n")

    def process_material_files(self, material_names: List[str]) -> str:
        """Load requested material files and concatenate their textual content."""
        if not self.cst_material_path:
            return ""
        if not os.path.isdir(self.cst_material_path):
            raise ValueError(
                f"Material library path not found: {self.cst_material_path}"
            )

        material_files: List[str] = []
        missing_files: List[str] = []
        for name in material_names:
            value = str(name or "").strip()
            if not value:
                continue

            material_path = os.path.normpath(
                os.path.join(self.cst_material_path, value)
            )
            if os.path.exists(material_path):
                material_files.append(material_path)
            else:
                missing_files.append(material_path)

        if missing_files:
            missing = "\n".join(missing_files)
            raise FileNotFoundError(f"Material file(s) not found:\n{missing}")

        return process_text_files(material_files) if material_files else ""

    def generate_vba_macro(
        self,
        material_contents: str,
        save_filename: Optional[str] = None,
    ) -> str:
        """Generate CST VBA code that recreates requested materials."""
        if not material_contents:
            return ""

        save_filename = save_filename or "materials.bas"
        save_path = os.path.join(self.save_dir, save_filename)

        code = self.vba_generator.generate_vba(
            prompt_files=[self.GENERATE_PROMPT_PATH],
            filename=save_path,
            description=material_contents,
        )
        return code

    def generate_materials(
        self,
        description: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        prompt_file: Optional[str] = None,
        additional_prompt_files: Optional[List[str]] = None,
        save_as: str = "materials.json",
        macro_file: str = "materials.bas",
        pdf_paths: Optional[List[str]] = None,
    ) -> List[str]:
        """Generate materials JSON and the corresponding CST import macro."""
        material_names = self.extract_materials(
            prompt_file=prompt_file,
            save_as=save_as,
            description=description,
            image_paths=image_paths,
            additional_prompt_files=additional_prompt_files,
            pdf_paths=pdf_paths,
        )
        material_contents = self.process_material_files(material_names)
        self.generate_vba_macro(material_contents, save_filename=macro_file)
        return material_names
