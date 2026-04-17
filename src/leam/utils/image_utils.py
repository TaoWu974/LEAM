import base64
import mimetypes
from pathlib import Path
from typing import Dict, Iterable, List

from leam.core.errors import InputValidationError

MODEL_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
MAX_IMAGE_INPUT_BYTES = 20 * 1024 * 1024


def _resolve_mime_type(path: str) -> str:
    mime_type, _ = mimetypes.guess_type(path)
    if isinstance(mime_type, str) and mime_type.startswith("image/"):
        return mime_type
    return "image/jpeg"


def _validate_model_image(path: str) -> Path:
    candidate = Path(path)
    if candidate.suffix.lower() not in MODEL_IMAGE_EXTENSIONS:
        raise InputValidationError(
            "Only PNG and JPEG image inputs are supported. "
            f"Unsupported image: {candidate.name}"
        )
    if not candidate.is_file():
        raise InputValidationError(f"Image input not found: {candidate}")
    size = candidate.stat().st_size
    if size > MAX_IMAGE_INPUT_BYTES:
        raise InputValidationError(
            "Image inputs must be 20 MiB or smaller. "
            f"Oversized image: {candidate.name}"
        )
    return candidate


def _to_data_url(path: str) -> str:
    candidate = _validate_model_image(path)
    with open(candidate, "rb") as image_file:
        encoded_bytes = base64.b64encode(image_file.read())
    return (
        f"data:{_resolve_mime_type(str(candidate))};base64,"
        f"{encoded_bytes.decode('utf-8')}"
    )


def encode_images(paths: Iterable[str]) -> List[Dict]:
    """Convert images to Chat Completions image_url content blocks."""
    encoded: List[Dict] = []
    for path in paths:
        encoded.append(
            {
                "type": "image_url",
                "image_url": {"url": _to_data_url(path)},
            }
        )
    return encoded


def encode_images_for_responses(paths: Iterable[str]) -> List[Dict]:
    """Convert images to Responses API input_image content blocks."""
    encoded: List[Dict] = []
    for path in paths:
        encoded.append(
            {
                "type": "input_image",
                "image_url": _to_data_url(path),
                "detail": "auto",
            }
        )
    return encoded
