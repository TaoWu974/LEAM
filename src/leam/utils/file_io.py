import os
from pathlib import Path
from typing import Iterable, Optional

from leam.core.errors import InputValidationError

from .constants import DEFAULT_OUTPUT_DIR_NAME

PROMPT_TEXT_EXTENSIONS = {
    ".bas",
    ".cfg",
    ".conf",
    ".csv",
    ".html",
    ".ini",
    ".json",
    ".log",
    ".md",
    ".py",
    ".rst",
    ".text",
    ".toml",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}
MAX_PROMPT_TEXT_FILE_BYTES = 1024 * 1024
MAX_PROMPT_TEXT_PROBE_BYTES = 4096
_TEXT_CONTROL_BYTES = {9, 10, 12, 13}


def _safe_prompt_file_label(path: str) -> str:
    return Path(path).name or "attachment"


def _looks_like_text_bytes(sample: bytes) -> bool:
    if not sample:
        return True
    if b"\x00" in sample:
        return False
    non_text_controls = sum(
        1
        for byte in sample
        if byte < 32 and byte not in _TEXT_CONTROL_BYTES
    )
    return non_text_controls / max(len(sample), 1) <= 0.05


def _validate_prompt_text_file(path: str) -> None:
    candidate = Path(path)
    if not candidate.is_file():
        raise InputValidationError(f"Prompt attachment not found: {candidate}")
    size = candidate.stat().st_size
    if size > MAX_PROMPT_TEXT_FILE_BYTES:
        raise InputValidationError(
            "Prompt text attachments must be 1 MiB or smaller. "
            f"Oversized file: {candidate.name}"
        )
    with open(candidate, "rb") as source:
        if not _looks_like_text_bytes(source.read(MAX_PROMPT_TEXT_PROBE_BYTES)):
            raise InputValidationError(
                "Prompt attachments must be readable text files. "
                f"Unsupported file: {candidate.name}"
            )


def is_prompt_text_file(path: str) -> bool:
    try:
        _validate_prompt_text_file(path)
    except InputValidationError:
        return False
    return True


def read_prompt_text_file(path: str) -> str:
    _validate_prompt_text_file(path)
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return Path(path).read_text(encoding="utf-8", errors="replace")


def process_text_files(files: Iterable[str]) -> str:
    """Combine multiple text files into a single string."""
    contents = []
    for path in files:
        contents.append(
            f"{_safe_prompt_file_label(path)}:\n{read_prompt_text_file(path)}"
        )
    return "\n\n".join(contents)



def prepare_output_path(path: str) -> str:
    """Ensure the parent directory for one output file exists."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return str(target)


def resolve_save_dir(save_dir: Optional[str] = None) -> str:
    """Resolve the directory used for generated outputs without creating it eagerly."""
    return save_dir or os.path.join(os.getcwd(), DEFAULT_OUTPUT_DIR_NAME)
