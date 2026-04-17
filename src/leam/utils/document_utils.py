import base64
from pathlib import Path
from typing import Dict, Iterable, List

from leam.core.errors import InputValidationError

PDF_INPUT_EXTENSIONS = {".pdf"}
MAX_PDF_INPUT_BYTES = 10 * 1024 * 1024


def _validate_pdf_input(path: str) -> Path:
    candidate = Path(path)
    if candidate.suffix.lower() not in PDF_INPUT_EXTENSIONS:
        raise InputValidationError(
            f"Only PDF document inputs are supported. Unsupported file: {candidate.name}"
        )
    if not candidate.is_file():
        raise InputValidationError(f"PDF input not found: {candidate}")
    size = candidate.stat().st_size
    if size > MAX_PDF_INPUT_BYTES:
        raise InputValidationError(
            "PDF inputs must be 10 MiB or smaller. "
            f"Oversized file: {candidate.name}"
        )
    return candidate


def encode_pdfs_for_responses(paths: Iterable[str]) -> List[Dict]:
    """Convert PDFs to Responses API input_file content blocks."""
    encoded: List[Dict] = []
    for path in paths:
        candidate = _validate_pdf_input(path)
        with open(candidate, "rb") as input_file:
            encoded.append(
                {
                    "type": "input_file",
                    "filename": candidate.name,
                    "file_data": base64.b64encode(input_file.read()).decode("utf-8"),
                }
            )
    return encoded
