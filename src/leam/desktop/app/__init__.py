"""PySide6 application bootstrap for LEAM Desktop."""

from __future__ import annotations

import sys

from leam.config import (
    RECOMMENDED_DESKTOP_INSTALL_COMMAND,
    _bootstrap_desktop_runtime_config,
)


def main() -> int:
    """Launch the LEAM desktop app."""

    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PySide6 is not installed. Reinstall LEAM with "
            f"`{RECOMMENDED_DESKTOP_INSTALL_COMMAND}` to use the desktop app."
        ) from exc

    from .main_window import MainWindow
    from .theme import apply_theme

    _bootstrap_desktop_runtime_config()

    app = QApplication(sys.argv)
    app.setApplicationName("LEAM Desktop")
    apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()
