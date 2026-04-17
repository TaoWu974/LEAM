import json
import os
import re
from typing import Any, Optional


def ensure_json_filename(filename: str) -> str:
    """Ensure the given filename ends with .json."""
    if filename.lower().endswith(".json"):
        return filename
    stem = os.path.splitext(filename)[0]
    return f"{stem}.json"



def parse_json_maybe(text: Optional[str]) -> Optional[Any]:
    """
    Best-effort JSON parser for LLM outputs that may include code
    fences or a leading 'json' label.

    Returns the parsed Python object (dict/list/...), or None if no
    valid JSON can be extracted.
    """
    if not text or not isinstance(text, str):
        return None

    candidate = text.strip()
    if not candidate:
        return None

    # Common pattern: leading "json" line then the JSON payload.
    lines = candidate.splitlines()
    if lines and lines[0].strip().lower() == "json":
        candidate = "\n".join(lines[1:]).strip()

    # Fast path: direct JSON.
    try:
        return json.loads(candidate)
    except Exception:
        pass

    # Try fenced blocks (```json ...``` or ``` ... ```).
    for match in re.finditer(
        r"```(?:json)?\s*(.*?)```",
        candidate,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        fenced = match.group(1).strip()
        if not fenced:
            continue
        try:
            return json.loads(fenced)
        except Exception:
            continue

    # Last resort: scan for the first JSON object/array and decode
    # from there.
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(candidate):
        if ch not in "{[":
            continue
        try:
            obj, _ = decoder.raw_decode(candidate[idx:])
            return obj
        except Exception:
            continue

    return None
