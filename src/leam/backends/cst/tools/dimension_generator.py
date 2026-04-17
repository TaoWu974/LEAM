"""Dimension extraction and normalization for CST modeling flows."""

import json
import os
from typing import List, Optional

from leam.backends.cst.paths import prompt_path
from leam.core.llm_caller import LLMCaller
from leam.utils.constants import DEFAULT_MODEL
from leam.utils.file_io import prepare_output_path, resolve_save_dir
from leam.utils.json_utils import ensure_json_filename, parse_json_maybe

DIMENSION_SCHEMA_HINT = (
    "Return JSON with shape: "
    '{ "solids": [ { "Type": "3D" or "2.5D", "name": string, '
    '"reference": string, '
    '"coordinates": {"x": number, "y": number, "z": number}, '
    '"dimensions": object, "notes": string } ] }'
)


def _normalize_type_value(value: Optional[str]) -> Optional[str]:
    """Normalize free-form type labels into canonical `3D` / `2.5D`."""
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


def _has_25d_hint(solid: dict) -> bool:
    """Infer whether a solid likely belongs to 2.5D workflow."""
    dims = solid.get("dimensions", {})
    shape = ""
    if isinstance(dims, dict):
        shape = str(dims.get("shape", "") or dims.get("Shape", ""))
    reference = str(solid.get("reference", "") or solid.get("Reference", ""))
    name = str(solid.get("name", "") or solid.get("Name", ""))
    notes = str(solid.get("notes", "") or solid.get("Notes", ""))
    hint = f"{name} {shape} {reference} {notes}".lower()
    return any(
        key in hint
        for key in [
            "extrude",
            "rotate",
            "spline",
            "polygon",
            "curve",
            "profile",
        ]
    )


def _guess_type_value(solid: dict, fallback: Optional[str]) -> str:
    """Pick the best type value using explicit, inferred, and fallback hints."""
    explicit = _normalize_type_value(solid.get("Type"))
    if explicit in {"3D", "2.5D"}:
        return explicit

    if _has_25d_hint(solid):
        return "2.5D"

    inferred = _normalize_type_value(fallback)
    if inferred in {"3D", "2.5D"}:
        return inferred

    return "3D"


def _order_solid_keys(solid: dict) -> dict:
    """Ensure stable key order to keep JSON outputs deterministic."""
    ordered = {"Type": solid.get("Type")}
    for key in ["name", "reference", "coordinates", "dimensions", "notes"]:
        if key in solid:
            ordered[key] = solid[key]
    for key, value in solid.items():
        if key in ordered:
            continue
        ordered[key] = value
    return ordered


def normalize_dimension_payload(payload: str) -> str:
    """Normalize LLM dimension payload into canonical `{solids:[...]}` shape."""
    parsed = parse_json_maybe(payload)
    if parsed is None:
        return payload

    solids_list = None
    top_level_type: Optional[str] = None

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
    elif isinstance(parsed, list):
        solids_list = parsed

    if not isinstance(solids_list, list):
        return payload

    normalized_solids = []
    for solid in solids_list:
        if not isinstance(solid, dict):
            continue
        # Copy and normalize each element to avoid mutating parsed objects.
        solid_copy = dict(solid)
        solid_copy["Type"] = _guess_type_value(solid_copy, top_level_type)
        normalized_solids.append(_order_solid_keys(solid_copy))

    return json.dumps({"solids": normalized_solids}, indent=2)



class DimensionGenerator(LLMCaller):
    """Generate coordinate-based dimensions from descriptions."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        save_dir: Optional[str] = None,
    ):
        """Initialize dimension prompt set and output directory."""
        super().__init__(default_model=model, reasoning_effort="high")
        self.prompt_files = [prompt_path("dimension_prompt.md")]
        self.save_dir = resolve_save_dir(save_dir)

    def generate_dimensions(
        self,
        description: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        additional_prompt_files: Optional[List[str]] = None,
        save_as: str = "dimensions.json",
        pdf_paths: Optional[List[str]] = None,
    ) -> str:
        """Generate, normalize, and persist dimensions as JSON."""
        prompt_files = self.prompt_files + (additional_prompt_files or [])
        result = self.call_llm(
            prompt_files=prompt_files,
            description=description,
            image_paths=image_paths,
            json_schema_hint=DIMENSION_SCHEMA_HINT,
            pdf_paths=pdf_paths,
        )

        result = normalize_dimension_payload(result)

        save_path = prepare_output_path(
            os.path.join(self.save_dir, ensure_json_filename(save_as))
        )
        with open(save_path, "w", encoding="utf-8") as output_file:
            output_file.write(result)

        return result
