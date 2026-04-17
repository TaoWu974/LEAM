from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path
from typing import Iterable

FORBIDDEN_ARCHIVE_SUBSTRINGS = ("examples/results_by_chat/",)


def _archive_members(artifact: Path) -> list[str]:
    if artifact.name.endswith(".whl") or artifact.name.endswith(".zip"):
        with zipfile.ZipFile(artifact) as archive:
            return [entry.filename.replace("\\", "/") for entry in archive.infolist()]
    if artifact.name.endswith(".tar.gz"):
        with tarfile.open(artifact, "r:gz") as archive:
            return [entry.name.replace("\\", "/") for entry in archive.getmembers()]
    raise ValueError(f"Unsupported distribution artifact: {artifact}")


def _assert_no_forbidden_members(artifacts: Iterable[Path]) -> None:
    for artifact in artifacts:
        members = _archive_members(artifact)
        for member in members:
            normalized = member.lstrip("./")
            if any(token in normalized for token in FORBIDDEN_ARCHIVE_SUBSTRINGS):
                raise SystemExit(
                    f"Forbidden repo-only content shipped in {artifact.name}: {normalized}"
                )


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_script(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def _run(command: list[str], *, cwd: Path) -> str:
    return subprocess.check_output(command, cwd=str(cwd), text=True)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    dist_dir = repo_root / "dist"
    if not dist_dir.is_dir():
        raise SystemExit("dist/ was not found. Run `python -m build` first.")

    artifacts = sorted(
        path
        for path in dist_dir.iterdir()
        if path.is_file() and path.name.endswith((".whl", ".tar.gz"))
    )
    if not artifacts:
        raise SystemExit("No wheel or sdist found under dist/.")

    wheels = [path for path in artifacts if path.name.endswith(".whl")]
    if not wheels:
        raise SystemExit("No wheel found under dist/.")

    _assert_no_forbidden_members(artifacts)

    wheel = wheels[0]
    with tempfile.TemporaryDirectory() as tempdir:
        venv_dir = Path(tempdir) / "smoke-venv"
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python_path = _venv_python(venv_dir)
        configure_path = _venv_script(venv_dir, "leam-configure")
        desktop_path = _venv_script(venv_dir, "leam-desktop")

        subprocess.check_call([str(python_path), "-m", "pip", "install", "-U", "pip"])
        subprocess.check_call([str(python_path), "-m", "pip", "install", str(wheel)])

        if not configure_path.exists():
            raise SystemExit(
                "`leam-configure` launcher was not installed into the environment."
            )
        if not desktop_path.exists():
            raise SystemExit("`leam-desktop` launcher was not installed into the environment.")

        _run(
            [
                str(python_path),
                "-c",
                (
                    "import importlib.util, leam; "
                    "assert hasattr(leam, 'LLMCaller'); "
                    "assert hasattr(leam, 'VBAGenerator'); "
                    "assert importlib.util.find_spec('leam.desktop') is not None; "
                    "assert importlib.util.find_spec('leam.desktop.app') is not None; "
                    "assert importlib.util.find_spec('leam.desktop.__main__') is not None; "
                    "assert importlib.util.find_spec('PySide6') is not None; "
                    "assert importlib.util.find_spec('ansys.aedt.core') is not None; "
                    "assert importlib.util.find_spec('pandas') is not None"
                ),
            ],
            cwd=repo_root,
        )
        _run([str(configure_path), "--dry-run"], cwd=repo_root)
        example_text = _run([str(configure_path), "--print-example"], cwd=repo_root)
        payload = json.loads(example_text)
        if not isinstance(payload, dict) or "allow_unsafe_execution" not in payload:
            raise SystemExit("`leam-configure --print-example` did not return the expected JSON payload.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
