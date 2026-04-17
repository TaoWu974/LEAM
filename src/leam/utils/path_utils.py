"""Helpers for predictable filesystem path normalization."""

from __future__ import annotations

import os
from pathlib import Path


def absolute_path_text(path_value: str | os.PathLike[str]) -> str:
    """Return an absolute path while preserving the caller's path spelling."""

    candidate = Path(path_value).expanduser()
    return os.path.abspath(str(candidate))


def _windows_long_path_text(path_text: str) -> str:
    try:
        import ctypes
    except Exception:
        return path_text

    kernel32 = getattr(ctypes, "windll", None)
    if kernel32 is None:
        return path_text

    get_long_path_name = getattr(kernel32.kernel32, "GetLongPathNameW", None)
    if get_long_path_name is None:
        return path_text

    candidate = Path(path_text)
    suffix_parts: list[str] = []
    existing = candidate

    while not existing.exists():
        parent = existing.parent
        if parent == existing:
            return path_text
        suffix_parts.append(existing.name)
        existing = parent

    existing_text = str(existing)
    required = get_long_path_name(existing_text, None, 0)
    if not required:
        return path_text

    buffer = ctypes.create_unicode_buffer(required)
    written = get_long_path_name(existing_text, buffer, required)
    if not written:
        return path_text

    long_text = buffer.value
    for part in reversed(suffix_parts):
        long_text = os.path.join(long_text, part)
    return long_text


def canonical_path_text(path_value: str | os.PathLike[str]) -> str:
    """Return a stable absolute path for runtime use.

    On Windows this expands existing 8.3 short names such as ``RUNNER~1`` into
    their long-form path segments, while keeping non-existent tail segments.
    """

    path_text = absolute_path_text(path_value)
    if os.name == "nt":
        return _windows_long_path_text(path_text)
    return path_text
