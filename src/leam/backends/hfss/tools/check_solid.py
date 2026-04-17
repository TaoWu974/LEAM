"""Validate HFSS solids.json against description, parameters, and materials."""

import json
import os
import re
from typing import Dict, List, Optional, Set

from leam.backends.hfss.paths import prompt_path
from leam.core.llm_caller import LLMCaller
from leam.utils.constants import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT
from leam.utils.file_io import prepare_output_path, resolve_save_dir
from leam.utils.json_utils import ensure_json_filename, parse_json_maybe

CHECK_SOLID_SCHEMA_HINT = (
    "Return JSON with shape: "
    '{ "issues": [ { "category": string, "severity": "error" or "warning", '
    '"solid": string|null, "path": string|null, '
    '"route_to": "parameters" or "materials" or "solids", '
    '"issue": string } ] }'
)
CHECK_SOLID_RESPONSE_FORMAT = {"type": "json_object"}
VALID_ROUTE_TARGETS = {"parameters", "materials", "solids"}
BUILTIN_MATERIALS = {
    "vacuum",
    "pec",
    "perfectelectricconductor",
}
IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
IGNORED_PARAMETER_TOKENS = {
    "x",
    "y",
    "z",
    "xy",
    "yz",
    "xz",
    "mm",
    "ghz",
    "hz",
    "axis",
    "shape",
    "primitive",
    "brick",
    "cylinder",
    "circle",
    "cone",
    "sphere",
    "torus",
    "prism",
    "polygon",
    "spline",
    "curve",
    "rectangle",
    "ellipse",
    "elliptical",
    "extrude",
    "rotate",
    "revolve",
    "profile",
    "plane",
    "origin",
    "component",
    "vacuum",
    "copper",
    "pec",
    "substrate",
    "patch",
    "ground",
    "feed",
    "cutout",
    "dielectric",
    "radiating",
    "feeding",
    "true",
    "false",
    "and",
    "or",
    "from",
    "to",
    "by",
    "sin",
    "cos",
    "tan",
    "abs",
    "sqr",
    "exp",
    "log",
    "int",
    "fix",
    "round",
    "sgn",
}


def _canonical_name(value: str) -> str:
    """Normalize a solid name for case-insensitive matching."""
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _material_key(value: str) -> str:
    """Normalize a material token for comparisons."""
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _base_material_name(value: str) -> str:
    """Return a material name without the .mtd suffix."""
    token = str(value or "").strip().strip('"\'`')
    if token.lower().endswith(".mtd"):
        token = token[:-4]
    return token.strip()


def _extract_solids_list(payload: object) -> Optional[List[dict]]:
    """Extract a solids list from supported JSON envelope shapes."""
    if isinstance(payload, dict):
        for key in ("solids", "items", "elements"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return None
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return None


def _extract_parameter_names(payload: object) -> Set[str]:
    """Load known parameter identifiers from parameters JSON."""
    names: Set[str] = set()
    if not isinstance(payload, dict):
        return names
    items = payload.get("items")
    if not isinstance(items, list):
        return names
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            names.add(name)
            if name.startswith("$") and len(name) > 1:
                names.add(name[1:])
    return names


def _extract_material_names(payload: object) -> Set[str]:
    """Load known material names from materials JSON."""
    names: Set[str] = set()
    if not isinstance(payload, dict):
        return names
    items = payload.get("items")
    if not isinstance(items, list):
        return names
    for item in items:
        if not isinstance(item, dict):
            continue
        for candidate in (
            item.get("name"),
            _base_material_name(item.get("file") or ""),
        ):
            value = str(candidate or "").strip()
            if value:
                names.add(_material_key(value))
    return names


def _extract_operation_targets(operation: str) -> List[str]:
    """Extract likely referenced solid names from boolean-like operations."""
    text = str(operation or "").strip()
    if not text:
        return []

    match = re.search(
        r"\b(?:subtract|minus|union|unite|intersect)\b\s*(?::|->|with)?\s*(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return []

    candidate = match.group(1).strip().strip('"\'`')
    candidate = re.split(
        r"\bfrom\b",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    parts = re.split(
        r"\s*(?:,|;|\band\b)\s*",
        candidate,
        flags=re.IGNORECASE,
    )
    refs: List[str] = []
    for part in parts:
        cleaned = re.sub(
            r"\s*\([^)]*\)\s*$",
            "",
            str(part or ""),
        ).strip().strip('"\'`')
        if cleaned:
            refs.append(cleaned)
    return refs


def _extract_parameter_tokens_from_string(value: str) -> Set[str]:
    """Best-effort extraction of parameter-like identifiers from dimension text."""
    text = str(value or "").strip()
    if not text:
        return set()

    compact = text.replace(" ", "")
    looks_expression_like = (
        any(ch.isdigit() for ch in compact)
        or any(ch in compact for ch in "+-*/^()[]")
        or compact.isidentifier()
    )
    if not looks_expression_like:
        return set()

    tokens: Set[str] = set()
    for token in IDENTIFIER_RE.findall(text):
        lower = token.lower()
        if lower in IGNORED_PARAMETER_TOKENS:
            continue
        if (
            compact == token
            and len(token) > 1
            and token[0].isupper()
            and token[1:].islower()
        ):
            continue
        tokens.add(token)
    return tokens


def _collect_parameter_tokens(value: object) -> Set[str]:
    """Recursively collect parameter-like identifiers from dimension payloads."""
    tokens: Set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            tokens.update(_collect_parameter_tokens(item))
        return tokens
    if isinstance(value, list):
        for item in value:
            tokens.update(_collect_parameter_tokens(item))
        return tokens
    if isinstance(value, str):
        return _extract_parameter_tokens_from_string(value)
    return tokens


class CheckSolid:
    """Run lightweight local and LLM-assisted checks over HFSS solids.json."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        save_dir: Optional[str] = None,
    ):
        """Initialize prompt set and output directory for HFSS solids checks."""
        self.llm_caller = LLMCaller(
            default_model=model,
            reasoning_effort=DEFAULT_REASONING_EFFORT,
        )
        self.prompt_file = prompt_path("check_solid_prompt.md")
        self.save_dir = resolve_save_dir(save_dir)

    @staticmethod
    def _load_json_file(path: str) -> object:
        """Load one JSON-like file using the repo's tolerant parser."""
        with open(path, "r", encoding="utf-8") as source:
            content = source.read()
        return parse_json_maybe(content)

    @staticmethod
    def _issue(
        category: str,
        issue: str,
        *,
        severity: str = "error",
        solid: Optional[str] = None,
        path: Optional[str] = None,
        route_to: Optional[str] = None,
    ) -> dict:
        """Create a normalized issue object."""
        normalized_route = str(route_to or "").strip().lower() or None
        if normalized_route not in VALID_ROUTE_TARGETS:
            normalized_route = None
        return {
            "category": category,
            "severity": severity,
            "solid": solid,
            "path": path,
            "route_to": normalized_route,
            "issue": issue,
        }

    def _run_local_checks(
        self,
        solids_file: str,
        parameters_file: str,
        materials_file: str,
    ) -> List[dict]:
        """Validate JSON structure and obvious cross-file inconsistencies locally."""
        issues: List[dict] = []
        payloads: Dict[str, object] = {}
        for label, path in {
            "solids": solids_file,
            "parameters": parameters_file,
            "materials": materials_file,
        }.items():
            if not path or not os.path.isfile(path):
                issues.append(
                    self._issue(
                        "json",
                        f"{label}.json file not found.",
                        path=path or label,
                    )
                )
                continue
            payload = self._load_json_file(path)
            if payload is None:
                issues.append(
                    self._issue(
                        "json",
                        f"{label}.json is not valid JSON.",
                        path=path,
                    )
                )
                continue
            payloads[label] = payload

        solids_list = _extract_solids_list(payloads.get("solids"))
        if solids_list is None:
            issues.append(
                self._issue(
                    "json",
                    "solids.json must contain a top-level solids list.",
                    path=solids_file,
                )
            )
            return issues

        parameter_names = _extract_parameter_names(payloads.get("parameters"))
        material_names = _extract_material_names(payloads.get("materials"))
        known_solids: Dict[str, str] = {}

        for index, solid in enumerate(solids_list):
            solid_name = str(solid.get("name") or "").strip()
            path_prefix = f"solids[{index}]"
            if not solid_name:
                issues.append(
                    self._issue(
                        "json",
                        "Solid is missing a non-empty name.",
                        path=f"{path_prefix}.name",
                    )
                )
                continue
            key = _canonical_name(solid_name)
            if key in known_solids:
                issues.append(
                    self._issue(
                        "json",
                        f"Duplicate solid name '{solid_name}'.",
                        solid=solid_name,
                        path=f"{path_prefix}.name",
                    )
                )
            else:
                known_solids[key] = solid_name

        required_keys = [
            "Type",
            "name",
            "Role",
            "material",
            "dimensions",
            "operations",
            "notes",
        ]
        for index, solid in enumerate(solids_list):
            solid_name = str(solid.get("name") or f"solid_{index}").strip()
            if not solid_name:
                solid_name = f"solid_{index}"
            path_prefix = f"solids[{index}]"
            for key in required_keys:
                if key not in solid:
                    issues.append(
                        self._issue(
                            "json",
                            f"Missing required key '{key}'.",
                            solid=solid_name,
                            path=f"{path_prefix}.{key}",
                        )
                    )

            solid_type = str(solid.get("Type") or "").strip()
            if solid_type not in {"3D", "2.5D"}:
                issues.append(
                    self._issue(
                        "json",
                        'Type must be exactly "3D" or "2.5D".',
                        solid=solid_name,
                        path=f"{path_prefix}.Type",
                    )
                )

            dimensions = solid.get("dimensions")
            if not isinstance(dimensions, dict):
                issues.append(
                    self._issue(
                        "json",
                        "dimensions must be an object.",
                        solid=solid_name,
                        path=f"{path_prefix}.dimensions",
                    )
                )
                dimensions = {}

            operations = solid.get("operations")
            if not isinstance(operations, list):
                issues.append(
                    self._issue(
                        "json",
                        "operations must be an array of strings.",
                        solid=solid_name,
                        path=f"{path_prefix}.operations",
                    )
                )
                operations = []

            material = str(solid.get("material") or "").strip()
            material_key = _material_key(_base_material_name(material))
            if not material:
                issues.append(
                    self._issue(
                        "materials",
                        "Solid is missing a material assignment.",
                        solid=solid_name,
                        path=f"{path_prefix}.material",
                    )
                )
            elif (
                material_key not in BUILTIN_MATERIALS
                and material_key not in material_names
            ):
                issues.append(
                    self._issue(
                        "materials",
                        f"Material '{material}' is not present in materials.json.",
                        solid=solid_name,
                        path=f"{path_prefix}.material",
                    )
                )

            undefined_parameters = sorted(
                token
                for token in _collect_parameter_tokens(dimensions)
                if token not in parameter_names
            )
            if undefined_parameters:
                issues.append(
                    self._issue(
                        "parameters",
                        "Undefined parameter references: "
                        + ", ".join(undefined_parameters),
                        solid=solid_name,
                        path=f"{path_prefix}.dimensions",
                    )
                )

            for op_index, operation in enumerate(operations):
                if not isinstance(operation, str):
                    issues.append(
                        self._issue(
                            "operations",
                            "Operation entries must be strings.",
                            solid=solid_name,
                            path=f"{path_prefix}.operations[{op_index}]",
                        )
                    )
                    continue
                for target in _extract_operation_targets(operation):
                    if _canonical_name(target) not in known_solids:
                        issues.append(
                            self._issue(
                                "operations",
                                f"Operation references unknown solid '{target}'.",
                                solid=solid_name,
                                path=f"{path_prefix}.operations[{op_index}]",
                            )
                        )

        return issues

    def _run_llm_alignment_check(
        self,
        description: Optional[str],
        image_paths: Optional[List[str]],
        solids_file: str,
        parameters_file: str,
        materials_file: str,
        pdf_paths: Optional[List[str]] = None,
    ) -> List[dict]:
        """Ask the model for semantic mismatches against the provided context."""
        if not description and not image_paths:
            return []
        for path in (solids_file, parameters_file, materials_file):
            if not path or not os.path.isfile(path):
                return []

        try:
            response = self.llm_caller.call_llm(
                prompt_files=[
                    self.prompt_file,
                    solids_file,
                    parameters_file,
                    materials_file,
                ],
                description=description,
                image_paths=image_paths,
                json_schema_hint=CHECK_SOLID_SCHEMA_HINT,
                text_format=CHECK_SOLID_RESPONSE_FORMAT,
                pdf_paths=pdf_paths,
            )
            parsed = parse_json_maybe(response)
        except Exception as exc:
            return [
                self._issue(
                    "alignment",
                    f"LLM alignment check failed: {exc}",
                    severity="warning",
                )
            ]

        if not isinstance(parsed, dict):
            return [
                self._issue(
                    "alignment",
                    "LLM alignment check returned invalid JSON.",
                    severity="warning",
                )
            ]

        issues: List[dict] = []
        for item in parsed.get("issues", []) or []:
            if not isinstance(item, dict):
                continue
            issues.append(
                self._issue(
                    str(item.get("category") or "alignment").strip()
                    or "alignment",
                    str(
                        item.get("issue")
                        or "Solid list does not match the provided context."
                    ).strip(),
                    severity=str(item.get("severity") or "error").strip()
                    or "error",
                    solid=(
                        str(item.get("solid")).strip()
                        if item.get("solid") is not None
                        else None
                    ),
                    path=(
                        str(item.get("path")).strip()
                        if item.get("path") is not None
                        else None
                    ),
                    route_to=item.get("route_to"),
                )
            )
        return issues

    @staticmethod
    def _dedupe_issues(issues: List[dict]) -> List[dict]:
        """Remove exact duplicate issues while preserving order."""
        deduped: List[dict] = []
        seen = set()
        for issue in issues:
            key = (
                issue.get("category"),
                issue.get("severity"),
                issue.get("solid"),
                issue.get("path"),
                issue.get("issue"),
            )
            if key in seen:
                continue
            deduped.append(issue)
            seen.add(key)
        return deduped

    def save_report(self, result: dict, save_as: str) -> str:
        """Persist one solids-check report JSON artifact."""
        path = prepare_output_path(
            os.path.join(self.save_dir, ensure_json_filename(save_as))
        )
        with open(path, "w", encoding="utf-8") as output_file:
            json.dump(result, output_file, indent=2)
            output_file.write("\n")
        return path

    def check(
        self,
        *,
        description: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        solids_file: str = "solids.json",
        parameters_file: str = "parameters.json",
        materials_file: str = "materials.json",
        save_as: Optional[str] = None,
        use_local_checks: bool = False,
        use_llm_checks: bool = True,
        pdf_paths: Optional[List[str]] = None,
    ) -> dict:
        """Return a lightweight report for the current solids payload."""
        local_issues = (
            self._run_local_checks(
                solids_file=solids_file,
                parameters_file=parameters_file,
                materials_file=materials_file,
            )
            if use_local_checks
            else []
        )
        llm_issues = (
            self._run_llm_alignment_check(
                description=description,
                image_paths=image_paths,
                solids_file=solids_file,
                parameters_file=parameters_file,
                materials_file=materials_file,
                pdf_paths=pdf_paths,
            )
            if use_llm_checks
            else []
        )
        issues = self._dedupe_issues(local_issues + llm_issues)
        result = {
            "status": (
                "ok"
                if not any(issue.get("severity") != "warning" for issue in issues)
                else "issues"
            ),
            "issues": issues,
            "issue_counts": {
                "total": len(issues),
                "errors": sum(
                    1 for issue in issues if issue.get("severity") != "warning"
                ),
                "warnings": sum(
                    1 for issue in issues if issue.get("severity") == "warning"
                ),
            },
            "paths": {
                "solids": solids_file,
                "parameters": parameters_file,
                "materials": materials_file,
            },
        }
        if save_as:
            result["report_file"] = self.save_report(result, save_as)
        return result
