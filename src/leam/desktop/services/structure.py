"""Structured preview helpers for desktop workflow artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class SolidPreviewItem:
    """One solid entry rendered in the Structure tab."""

    name: str
    solid_type: str
    role: str
    material: str
    dimensions_text: str
    operations_text: str
    notes: str


@dataclass
class StructurePreview:
    """Structured read-only preview model for one step artifact."""

    kind: str
    summary: str
    source_path: str
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    solids: List[SolidPreviewItem] = field(default_factory=list)
    message: str = ""


def load_parameters_preview(path: str) -> StructurePreview:
    payload = _load_json(path)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append(
            [
                str(item.get("name") or ""),
                str(item.get("value") or ""),
                str(item.get("notes") or ""),
            ]
        )
    return StructurePreview(
        kind="parameters",
        summary=_count_summary(len(rows), "parameter"),
        source_path=path,
        headers=["Name", "Value", "Notes"],
        rows=rows,
    )


def load_materials_preview(path: str) -> StructurePreview:
    payload = _load_json(path)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    rows = []
    use_resolved_headers = False
    for item in items:
        if not isinstance(item, dict):
            continue
        if any(
            key in item for key in ("source", "builtin", "notes")
        ) and not item.get("file"):
            builtin_value = item.get("builtin")
            use_resolved_headers = True
            rows.append(
                [
                    str(item.get("name") or ""),
                    str(item.get("source") or ""),
                    "" if builtin_value is None else str(builtin_value),
                    str(item.get("notes") or ""),
                ]
            )
        else:
            rows.append(
                [
                    str(item.get("name") or ""),
                    str(item.get("file") or ""),
                ]
            )
    return StructurePreview(
        kind="materials",
        summary=_count_summary(len(rows), "material"),
        source_path=path,
        headers=(
            ["Name", "Source", "Builtin", "Notes"]
            if use_resolved_headers
            else ["Name", "File"]
        ),
        rows=rows,
    )


def load_solids_preview(path: str) -> StructurePreview:
    payload = _load_json(path)
    items = payload.get("solids", []) if isinstance(payload, dict) else []
    solids: List[SolidPreviewItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        operations = item.get("operations")
        operation_lines = []
        if isinstance(operations, list):
            operation_lines = [str(value) for value in operations]
        dimensions_text = _format_nested_value(item.get("dimensions"), 0)
        solids.append(
            SolidPreviewItem(
                name=str(item.get("name") or ""),
                solid_type=str(item.get("Type") or ""),
                role=str(item.get("Role") or ""),
                material=str(item.get("material") or ""),
                dimensions_text=dimensions_text or "-",
                operations_text="\n".join(operation_lines) if operation_lines else "-",
                notes=str(item.get("notes") or ""),
            )
        )
    return StructurePreview(
        kind="solids",
        summary=_count_summary(len(solids), "solid"),
        source_path=path,
        solids=solids,
    )


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as source:
        return json.load(source)


def _count_summary(count: int, noun: str) -> str:
    suffix = "" if count == 1 else "s"
    return f"{count} {noun}{suffix}"


def _format_nested_value(value: Any, indent: int) -> str:
    prefix = "  " * indent
    if isinstance(value, dict):
        lines = []
        for key, nested in value.items():
            if isinstance(nested, (dict, list)):
                nested_text = _format_nested_value(nested, indent + 1)
                lines.append(f"{prefix}{key}:")
                lines.append(nested_text)
            else:
                lines.append(f"{prefix}{key}: {nested}")
        return "\n".join(line for line in lines if line)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(_format_nested_value(item, indent + 1))
            else:
                lines.append(f"{prefix}- {item}")
        return "\n".join(lines)
    if value is None:
        return ""
    return f"{prefix}{value}"
