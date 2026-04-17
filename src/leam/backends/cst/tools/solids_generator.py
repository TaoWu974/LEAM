"""Solid extraction, normalization, and persistence utilities for CST flows."""

import json
import os
import re
from typing import List, Optional, Sequence

from leam.core.llm_caller import LLMCaller
from leam.utils.constants import DEFAULT_MODEL
from leam.utils.file_io import prepare_output_path, resolve_save_dir
from leam.utils.json_utils import ensure_json_filename, parse_json_maybe

SOLIDS_SCHEMA_HINT = (
    "Return JSON with shape: "
    '{ "solids": [ { "Type": "3D" or "2.5D", "name": string, "Role": string, '
    '"material": string, "dimensions": object, '
    '"operations": [string], "notes": string } ] }.'
)


SOLIDS_RESPONSE_FORMAT = {
    "type": "json_object",
}

CODE_INTERPRETER_TOOLS = [
    {"type": "code_interpreter", "container": {"type": "auto"}}
]
CODE_INTERPRETER_TOOL_CHOICE = "auto"


def _normalize_type_value(value: Optional[str]) -> Optional[str]:
    """Normalize free-form type tokens into canonical `3D` / `2.5D`."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    normalized = candidate.upper()
    normalized_compact = (
        normalized.replace(".", "").replace("_", "").replace(" ", "")
    )
    if normalized_compact.startswith("3"):
        return "3D"
    if normalized_compact.startswith("2"):
        return "2.5D"
    return None


def _infer_type_from_geometry(solid: dict) -> Optional[str]:
    """Infer solid type from geometry hints embedded in dimensions/reference."""
    dims = solid.get("dimensions", {})
    shape = ""
    if isinstance(dims, dict):
        shape = str(
            dims.get("shape", "")
            or dims.get("Shape", "")
            or dims.get("geometry", "")
            or dims.get("Geometry", "")
        )
    reference = str(solid.get("reference", "") or solid.get("Reference", ""))
    hint = f"{shape} {reference}".lower()

    if any(key in hint for key in ["extrude", "rotate"]):
        return "2.5D"
    if any(
        key in hint
        for key in [
            "brick",
            "cylinder",
            "cone",
            "sphere",
            "torus",
            "prism",
            "wedge",
            "pyramid",
            "elliptical",
        ]
    ):
        return "3D"

    name = str(solid.get("name", "") or solid.get("Name", "")).lower()
    if any(key in name for key in ["extrude", "rotate"]):
        return "2.5D"
    return None


def _guess_type_value(solid: dict, fallback: Optional[str]) -> str:
    """Pick the strongest available type hint for one solid entry."""
    explicit = _normalize_type_value(solid.get("Type"))
    if explicit in {"3D", "2.5D"}:
        return explicit

    inferred = _infer_type_from_geometry(solid)
    if inferred in {"3D", "2.5D"}:
        return inferred

    inferred = _normalize_type_value(fallback)
    if inferred in {"3D", "2.5D"}:
        return inferred

    notes = str(solid.get("notes", "") or solid.get("Notes", "")).lower()
    if any(key in notes for key in ["extrude", "rotate"]):
        return "2.5D"

    return "3D"


def _order_solid_keys(solid: dict) -> dict:
    """Return a deterministic key order to stabilize saved JSON diffs."""
    ordered = {"Type": solid.get("Type")}
    for key in [
        "name",
        "Role",
        "material",
        "dimensions",
        "operations",
        "notes",
    ]:
        if key in solid:
            ordered[key] = solid[key]
    for key, value in solid.items():
        if key in ordered:
            continue
        ordered[key] = value
    return ordered


def _clean_25d_wording(text: str) -> str:
    """Normalize inconsistent 2D/2.5D phrasing from model outputs."""
    cleaned = (
        text.replace("2.5D handled elsewhere", "2.5D")
        .replace("2.5d handled elsewhere", "2.5D")
        .replace("2D handled elsewhere", "2.5D")
        .replace("2d handled elsewhere", "2.5D")
    )
    cleaned = re.sub(r"\b2d\b", "2.5D", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\s*\(\s*2\.?5\s*d\s*\)\s*$", "", cleaned, flags=re.IGNORECASE
    )
    return cleaned


def _looks_like_geometry(value: str) -> bool:
    """Heuristically decide if a free-form token looks like geometry metadata."""
    cleaned = value.strip().lower()
    if not cleaned:
        return False
    return any(
        token in cleaned
        for token in [
            "brick",
            "cylinder",
            "cone",
            "sphere",
            "torus",
            "prism",
            "wedge",
            "pyramid",
            "elliptical",
            "extrude",
            "rotate",
            "revolve",
            "polygon",
            "spline",
            "curve",
            "rectangle",
            "circle",
            "ellipse",
            "line",
        ]
    )


def _canonical_name(value: str) -> str:
    """Generate a normalized key for case-insensitive name matching."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _extract_z_range(dimensions: object) -> Optional[list]:
    """Extract two-point z-range from dimension dictionaries when present."""
    if not isinstance(dimensions, dict):
        return None
    for key in [
        "z_range",
        "z_range_mm",
        "zrange",
        "Zrange",
        "extrude_z_range",
        "extrude_z_range_mm",
        "extrude_zrange",
    ]:
        value = dimensions.get(key)
        if isinstance(value, list) and len(value) == 2:
            return value
    return None


def _extract_referenced_names(operation: str) -> List[str]:
    """Extract referenced target names from boolean operation text."""
    operation = operation.strip()
    if not operation:
        return []

    candidates: List[str] = []
    if re.search(r"\bminus\b", operation, flags=re.IGNORECASE):
        match = re.search(r"\bminus\b\s+(.+)$", operation, flags=re.IGNORECASE)
        if match:
            candidates.append(match.group(1))
    else:
        match = re.search(
            r"\bsubtract\b\s*(?::|->|=>)\s*(.+)$",
            operation,
            flags=re.IGNORECASE,
        )
        if match:
            candidates.append(match.group(1))

    cleaned: List[str] = []
    for candidate in candidates:
        # Strip decorative suffixes and quoted wrappers before splitting.
        candidate = (
            re.sub(r"\s*\([^)]*\)\s*$", "", candidate)
            .strip()
            .strip("\"'`")
        )
        candidate = re.split(
            r"\bfrom\b", candidate, maxsplit=1, flags=re.IGNORECASE
        )[0].strip()
        if " - " in candidate:
            candidate = candidate.split(" - ")[-1].strip()
        if not candidate:
            continue
        parts = re.split(
            r"\s*(?:,|;|\band\b)\s*", candidate, flags=re.IGNORECASE
        )
        for part in parts:
            part = (
                re.sub(r"\s*\([^)]*\)\s*$", "", part)
                .strip()
                .strip("\"'`")
            )
            part = re.split(
                r"\bfrom\b", part, maxsplit=1, flags=re.IGNORECASE
            )[0].strip()
            if " - " in part:
                part = part.split(" - ")[-1].strip()
            if part:
                cleaned.append(part)

    seen = set()
    deduped: List[str] = []
    for name in cleaned:
        key = _canonical_name(name)
        if not key or key in seen:
            continue
        deduped.append(name)
        seen.add(key)
    return deduped


def _infer_placeholder_type(reference_name: str, operation: str) -> str:
    """Infer type for auto-injected placeholder solids from operation context."""
    hint = f"{reference_name} {operation}".lower()
    if "2.5d" in hint or any(
        key in hint
        for key in ["extrude", "rotate", "spline", "polygon", "profile"]
    ):
        return "2.5D"
    if any(
        key in hint
        for key in ["brick", "cylinder", "cone", "sphere", "torus", "prism"]
    ):
        return "3D"
    return "3D"


def normalize_solids_payload(solids: str) -> str:
    """Normalize LLM solids payload into canonical and dependency-safe JSON."""
    parsed = parse_json_maybe(solids)
    if parsed is None:
        return solids

    top_level_type: Optional[str] = None
    solids_list = None

    if isinstance(parsed, dict):
        representation = parsed.get("representation")
        type_value = parsed.get("Type")
        if isinstance(type_value, str) and type_value.strip():
            top_level_type = type_value.strip()
        elif isinstance(representation, str) and representation.strip():
            top_level_type = representation.strip()

        if isinstance(parsed.get("solids"), list):
            solids_list = parsed.get("solids")
        elif isinstance(parsed.get("items"), list):
            solids_list = parsed.get("items")
        elif isinstance(parsed.get("elements"), list):
            solids_list = parsed.get("elements")
        else:
            return solids
    elif isinstance(parsed, list):
        solids_list = parsed
    else:
        return solids

    normalized_solids = []
    for solid in solids_list:
        if not isinstance(solid, dict):
            continue
        solid_copy = dict(solid)
        solid_copy["Type"] = _guess_type_value(solid_copy, top_level_type)

        if "type" in solid_copy:
            # Some prompts emit lowercase `type`; treat geometry-like values as
            # dimension shape hints and semantic values as `Role`.
            raw = solid_copy.get("type")
            raw_str = str(raw).strip() if raw is not None else ""
            if raw_str:
                if _looks_like_geometry(raw_str):
                    dimensions = solid_copy.get("dimensions")
                    if not isinstance(dimensions, dict):
                        dimensions = {}
                    if not any(
                        key in dimensions
                        for key in ["shape", "Shape", "geometry", "Geometry"]
                    ):
                        dimensions["shape"] = raw_str
                    solid_copy["dimensions"] = dimensions
                elif "Role" not in solid_copy:
                    solid_copy["Role"] = raw_str
            solid_copy.pop("type", None)

        if "role" in solid_copy:
            if "Role" not in solid_copy:
                solid_copy["Role"] = solid_copy.get("role")
            solid_copy.pop("role", None)

        operations = solid_copy.get("operations")
        if isinstance(operations, list):
            cleaned_ops = []
            for operation in operations:
                if isinstance(operation, str):
                    cleaned_ops.append(_clean_25d_wording(operation))
                else:
                    cleaned_ops.append(operation)
            solid_copy["operations"] = cleaned_ops
        else:
            solid_copy["operations"] = []

        notes = solid_copy.get("notes")
        if isinstance(notes, str):
            solid_copy["notes"] = _clean_25d_wording(notes)

        normalized_solids.append(_order_solid_keys(solid_copy))

    name_index = {}
    for solid in normalized_solids:
        name = solid.get("name")
        if isinstance(name, str) and name.strip():
            key = _canonical_name(name)
            if key and key not in name_index:
                name_index[key] = name

    injected: List[dict] = []
    for solid in normalized_solids:
        operations = solid.get("operations", [])
        if not isinstance(operations, list):
            operations = []
        solid_name = solid.get("name")
        note_lines: List[str] = []
        notes = solid.get("notes")
        if isinstance(notes, str):
            note_lines = [
                line.strip() for line in notes.splitlines() if line.strip()
            ]

        for operation in [*operations, *note_lines]:
            if not isinstance(operation, str):
                continue
            for ref in _extract_referenced_names(operation):
                ref_key = _canonical_name(ref)
                if not ref_key or ref_key in name_index:
                    continue

                # Auto-add missing boolean tools so downstream generators do not
                # fail on unresolved subtraction references.
                placeholder_type = _infer_placeholder_type(ref, operation)
                dimensions = {}
                if placeholder_type == "2.5D":
                    z_range = _extract_z_range(solid.get("dimensions")) or [
                        "ts",
                        "ts+tp",
                    ]
                    dimensions = {
                        "shape": "Extrude (from closed planar profile)",
                        "profile_plane": "z = ts",
                        "z_range": z_range,
                        "profile": {"kind": "spline", "closed": True},
                    }

                injected.append(
                    {
                        "Type": placeholder_type,
                        "name": ref,
                        "Role": "Boolean tool (auto-added)",
                        "material": "Vacuum",
                        "dimensions": dimensions,
                        "operations": [],
                        "notes": (
                            "Auto-added: referenced by boolean operation in "
                            f"'{solid_name}': {operation}"
                        ),
                    }
                )
                name_index[ref_key] = ref

    if injected:
        normalized_solids.extend(injected)

    return json.dumps({"solids": normalized_solids}, indent=2)


class SolidsGeneratorBase(LLMCaller):
    """Base class for solids generators that produce JSON artifacts."""

    def __init__(
        self,
        prompt_files: Sequence[str],
        model: str = DEFAULT_MODEL,
        save_dir: Optional[str] = None,
        reasoning_effort: Optional[str] = "high",
        enable_code_interpreter: bool = False,
    ):
        """Initialize shared prompt set, output directory, and optional tools."""
        super().__init__(
            default_model=model,
            reasoning_effort=reasoning_effort,
        )
        if enable_code_interpreter:
            self.set_default_tools(CODE_INTERPRETER_TOOLS)
            self.set_default_tool_choice(CODE_INTERPRETER_TOOL_CHOICE)
        self.prompt_files = list(prompt_files)
        self.save_dir = resolve_save_dir(save_dir)

    def save_solids(self, solids: str, filename: str) -> str:
        """Save generated solid specifications to a JSON file."""
        filepath = prepare_output_path(
            os.path.join(self.save_dir, ensure_json_filename(filename))
        )
        try:
            with open(filepath, "w", encoding="utf-8") as output_file:
                output_file.write(solids)
        except UnicodeEncodeError:
            sanitized = solids.encode("ascii", "ignore").decode("ascii")
            with open(filepath, "w", encoding="utf-8") as output_file:
                output_file.write(sanitized)
        return filepath

    def get_solids(
        self,
        description: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        additional_prompt_files: Optional[List[str]] = None,
        save_as: Optional[str] = "solids.json",
        pdf_paths: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Convert a description (and images) into solid specifications."""
        prompt_files = self.prompt_files + (additional_prompt_files or [])
        solids = self.call_llm(
            prompt_files=prompt_files,
            description=description,
            image_paths=image_paths,
            json_schema_hint=SOLIDS_SCHEMA_HINT,
            text_format=SOLIDS_RESPONSE_FORMAT,
            pdf_paths=pdf_paths,
        )
        if solids:
            solids = normalize_solids_payload(solids)

        if solids and save_as:
            self.save_solids(solids, save_as)

        return solids
