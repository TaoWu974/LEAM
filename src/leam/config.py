import importlib
import json
import os
import re
import sys
from argparse import ArgumentParser
from importlib import resources as importlib_resources
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

from .utils.module_utils import optional_module_available
from .utils.path_utils import canonical_path_text

CONFIG_FILE = "config.json"
ENV_CST_PATH = "CST_PATH"
ENV_HFSS_PATH = "HFSS_PATH"
ENV_LEAM_CONFIG = "LEAM_CONFIG"
ENV_ALLOW_UNSAFE_EXECUTION = "LEAM_ALLOW_UNSAFE_EXECUTION"
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_OPENAI_TIMEOUT_SECONDS = "OPENAI_TIMEOUT_SECONDS"
RECOMMENDED_DESKTOP_INSTALL_COMMAND = "pip install leam"
_USER_CONFIG_DIRNAME = ".leam"
_CST_INSTALL_ROOTS = (
    Path(r"C:\Program Files (x86)"),
    Path(r"C:\Program Files"),
)
_HFSS_INSTALL_ROOT = Path(r"C:\Program Files\ANSYS Inc")
_CST_VERSION_RE = re.compile(r"(20\d{2})")
_HFSS_VERSION_RE = re.compile(r"[\\/]+v(\d{3})(?:[\\/]|$)", re.IGNORECASE)
_HFSS_LEGACY_VERSION_RE = re.compile(r"AnsysEM(\d{2})\.(\d)", re.IGNORECASE)
_ANSYSEM_ENV_RE = re.compile(r"ANSYSEM_ROOT(\d{3})$", re.IGNORECASE)
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_CONFIG_EXAMPLE_RESOURCE = ("resources", "config.example.json")


def _normalize_path_text(path_value: str) -> str:
    return canonical_path_text(path_value)


def _coerce_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return default


def _user_config_path() -> Path:
    configured_path = os.environ.get(ENV_LEAM_CONFIG)
    if configured_path:
        return Path(configured_path).expanduser()
    return Path.home() / _USER_CONFIG_DIRNAME / CONFIG_FILE


def _config_search_paths(config_file: str = CONFIG_FILE) -> Iterable[Path]:
    if config_file != CONFIG_FILE:
        yield Path(config_file).expanduser()
        return

    yield _user_config_path()


def _read_config_file(path: Path) -> Optional[Dict]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else {}


def _write_user_config(config: Dict) -> Path:
    target = _user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as output_file:
        json.dump(config, output_file, indent=2)
        output_file.write("\n")
    return target


def load_config(config_file: str = CONFIG_FILE) -> Dict:
    """Load configuration from the explicit LEAM config path or user config."""
    for path in _config_search_paths(config_file):
        payload = _read_config_file(path)
        if payload is not None:
            return payload
    return {}


def _normalize_cst_root(path_value: Optional[str]) -> Optional[str]:
    if not path_value:
        return None

    candidate = Path(_normalize_path_text(path_value))
    candidates = [candidate]
    if candidate.name.lower() == "python_cst_libraries":
        candidates.append(candidate.parent.parent)
    if candidate.name.upper() == "AMD64":
        candidates.append(candidate.parent)

    for root in candidates:
        libs_path = root / "AMD64" / "python_cst_libraries"
        if root.is_dir() and libs_path.is_dir():
            return canonical_path_text(root)
    return None


def _cst_version_key(path_value: str) -> int:
    match = _CST_VERSION_RE.search(str(path_value))
    return int(match.group(1)) if match else 0


def _iter_cst_install_roots() -> Iterable[str]:
    for base_dir in _CST_INSTALL_ROOTS:
        if not base_dir.is_dir():
            continue
        for child in base_dir.glob("CST Studio Suite *"):
            if child.is_dir():
                yield str(child)


def _resolve_configured_cst_path(config: Dict) -> Optional[str]:
    for value in (
        config.get("cst_path"),
        os.environ.get(ENV_CST_PATH),
    ):
        if value:
            normalized = _normalize_cst_root(str(value))
            return normalized or _normalize_path_text(str(value))
    return None


def _detect_latest_cst_install(config: Optional[Dict] = None) -> Optional[Dict[str, str]]:
    candidates = {}
    config = config or {}
    for raw_path in (
        config.get("cst_path"),
        os.environ.get(ENV_CST_PATH),
    ):
        normalized = _normalize_cst_root(str(raw_path)) if raw_path else None
        if normalized:
            candidates[normalized] = _cst_version_key(normalized)

    for raw_path in _iter_cst_install_roots():
        normalized = _normalize_cst_root(raw_path)
        if normalized:
            candidates[normalized] = _cst_version_key(normalized)

    if not candidates:
        return None

    selected = max(
        candidates.items(),
        key=lambda item: (item[1], item[0].casefold()),
    )[0]
    return {
        "path": selected,
        "python_libraries_path": get_python_libs_path(selected),
    }


def resolve_cst_path(config: Dict) -> Optional[str]:
    """Resolve the explicit CST installation root from config or env."""
    return _resolve_configured_cst_path(config)


def resolve_cst_python_libraries_path(config: Dict) -> Optional[str]:
    """Derive the CST Python library directory from the configured CST install."""
    cst_path = resolve_cst_path(config)
    if not cst_path:
        return None
    libraries_path = get_python_libs_path(cst_path)
    return libraries_path if os.path.isdir(libraries_path) else None


def _normalize_hfss_root(path_value: Optional[str]) -> Optional[str]:
    if not path_value:
        return None

    candidate = Path(_normalize_path_text(path_value))
    if candidate.is_file():
        candidate = candidate.parent

    for root in (candidate, *list(candidate.parents)[:4]):
        if (root / "syslib").is_dir():
            return canonical_path_text(root)
        child_root = root / "AnsysEM"
        if child_root.is_dir() and (child_root / "syslib").is_dir():
            return canonical_path_text(child_root)
    return None


def _hfss_version_key(path_value: str, env_name: Optional[str] = None) -> int:
    text = str(path_value)
    match = _HFSS_VERSION_RE.search(text)
    if match:
        return int(match.group(1))

    match = _HFSS_LEGACY_VERSION_RE.search(text)
    if match:
        return int(f"{match.group(1)}{match.group(2)}")

    if env_name:
        match = _ANSYSEM_ENV_RE.match(str(env_name))
        if match:
            return int(match.group(1))
    return 0


def _iter_hfss_env_candidates() -> Iterable[Tuple[str, Optional[str]]]:
    configured = os.environ.get(ENV_HFSS_PATH)
    if configured:
        yield configured, None

    for name, value in os.environ.items():
        if value and _ANSYSEM_ENV_RE.match(name):
            yield value, name


def _iter_hfss_install_roots() -> Iterable[Tuple[str, Optional[str]]]:
    if not _HFSS_INSTALL_ROOT.is_dir():
        return
    for child in _HFSS_INSTALL_ROOT.glob("v*/AnsysEM"):
        if child.is_dir():
            yield str(child), None


def _detect_latest_hfss_install(config: Optional[Dict] = None) -> Optional[Dict[str, str]]:
    candidates = {}
    config = config or {}
    for raw_path, env_name in (
        [(config.get("hfss_path"), None)] if config.get("hfss_path") else []
    ):
        normalized = _normalize_hfss_root(str(raw_path))
        if normalized:
            candidates[normalized] = _hfss_version_key(normalized, env_name=env_name)

    for raw_path, env_name in _iter_hfss_env_candidates():
        normalized = _normalize_hfss_root(raw_path)
        if normalized:
            candidates[normalized] = _hfss_version_key(normalized, env_name=env_name)

    for raw_path, env_name in _iter_hfss_install_roots():
        normalized = _normalize_hfss_root(raw_path)
        if normalized:
            candidates[normalized] = _hfss_version_key(normalized, env_name=env_name)

    if not candidates:
        return None

    selected = max(
        candidates.items(),
        key=lambda item: (item[1], item[0].casefold()),
    )[0]
    return {"path": selected}


def resolve_hfss_path(config: Dict) -> Optional[str]:
    """Resolve the explicit HFSS path from config or env."""
    configured = config.get("hfss_path") or os.environ.get(ENV_HFSS_PATH)
    if configured:
        normalized = _normalize_hfss_root(str(configured))
        return normalized or _normalize_path_text(str(configured))

    return None


def resolve_openai_api_key(config: Dict) -> Optional[str]:
    """Resolve OpenAI API key from the environment only."""
    del config
    api_key = os.environ.get(ENV_OPENAI_API_KEY)
    if api_key is None:
        return None
    api_key = str(api_key).strip()
    return api_key or None


def resolve_allow_unsafe_execution(
    config: Dict,
    default: bool = False,
) -> bool:
    """Resolve whether generated simulator code execution is explicitly enabled."""
    env_value = os.environ.get(ENV_ALLOW_UNSAFE_EXECUTION)
    if env_value not in (None, ""):
        return _coerce_bool(env_value, default=default)
    return _coerce_bool(config.get("allow_unsafe_execution"), default=default)


def resolve_openai_timeout_seconds(
    config: Dict,
    default: float = 300.0,
) -> float:
    """Resolve OpenAI request timeout seconds from environment or config."""
    raw_value: object = (
        os.environ.get(ENV_OPENAI_TIMEOUT_SECONDS)
        or config.get("openai_timeout_seconds")
    )
    if raw_value in (None, ""):
        return float(default)
    try:
        timeout = float(str(raw_value).strip())
    except (TypeError, ValueError):
        return float(default)
    return timeout if timeout > 0 else float(default)


def ensure_openai_api_key(config_file: str = CONFIG_FILE) -> str:
    """Ensure an OpenAI API key is configured."""
    del config_file
    api_key = resolve_openai_api_key({})
    if not api_key:
        raise RuntimeError(
            "OpenAI API key not configured. Set OPENAI_API_KEY as an environment "
            "variable. LEAM does not read OpenAI API keys from config.json. If "
            "you just added it through Windows Environment Variables, close and "
            "reopen PowerShell and LEAM first."
        )
    return api_key


def get_materials_path(cst_path: str) -> str:
    """Return the CST materials library path."""
    return os.path.join(cst_path, "Library", "Materials")


def get_python_libs_path(cst_path: str) -> str:
    if os.name == "nt":
        return os.path.join(cst_path, "AMD64", "python_cst_libraries")
    return os.path.join(cst_path, "LinuxAMD64", "python_cst_libraries")


def validate_cst_path(cst_path: Optional[str]) -> Tuple[bool, str]:
    """Validate the CST path and return a status with details."""
    if not cst_path:
        return (
            False,
            "CST was not detected automatically. Install CST Studio Suite "
            "locally. If LEAM still cannot find it, set CST_PATH or add "
            "`cst_path` to your LEAM config as an advanced override.",
        )
    if not os.path.isdir(cst_path):
        return False, f"CST path not found: {cst_path}"
    return True, ""


def validate_hfss_path(hfss_path: Optional[str]) -> Tuple[bool, str]:
    """Validate the HFSS path and return a status with details."""
    if not hfss_path:
        return (
            False,
            "HFSS was not detected automatically. Install Ansys Electronics "
            "Desktop locally. If LEAM still cannot find it, set HFSS_PATH or "
            "add `hfss_path` to your LEAM config as an advanced override.",
        )
    if not os.path.isdir(hfss_path):
        return False, f"HFSS path not found: {hfss_path}"
    return True, ""


def _module_spec_exists(module_name: str) -> bool:
    return optional_module_available(module_name)


def _read_packaged_example_config_text() -> str:
    resource = importlib_resources.files("leam").joinpath(*_CONFIG_EXAMPLE_RESOURCE)
    return resource.read_text(encoding="utf-8")


def _ensure_cst_runtime_connected(
    cst_path: Optional[str],
    python_libraries_path: Optional[str],
) -> Tuple[bool, str]:
    if not cst_path:
        return (
            False,
            "CST was not detected automatically. Install CST Studio Suite "
            "locally, or use `cst_path` / `CST_PATH` as an advanced override.",
        )
    if not python_libraries_path:
        return False, (
            "CST Python libraries were not found under the detected CST install."
        )

    if _module_spec_exists("cst.interface"):
        return True, ""

    if python_libraries_path not in sys.path:
        sys.path.insert(0, python_libraries_path)
        importlib.invalidate_caches()

    if _module_spec_exists("cst.interface"):
        return True, ""

    return False, (
        "Python package `cst.interface` is not available after bootstrapping "
        "the CST Python libraries path."
    )


def _bootstrap_desktop_runtime_config() -> Dict:
    """Load config, persist newly detected simulator paths, and bootstrap CST."""
    config = load_config()
    updated = autofill_simulator_paths(config)
    if any(
        not config.get(key) and updated.get(key)
        for key in ("cst_path", "hfss_path")
    ):
        _write_user_config(updated)
        config = updated
    _ensure_cst_runtime_connected(
        resolve_cst_path(config),
        resolve_cst_python_libraries_path(config),
    )
    return config


def autofill_simulator_paths(config: Optional[Dict] = None) -> Dict:
    """Fill missing simulator paths from local install detection."""
    updated = dict(config or {})

    if "allow_unsafe_execution" not in updated:
        updated["allow_unsafe_execution"] = False

    current_cst_path = updated.get("cst_path")
    if current_cst_path:
        normalized_cst = _normalize_cst_root(str(current_cst_path))
        updated["cst_path"] = normalized_cst or _normalize_path_text(str(current_cst_path))
    else:
        detected_cst = _detect_latest_cst_install(updated)
        if detected_cst:
            updated["cst_path"] = detected_cst["path"]

    current_hfss_path = updated.get("hfss_path")
    if current_hfss_path:
        normalized_hfss = _normalize_hfss_root(str(current_hfss_path))
        updated["hfss_path"] = normalized_hfss or _normalize_path_text(str(current_hfss_path))
    else:
        detected_hfss = _detect_latest_hfss_install(updated)
        if detected_hfss:
            updated["hfss_path"] = detected_hfss["path"]

    return updated


def initialize_user_config(config: Optional[Dict] = None) -> Tuple[Optional[Path], Dict]:
    """Write a user config with detected simulator paths filled in when available."""
    updated = autofill_simulator_paths(load_config() if config is None else config)
    if not updated:
        return None, updated
    return _write_user_config(updated), updated


def _runtime_setup_report(config: Dict) -> Dict[str, str]:
    cst_path = resolve_cst_path(config)
    cst_libraries_path = resolve_cst_python_libraries_path(config)
    cst_connected, cst_message = _ensure_cst_runtime_connected(
        cst_path,
        cst_libraries_path,
    )
    hfss_path = resolve_hfss_path(config)
    pyaedt_available = _module_spec_exists("ansys.aedt.core")

    return {
        "config_path": str(_user_config_path()),
        "cst_path": cst_path or "",
        "cst_python_libraries_path": cst_libraries_path or "",
        "cst_runtime_status": (
            "available"
            if cst_connected
            else (cst_message or "not configured")
        ),
        "hfss_path": hfss_path or "",
        "pyaedt_status": (
            "available"
            if pyaedt_available
            else "missing; reinstall LEAM with "
            f"`{RECOMMENDED_DESKTOP_INSTALL_COMMAND}`"
        ),
    }


def _print_runtime_setup_report(
    config: Dict,
    *,
    config_written: bool,
) -> None:
    report = _runtime_setup_report(config)

    print(
        (
            "Wrote LEAM config:"
            if config_written
            else "Resolved LEAM config (dry run):"
        ),
        report["config_path"],
    )
    print("cst_path:", report["cst_path"] or "not detected")
    print(
        "cst.interface:",
        report["cst_runtime_status"],
    )
    print("hfss_path:", report["hfss_path"] or "not detected")
    print("ansys.aedt.core:", report["pyaedt_status"])
    print(
        "OPENAI_API_KEY:",
        "required at runtime; LEAM reads it from the environment variable only",
    )


def main(argv: Optional[list[str]] = None) -> int:
    """Detect local simulator installs, write config, or print an example."""
    parser = ArgumentParser(
        prog="leam-configure",
        description=(
            "Advanced setup: detect local CST/HFSS installs and write "
            "~/.leam/config.json without overriding already pinned paths."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the resolved config without writing it.",
    )
    parser.add_argument(
        "--print-example",
        action="store_true",
        help="Print the packaged example config JSON and exit.",
    )
    args = parser.parse_args(argv)

    if args.print_example:
        print(_read_packaged_example_config_text().rstrip())
        return 0

    current = load_config()
    updated = autofill_simulator_paths(current)

    if args.dry_run:
        _print_runtime_setup_report(updated, config_written=False)
        return 0

    written_path = None
    if updated:
        written_path, updated = initialize_user_config(updated)

    _print_runtime_setup_report(updated, config_written=written_path is not None)
    return 0
