"""Runtime bridge for executing generated VBA code in CST Studio Suite."""

from __future__ import annotations

import os
import re
from typing import Dict, Optional

from leam.config import load_config, resolve_allow_unsafe_execution


def _load_cst_interface():
    try:
        import cst.interface as cst_interface
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Python package `cst.interface` is not available. "
            "Install CST Studio Suite Python libraries or bootstrap the CST "
            "runtime before using CstRunner."
        ) from exc
    return cst_interface


class CstRunner:
    """Run generated VBA macros in CST Studio Suite."""

    def __init__(
        self,
        create_new_if_none: bool = False,
        project_path: Optional[str] = None,
        use_active_project: bool = False,
        allow_unsafe_execution: Optional[bool] = None,
    ):
        """Attach to CST environment and resolve target project handle."""
        self.allow_unsafe_execution = self._resolve_unsafe_execution(
            allow_unsafe_execution
        )
        self._require_unsafe_execution_enabled()
        cst_interface = _load_cst_interface()
        pids = cst_interface.running_design_environments()

        if pids:
            self.de = cst_interface.DesignEnvironment.connect(pids[0])
        elif create_new_if_none:
            self.de = cst_interface.DesignEnvironment.connect_to_any_or_new()
        else:
            raise RuntimeError(
                "No running CST DesignEnvironment found. "
                "Please start CST Studio Suite manually first."
            )

        self.prj = None
        if project_path:
            normalized = os.path.abspath(project_path)
            if not os.path.exists(normalized):
                raise FileNotFoundError(f"CST project not found: {normalized}")
            try:
                # Prefer already opened project to avoid duplicate sessions.
                self.prj = self.de.get_open_project(normalized)
            except Exception:
                # Fallback to opening from disk when not already attached.
                self.prj = self.de.open_project(normalized)
        elif use_active_project and self.de.has_active_project():
            self.prj = self.de.active_project()
        else:
            self.prj = self.de.new_mws()

        self.history_tasks: Dict[str, str] = {}
        self.parameter_tasks: Dict[str, str] = {}

    @staticmethod
    def _resolve_unsafe_execution(
        allow_unsafe_execution: Optional[bool],
    ) -> bool:
        if allow_unsafe_execution is not None:
            return bool(allow_unsafe_execution)
        return resolve_allow_unsafe_execution(load_config())

    def _require_unsafe_execution_enabled(self) -> None:
        if self.allow_unsafe_execution:
            return
        raise RuntimeError(
            "Generated CST VBA execution is disabled. Set "
            "LEAM_ALLOW_UNSAFE_EXECUTION=1 or `allow_unsafe_execution: true` "
            "in the LEAM config to execute generated simulator code."
        )

    def set_history_tasks(self, tasks: Dict[str, str]) -> None:
        """Register VBA tasks to run via AddToHistory."""
        self.history_tasks = tasks

    def set_parameter_tasks(self, tasks: Dict[str, str]) -> None:
        """Register VBA tasks to run via Schematic.execute_vba_code."""
        self.parameter_tasks = tasks

    def _read_vba_file(self, file_path: str) -> str:
        """Read VBA file contents and validate source path."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"VBA file not found: {file_path}")
        with open(file_path, "r", encoding="utf8") as vba_file:
            return vba_file.read()

    def _ensure_sub_main(self, vba_code: str) -> str:
        """Wrap plain VBA statements into `Sub Main` when needed."""
        if re.search(
            r"^\s*(Sub|Function)\b",
            vba_code,
            flags=re.IGNORECASE | re.MULTILINE,
        ):
            return vba_code
        stripped = vba_code.strip()
        if not stripped:
            return "Sub Main()\nEnd Sub\n"
        return f"Sub Main()\n{stripped}\nEnd Sub\n"

    def add_to_history(self, description: str, file_path: str) -> None:
        """Add a VBA macro to the model history and execute it."""
        vba_code = self._read_vba_file(file_path)
        self.prj.modeler.add_to_history(description, vba_code)

    def execute_vba_code(self, file_path: str) -> None:
        """Execute a VBA snippet via Schematic.execute_vba_code."""
        if self.prj.schematic is None:
            raise RuntimeError(
                "Schematic interface is not available for this project."
            )
        vba_code = self._read_vba_file(file_path)
        self.prj.schematic.execute_vba_code(self._ensure_sub_main(vba_code))

    def run_history_tasks(self) -> None:
        """Execute all history tasks using AddToHistory."""
        for task, vba_file in self.history_tasks.items():
            self.add_to_history(task, vba_file)

    def run_parameter_tasks(self) -> None:
        """Execute all parameter tasks using execute_vba_code."""
        if not self.parameter_tasks:
            return
        if self.prj.schematic is None:
            raise RuntimeError(
                "Schematic interface is not available for this project."
            )
        for _, vba_file in self.parameter_tasks.items():
            self.execute_vba_code(vba_file)

    def create_project(
        self,
        save_path: str,
        include_results: bool = False,
        allow_overwrite: bool = True,
        close_project_after_save: bool = True,
    ) -> None:
        """Run history tasks, save the project, and optionally close."""
        with self.de.quiet_mode_enabled():
            self.run_history_tasks()
            self.prj.save(
                save_path,
                include_results=include_results,
                allow_overwrite=allow_overwrite,
            )

        if close_project_after_save:
            self.close_project()

    def apply_parameter_updates(
        self,
        save_path: Optional[str] = None,
        include_results: bool = False,
        allow_overwrite: bool = True,
        close_project_after_save: bool = True,
    ) -> None:
        """Execute parameter updates and optionally save the project."""
        with self.de.quiet_mode_enabled():
            self.run_parameter_tasks()
            if save_path:
                self.prj.save(
                    save_path,
                    include_results=include_results,
                    allow_overwrite=allow_overwrite,
                )

        if close_project_after_save:
            self.close_project()

    def close_project(self) -> None:
        """Close the current CST project (keep CST open)."""
        if self.prj is not None:
            self.prj.close()
            self.prj = None
