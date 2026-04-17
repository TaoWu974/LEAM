from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent


def prompt_path(filename: str) -> str:
    """Return the absolute path to a CST prompt file."""
    return str(BACKEND_ROOT / "prompts" / filename)


def resource_path(filename: str) -> str:
    """Return the absolute path to a CST resource file."""
    return str(BACKEND_ROOT / "resources" / filename)
