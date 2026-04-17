"""Material matching and optional custom-material generation for HFSS."""

import difflib
import json
import os
import re
from typing import Dict, List, Optional

from leam.backends.hfss.paths import prompt_path
from leam.config import load_config, resolve_hfss_path
from leam.core.llm_caller import LLMCaller
from leam.core.script_generator import ScriptGenerator
from leam.utils.constants import DEFAULT_MODEL
from leam.utils.file_io import (
    prepare_output_path,
    process_text_files,
    resolve_save_dir,
)
from leam.utils.json_utils import ensure_json_filename, parse_json_maybe


class MaterialsProcessor:
    """Resolve HFSS material assignments and optionally create custom scripts."""

    EXTRACT_PROMPT_PATH = prompt_path("materials_extract_prompt.md")
    GENERATE_PROMPT_PATH = prompt_path("materials_python_prompt.md")
    _BEGIN_RE = re.compile(r"^\$begin '(.+)'$")
    _BUILTIN_MATERIALS = {
        "vacuum": "vacuum",
        "pec": "pec",
        "perfectelectricconductor": "pec",
        "perfect electric conductor": "pec",
    }

    def __init__(
        self,
        save_dir: Optional[str] = None,
        hfss_path: Optional[str] = None,
    ):
        """Initialize HFSS material library discovery and optional generation."""
        config = load_config()
        self.hfss_base_path = hfss_path or resolve_hfss_path(config)
        if self.hfss_base_path and not os.path.isdir(self.hfss_base_path):
            raise ValueError(
                f"HFSS installation path not found: {self.hfss_base_path}"
            )

        self.material_library_roots = self._resolve_material_library_roots()
        self.llm_caller = LLMCaller(default_model=DEFAULT_MODEL)
        self.script_generator = ScriptGenerator(
            default_model=DEFAULT_MODEL,
            extension=".py",
            language_tags=["python", "py"],
            json_keys=["python", "content", "script"],
        )
        self.save_dir = resolve_save_dir(save_dir)

    @staticmethod
    def _base_material_name(name: str) -> str:
        """Normalize a material token while keeping the human-readable name."""
        return str(name or "").strip().strip('"\'`')

    @staticmethod
    def _material_key(name: str) -> str:
        """Normalize a material token for matching."""
        return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())

    def _builtin_material_name(self, name: str) -> Optional[str]:
        """Return the canonical built-in material name when applicable."""
        token = self._base_material_name(name)
        if not token:
            return None
        return self._BUILTIN_MATERIALS.get(self._material_key(token))

    def _resolve_material_library_roots(self) -> List[str]:
        """Resolve the local AEDT SysLibrary root that may contain .amat files."""
        if not self.hfss_base_path:
            return []

        candidates = [os.path.join(self.hfss_base_path, "syslib")]
        roots = []
        for path_value in candidates:
            normalized = os.path.normpath(path_value)
            if os.path.isdir(normalized) and normalized not in roots:
                roots.append(normalized)
        return roots

    def _iter_material_library_files(self) -> List[str]:
        """Return all local .amat files under the configured library roots."""
        files: List[str] = []
        for root in self.material_library_roots:
            for dirpath, _, filenames in os.walk(root):
                for filename in filenames:
                    if filename.lower().endswith(".amat"):
                        files.append(os.path.join(dirpath, filename))
        files.sort(key=str.casefold)
        return files

    def _read_text_lines(self, file_path: str) -> List[str]:
        """Read a material library file with tolerant decoding."""
        with open(file_path, "rb") as input_file:
            return [
                line.decode("utf-8", errors="ignore")
                for line in input_file.read().splitlines()
            ]

    def _extract_material_names(self, file_path: str) -> List[str]:
        """Extract top-level material names from one .amat file."""
        names: List[str] = []
        for line in self._read_text_lines(file_path):
            match = self._BEGIN_RE.match(line)
            if not match:
                continue
            name = match.group(1)
            if name in {"$index$", "$base_index$"}:
                continue
            names.append(name)
        return names

    def _extract_material_block(
        self, file_path: str, material_name: str
    ) -> Optional[str]:
        """Extract the full top-level block for one material from a .amat file."""
        lines = self._read_text_lines(file_path)
        start_line = f"$begin '{material_name}'"
        end_line = f"$end '{material_name}'"
        block: List[str] = []
        in_block = False

        for line in lines:
            if not in_block:
                if line == start_line:
                    in_block = True
                    block.append(line)
                continue

            block.append(line)
            if line == end_line:
                return "\n".join(block)

        return None

    def _list_available_materials(self) -> List[str]:
        """List available HFSS/AEDT material names from local .amat libraries."""
        material_map: Dict[str, str] = {}
        for file_path in self._iter_material_library_files():
            for name in self._extract_material_names(file_path):
                material_map.setdefault(name.casefold(), name)
        return sorted(material_map.values(), key=str.casefold)

    def _resolve_material_match(
        self,
        name: str,
        available_names: List[str],
    ) -> Optional[str]:
        """Map a free-form material token to one built-in or HFSS library name."""
        normalized = self._base_material_name(name)
        if not normalized:
            return None

        builtin_name = self._builtin_material_name(normalized)
        if builtin_name:
            return builtin_name

        by_lower = {value.lower(): value for value in available_names}
        if normalized.lower() in by_lower:
            return by_lower[normalized.lower()]

        by_key = {
            self._material_key(value): value for value in available_names
        }
        key = self._material_key(normalized)
        if key in by_key:
            return by_key[key]

        match = difflib.get_close_matches(
            normalized,
            available_names,
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
        """Resolve HFSS material names from text/image context and local libraries."""
        library_materials = self._list_available_materials()
        available_materials = list(dict.fromkeys(["vacuum", "pec", *library_materials]))
        context_text = self._load_context_blocks(
            prompt_file=prompt_file,
            description=description,
            additional_prompt_files=additional_prompt_files,
        )

        if not available_materials:
            if save_as:
                self._save_materials_json([], save_as)
            return []

        schema_hint = (
            "Return JSON with shape: "
            '{ "representation": "materials", '
            '"items": [ { "name": string, "notes": string } ] }'
        )
        response = self.llm_caller.call_llm(
            prompt_files=[self.EXTRACT_PROMPT_PATH],
            description=(
                f"{context_text}\n\nAvailable materials:\n"
                + "\n".join(available_materials)
            ).strip(),
            image_paths=image_paths,
            json_schema_hint=schema_hint,
            pdf_paths=pdf_paths,
        )

        materials: List[str] = []
        parsed = parse_json_maybe(response)
        if isinstance(parsed, dict):
            for item in parsed.get("items", []) or []:
                raw_name = str(item.get("name") or "").strip()
                matched = self._resolve_material_match(
                    raw_name, library_materials
                )
                if matched:
                    materials.append(matched)
        elif isinstance(response, str):
            for line in response.splitlines():
                raw_name = line.strip()
                matched = self._resolve_material_match(
                    raw_name, library_materials
                )
                if matched:
                    materials.append(matched)

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
        self, materials: List[str], save_as: str
    ) -> None:
        """Write resolved HFSS material matches to the configured output directory."""
        save_path = prepare_output_path(
            os.path.join(self.save_dir, ensure_json_filename(save_as))
        )
        payload = {
            "representation": "materials",
            "items": [
                {
                    "name": name,
                    "source": (
                        "builtin"
                        if self._builtin_material_name(name)
                        else "syslibrary"
                    ),
                    "builtin": bool(self._builtin_material_name(name)),
                    "notes": "",
                }
                for name in materials
            ],
        }
        with open(save_path, "w", encoding="utf-8") as output_file:
            json.dump(payload, output_file, indent=2)
            output_file.write("\n")

    def generate_materials(
        self,
        description: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        prompt_file: Optional[str] = None,
        additional_prompt_files: Optional[List[str]] = None,
        save_as: str = "materials.json",
        pdf_paths: Optional[List[str]] = None,
    ) -> List[str]:
        """Generate HFSS materials JSON using library-name matching only."""
        return self.extract_materials(
            prompt_file=prompt_file,
            save_as=save_as,
            description=description,
            image_paths=image_paths,
            additional_prompt_files=additional_prompt_files,
            pdf_paths=pdf_paths,
        )

    def process_material_files(self, material_names: List[str]) -> str:
        """Load requested custom material definitions from local .amat files."""
        if not self.material_library_roots:
            return ""

        available_lookup = {
            name.casefold(): name for name in self._list_available_materials()
        }
        requested = []
        for name in material_names:
            if self._builtin_material_name(name):
                continue
            canonical = available_lookup.get(name.strip().casefold())
            if canonical:
                requested.append(canonical)
        requested = list(dict.fromkeys(requested))

        missing = [
            name
            for name in material_names
            if not self._builtin_material_name(name)
            and name.strip().casefold() not in available_lookup
        ]
        if missing:
            raise FileNotFoundError(
                "Material definition(s) not found in local HFSS libraries:\n"
                + "\n".join(missing)
            )

        blocks: List[str] = []
        library_files = self._iter_material_library_files()
        for material_name in requested:
            block = None
            for file_path in library_files:
                block = self._extract_material_block(file_path, material_name)
                if block:
                    break
            if not block:
                raise FileNotFoundError(
                    "Material definition not found in local HFSS libraries: "
                    f"{material_name}"
                )
            blocks.append(block)

        return "\n\n".join(blocks)

    def generate_python_script(
        self, material_contents: str, save_filename: Optional[str] = None
    ) -> str:
        """Generate optional custom-material creation code for HFSS."""
        if not material_contents:
            return ""

        save_filename = save_filename or "materials.py"
        save_path = os.path.join(self.save_dir, save_filename)

        return self.script_generator.generate_script(
            prompt_files=[self.GENERATE_PROMPT_PATH],
            filename=save_path,
            description=material_contents,
        )

    def generate_material_script(
        self, material_contents: str, save_filename: Optional[str] = None
    ) -> str:
        """Generate an optional HFSS custom-material script."""
        return self.generate_python_script(material_contents, save_filename)
