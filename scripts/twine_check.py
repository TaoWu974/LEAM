from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    dist_dir = repo_root / "dist"
    artifacts = sorted(
        path
        for path in dist_dir.iterdir()
        if path.is_file() and path.name.endswith((".whl", ".tar.gz", ".zip"))
    ) if dist_dir.is_dir() else []
    if not artifacts:
        raise SystemExit("No distributions found under dist/. Run `python -m build` first.")
    command = [sys.executable, "-m", "twine", "check", *[str(path) for path in artifacts]]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
