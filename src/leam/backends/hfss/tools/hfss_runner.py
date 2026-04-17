"""PyAEDT-backed runtime bridge for executing generated HFSS scripts."""

from __future__ import annotations

import ast
import functools
import importlib
import os
from pathlib import Path
from typing import Dict, Optional

from leam.config import (
    RECOMMENDED_DESKTOP_INSTALL_COMMAND,
    load_config,
    resolve_allow_unsafe_execution,
)
from leam.utils.path_utils import canonical_path_text

_FALSE_GUARD_METHOD_PREFIXES = (
    "create_",
    "cover_",
    "duplicate_",
    "insert_",
    "sweep_",
    "thicken_",
    "wrap_",
)
_FALSE_GUARD_METHOD_NAMES = {
    "chamfer",
    "connect",
    "delete",
    "fillet",
    "imprint",
    "intersect",
    "mirror",
    "move",
    "rotate",
    "section",
    "separate_bodies",
    "split",
    "subtract",
    "subtract_blank",
    "unite",
}
_SAFE_SCRIPT_BUILTINS = {
    "RuntimeError": RuntimeError,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "abs": abs,
    "all": all,
    "any": any,
    "enumerate": enumerate,
    "len": len,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "sum": sum,
    "zip": zip,
}
_SAFE_SCRIPT_GLOBAL_NAMES = {
    "hfss",
    "aedtapp",
    "app",
    "modeler",
}
_SAFE_DIRECT_CALL_NAMES = set(_SAFE_SCRIPT_BUILTINS)
_BLOCKED_NAME_PREFIX = "_"
_POLYLINE_SEGMENT_IMPORT_MODULE = "ansys.aedt.core.modeler.cad.primitives"
_POLYLINE_SEGMENT_IMPORT_NAME = "PolylineSegment"
_PYAEDT_POLYLINES_MODULE = "ansys.aedt.core.modeler.cad.polylines"
_PYAEDT_GENERAL_METHODS_MODULE = "ansys.aedt.core.generic.general_methods"
_PYAEDT_DESKTOP_MODULE = "ansys.aedt.core.desktop"
_PYAEDT_COMPOUND_SPLINE_PATCH_VERSION = "0.25.1"
_DISALLOWED_SCRIPT_NODES = [
    ast.AsyncFor,
    ast.AsyncFunctionDef,
    ast.AsyncWith,
    ast.Await,
    ast.ClassDef,
    ast.Delete,
    ast.DictComp,
    ast.FunctionDef,
    ast.GeneratorExp,
    ast.Global,
    ast.Import,
    ast.ImportFrom,
    ast.Lambda,
    ast.ListComp,
    ast.NamedExpr,
    ast.Nonlocal,
    ast.SetComp,
    ast.Try,
    ast.While,
    ast.With,
    ast.Yield,
    ast.YieldFrom,
]
_MATCH_NODE = getattr(ast, "Match", None)
if _MATCH_NODE is not None:
    _DISALLOWED_SCRIPT_NODES.append(_MATCH_NODE)
_DISALLOWED_SCRIPT_NODES = tuple(_DISALLOWED_SCRIPT_NODES)


def _build_psutil_target_process_query():
    """Build a PowerShell-free Windows process query for PyAEDT session discovery."""
    try:
        import psutil
    except Exception:
        return None

    ignored_errors = (
        psutil.NoSuchProcess,
        psutil.AccessDenied,
        getattr(psutil, "ZombieProcess", RuntimeError),
    )

    def _get_target_processes(target_name: list[str]) -> list[tuple[int, list[str]]]:
        target_names = {
            str(name).strip().casefold()
            for name in list(target_name or [])
            if str(name).strip()
        }
        if not target_names:
            return []

        found_data = []
        for process in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = str(process.info.get("name") or "").casefold()
                if name not in target_names:
                    continue

                pid = process.info.get("pid")
                cmdline = process.info.get("cmdline") or []
                if isinstance(cmdline, str):
                    cmdline = cmdline.split()
                found_data.append((int(pid), list(cmdline)))
            except ignored_errors:
                continue
            except (TypeError, ValueError):
                continue
        return found_data

    return _get_target_processes


def _patch_pyaedt_windows_process_query() -> None:
    """Hide PowerShell flash by replacing PyAEDT's Windows process query."""
    if os.name != "nt":
        return

    replacement = _build_psutil_target_process_query()
    if replacement is None:
        return

    try:
        general_methods = importlib.import_module(_PYAEDT_GENERAL_METHODS_MODULE)
        desktop_module = importlib.import_module(_PYAEDT_DESKTOP_MODULE)
    except Exception:
        return

    if getattr(general_methods, "_leam_psutil_process_query_patch", False):
        return

    general_methods._get_target_processes = replacement
    desktop_module._get_target_processes = replacement
    general_methods._leam_psutil_process_query_patch = True
    desktop_module._leam_psutil_process_query_patch = True


def _polyline_init_arg(args, kwargs, name: str, position: int, default=None):
    if name in kwargs:
        return kwargs[name]
    if len(args) > position:
        return args[position]
    return default


def _segment_type_name(segment) -> Optional[str]:
    return getattr(segment, "type", None)


def _segment_num_points(segment) -> int:
    try:
        return int(getattr(segment, "num_points"))
    except Exception:
        return 0


def _point_to_coordinate_list(point) -> list:
    if isinstance(point, list):
        return list(point)
    if isinstance(point, tuple):
        return list(point)
    if all(hasattr(point, axis) for axis in ("X", "Y", "Z")):
        return [point.X, point.Y, point.Z]
    return list(point)


def _normalize_compound_polyline_segments(segment_type, polyline_segment_cls):
    normalized = []
    for segment in segment_type:
        if isinstance(segment, str):
            normalized.append(polyline_segment_cls(segment))
        else:
            normalized.append(segment)
    return normalized


def _should_patch_compound_spline_segment_list(segment_type) -> bool:
    if not isinstance(segment_type, list):
        return False

    contains_spline = False
    for segment in segment_type:
        if isinstance(segment, str):
            if segment != "Spline":
                continue
            return False

        if _segment_type_name(segment) != "Spline":
            continue

        contains_spline = True
        if _segment_num_points(segment) <= 0:
            return False

    return contains_spline


def _build_corrected_compound_polyline_state(
    polyline,
    position_list,
    segment_type,
    *,
    close_surface: bool,
):
    polyline_segment_cls = type(polyline)._leam_polyline_segment_cls
    normalized_segments = _normalize_compound_polyline_segments(
        segment_type,
        polyline_segment_cls,
    )
    corrected_positions = [_point_to_coordinate_list(position_list[0])]
    point_index = 0

    for segment in normalized_segments:
        segment_name = _segment_type_name(segment)
        if segment_name == "Line":
            if len(position_list[point_index : point_index + 2]) < 2:
                raise ValueError(
                    "The position_list argument must contain at least 2 points for segment of type Line."
                )
            corrected_positions.extend(
                _point_to_coordinate_list(point)
                for point in position_list[point_index + 1 : point_index + 2]
            )
            point_index += 1
        elif segment_name == "Arc":
            if (
                (not close_surface and len(position_list[point_index : point_index + 3]) < 3)
                or (close_surface and len(position_list[point_index : point_index + 3]) < 2)
            ):
                raise ValueError(
                    "The position_list argument must contain at least 3 points for segment of type Arc."
                )
            corrected_positions.extend(
                _point_to_coordinate_list(point)
                for point in position_list[point_index + 1 : point_index + 3]
            )
            point_index += 2
        elif segment_name == "Spline":
            spline_point_count = _segment_num_points(segment)
            if len(position_list[point_index : point_index + spline_point_count]) < spline_point_count:
                raise ValueError(
                    "The position_list argument must contain all points required by the segment Spline."
                )
            corrected_positions.extend(
                _point_to_coordinate_list(point)
                for point in position_list[
                    point_index + 1 : point_index + spline_point_count
                ]
            )
            point_index += spline_point_count - 1
        elif segment_name == "AngularArc":
            start_point = _point_to_coordinate_list(position_list[point_index])
            polyline._evaluate_arc_angle_extra_points(
                segment,
                start_point=start_point,
            )
            corrected_positions.extend(
                _point_to_coordinate_list(point)
                for point in segment.extra_points[:]
            )
            point_index += _segment_num_points(segment) - 1
        else:
            raise TypeError(f"Invalid segment_type input of type {type(segment)}")

    return corrected_positions, normalized_segments


def _patch_pyaedt_compound_spline_polyline(aedt_core_module) -> None:
    """Fix PyAEDT 0.25.1 compound polyline spline point consumption."""
    version = str(getattr(aedt_core_module, "__version__", "") or "")
    if version != _PYAEDT_COMPOUND_SPLINE_PATCH_VERSION:
        return

    try:
        polylines_module = importlib.import_module(_PYAEDT_POLYLINES_MODULE)
    except Exception:
        return

    if getattr(polylines_module, "_leam_compound_spline_patch", False):
        return

    polyline_cls = getattr(polylines_module, "Polyline", None)
    polyline_segment_cls = getattr(polylines_module, "PolylineSegment", None)
    if polyline_cls is None or polyline_segment_cls is None:
        return

    original_init = polyline_cls.__init__
    original_point_segment_string_array = polyline_cls._point_segment_string_array

    @functools.wraps(original_init)
    def _patched_polyline_init(self, *args, **kwargs):
        source_object = _polyline_init_arg(args, kwargs, "src_object", 1)
        position_list = _polyline_init_arg(args, kwargs, "position_list", 2)
        segment_type = _polyline_init_arg(args, kwargs, "segment_type", 3)
        cover_surface = bool(
            _polyline_init_arg(args, kwargs, "cover_surface", 4, False)
        )
        close_surface = bool(
            _polyline_init_arg(args, kwargs, "close_surface", 5, False)
        )

        if (
            not source_object
            and position_list
            and _should_patch_compound_spline_segment_list(segment_type)
        ):
            self._leam_original_position_list = position_list
            self._leam_original_segment_type = segment_type
            self._leam_original_close_surface = close_surface or cover_surface

        original_init(self, *args, **kwargs)

        if hasattr(self, "_leam_original_position_list"):
            corrected_positions, corrected_segments = (
                _build_corrected_compound_polyline_state(
                    self,
                    self._leam_original_position_list,
                    self._leam_original_segment_type,
                    close_surface=self._leam_original_close_surface,
                )
            )
            self._positions = corrected_positions
            self._segment_types = corrected_segments

    @functools.wraps(original_point_segment_string_array)
    def _patched_point_segment_string_array(self):
        if not hasattr(self, "_leam_original_position_list"):
            return original_point_segment_string_array(self)

        corrected_positions, corrected_segments = (
            _build_corrected_compound_polyline_state(
                self,
                self._leam_original_position_list,
                self._leam_original_segment_type,
                close_surface=self._leam_original_close_surface,
            )
        )
        original_positions = self._positions
        original_segments = self._segment_types
        self._positions = corrected_positions
        self._segment_types = corrected_segments
        try:
            return original_point_segment_string_array(self)
        finally:
            self._positions = original_positions
            self._segment_types = original_segments

    polyline_cls.__init__ = _patched_polyline_init
    polyline_cls._point_segment_string_array = (
        _patched_point_segment_string_array
    )
    polyline_cls._leam_polyline_segment_cls = polyline_segment_cls
    polylines_module._leam_compound_spline_patch = True


def _is_allowed_helper_import(node: ast.ImportFrom) -> bool:
    if node.level != 0 or node.module != _POLYLINE_SEGMENT_IMPORT_MODULE:
        return False
    if len(node.names) != 1:
        return False
    imported_name = node.names[0]
    return imported_name.name == _POLYLINE_SEGMENT_IMPORT_NAME and imported_name.asname in (
        None,
        _POLYLINE_SEGMENT_IMPORT_NAME,
    )


class _HfssScriptNormalizer(ast.NodeTransformer):
    """Strip redundant imports that are preloaded into the runner sandbox."""

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if _is_allowed_helper_import(node):
            return None
        return self.generic_visit(node)


class _HfssScriptValidator(ast.NodeVisitor):
    """Reject Python features that exceed LEAM's HFSS runtime contract."""

    def __init__(
        self,
        *,
        extra_load_names: Optional[set[str]] = None,
        extra_direct_call_names: Optional[set[str]] = None,
    ) -> None:
        self._assigned_names = set()
        self._extra_load_names = set(extra_load_names or ())
        self._direct_call_names = set(_SAFE_DIRECT_CALL_NAMES) | set(
            extra_direct_call_names or ()
        )

    def _reject(self, node: ast.AST, message: str) -> None:
        line = getattr(node, "lineno", "?")
        raise ValueError(f"Line {line}: {message}")

    @staticmethod
    def _is_safe_name(name: str) -> bool:
        return bool(name) and not name.startswith(_BLOCKED_NAME_PREFIX)

    def _known_load_names(self) -> set[str]:
        return (
            set(_SAFE_SCRIPT_GLOBAL_NAMES)
            | set(_SAFE_SCRIPT_BUILTINS)
            | self._extra_load_names
            | self._assigned_names
        )

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, _DISALLOWED_SCRIPT_NODES):
            self._reject(
                node,
                f"Python construct `{type(node).__name__}` is not allowed in HFSS runner scripts.",
            )
        super().generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if not self._is_safe_name(node.attr):
            self._reject(
                node,
                "Private or dunder attribute access is not allowed in HFSS runner scripts.",
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if not self._is_safe_name(node.id):
            self._reject(
                node,
                f"Name `{node.id}` is not allowed in HFSS runner scripts.",
            )
        if isinstance(node.ctx, ast.Store):
            self._assigned_names.add(node.id)
            return
        if isinstance(node.ctx, ast.Load) and node.id not in self._known_load_names():
            self._reject(
                node,
                f"Name `{node.id}` is not available in the HFSS runner sandbox.",
            )

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id not in self._direct_call_names
        ):
            self._reject(
                node,
                f"Direct call to `{node.func.id}` is not allowed in HFSS runner scripts.",
            )
        self.generic_visit(node)


def _prepare_hfss_script_code(
    code: str,
    filename: str,
    *,
    extra_load_names: Optional[set[str]] = None,
    extra_direct_call_names: Optional[set[str]] = None,
):
    tree = ast.parse(code, filename=filename, mode="exec")
    tree = _HfssScriptNormalizer().visit(tree)
    tree = ast.fix_missing_locations(tree)
    _HfssScriptValidator(
        extra_load_names=extra_load_names,
        extra_direct_call_names=extra_direct_call_names,
    ).visit(tree)
    return compile(tree, filename, "exec")


def _should_guard_false(method_name: str) -> bool:
    return method_name.startswith(_FALSE_GUARD_METHOD_PREFIXES) or (
        method_name in _FALSE_GUARD_METHOD_NAMES
    )


def _unwrap_proxy_value(value):
    if isinstance(value, _PyAEDTProxy):
        return value.raw_target
    if isinstance(value, list):
        return [_unwrap_proxy_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_unwrap_proxy_value(item) for item in value)
    if isinstance(value, dict):
        return {
            key: _unwrap_proxy_value(item) for key, item in value.items()
        }
    if isinstance(value, set):
        return {_unwrap_proxy_value(item) for item in value}
    return value


def _wrap_proxy_value(value, path: str):
    if value is False:
        return False
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    if isinstance(value, list):
        return [
            _wrap_proxy_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, tuple):
        return tuple(
            _wrap_proxy_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    if isinstance(value, dict):
        return {
            key: _wrap_proxy_value(item, f"{path}[{key!r}]")
            for key, item in value.items()
        }
    if isinstance(value, set):
        return {_wrap_proxy_value(item, path) for item in value}
    return _PyAEDTProxy(value, path=path)


class _PyAEDTProxy:
    def __init__(
        self,
        target,
        *,
        path: str,
        guard_false: bool = False,
    ):
        self._target = target
        self._path = path
        self._guard_false = guard_false

    @property
    def raw_target(self):
        return self._target

    def __getattr__(self, name: str):
        attribute = getattr(self._target, name)
        return _wrap_proxy_value(
            attribute,
            f"{self._path}.{name}",
        ) if not callable(attribute) else _PyAEDTProxy(
            attribute,
            path=f"{self._path}.{name}",
            guard_false=_should_guard_false(name),
        )

    def __getitem__(self, key):
        value = self._target[_unwrap_proxy_value(key)]
        return _wrap_proxy_value(value, f"{self._path}[{key!r}]")

    def __setitem__(self, key, value) -> None:
        self._target[_unwrap_proxy_value(key)] = _unwrap_proxy_value(value)

    def __call__(self, *args, **kwargs):
        result = self._target(
            *[_unwrap_proxy_value(arg) for arg in args],
            **{
                key: _unwrap_proxy_value(value)
                for key, value in kwargs.items()
            },
        )
        if self._guard_false and result is False:
            raise RuntimeError(
                f"HFSS call `{self._path}` returned False."
            )
        return _wrap_proxy_value(result, f"{self._path}()")

    def __iter__(self):
        return iter(self._target)

    def __len__(self):
        return len(self._target)

    def __bool__(self):
        return bool(self._target)

    def __str__(self) -> str:
        return str(self._target)

    def __repr__(self) -> str:
        return repr(self._target)


class HfssRunner:
    """Run generated HFSS Python snippets inside one shared PyAEDT session."""

    def __init__(
        self,
        project_path: Optional[str] = None,
        design_name: Optional[str] = None,
        version: Optional[str] = None,
        non_graphical: bool = False,
        new_desktop: bool = False,
        close_desktop_on_exit: Optional[bool] = None,
        student_version: bool = False,
        machine: str = "",
        port: int = 0,
        aedt_process_id: Optional[int] = None,
        remove_lock: bool = False,
        allow_unsafe_execution: Optional[bool] = None,
    ):
        """Attach to one HFSS design or create a fresh one for script execution."""
        self.allow_unsafe_execution = self._resolve_unsafe_execution(
            allow_unsafe_execution
        )
        self._require_unsafe_execution_enabled()
        self.project_path = (
            canonical_path_text(project_path) if project_path else None
        )
        if self.project_path and os.path.exists(self.project_path):
            if not os.path.isfile(self.project_path):
                raise ValueError(
                    f"HFSS project path is not a file: {self.project_path}"
                )
        elif self.project_path:
            Path(self.project_path).parent.mkdir(parents=True, exist_ok=True)

        self.design_name = design_name
        self.version = version
        self.non_graphical = non_graphical
        self.new_desktop = new_desktop
        self.close_desktop_on_exit = (
            new_desktop
            if close_desktop_on_exit is None
            else bool(close_desktop_on_exit)
        )
        self.student_version = student_version
        self.machine = machine
        self.port = port
        self.aedt_process_id = aedt_process_id
        self.remove_lock = remove_lock

        self.history_tasks: Dict[str, str] = {}
        self.parameter_tasks: Dict[str, str] = {}

        self._aedt_core = self._load_aedt_core()
        self._script_helpers = self._load_script_helpers()
        self.hfss = self._create_hfss_session()
        self._script_globals = self._build_script_globals()

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
            "Generated HFSS script execution is disabled. Set "
            "LEAM_ALLOW_UNSAFE_EXECUTION=1 or `allow_unsafe_execution: true` "
            "in the LEAM config to execute generated simulator code."
        )

    def _load_aedt_core(self):
        """Import PyAEDT lazily so tests can mock it and users get a clear error."""
        try:
            aedt_core = importlib.import_module("ansys.aedt.core")
            _patch_pyaedt_windows_process_query()
            _patch_pyaedt_compound_spline_polyline(aedt_core)
            return aedt_core
        except Exception as exc:
            raise RuntimeError(
                "PyAEDT is not available. Reinstall LEAM with "
                f"`{RECOMMENDED_DESKTOP_INSTALL_COMMAND}` and make sure "
                "HFSS/AEDT is installed locally before using HfssRunner."
            ) from exc

    def _create_hfss_session(self):
        """Create a PyAEDT HFSS object for a new or existing project."""
        return self._aedt_core.Hfss(
            project=self.project_path,
            design=self.design_name,
            version=self.version,
            non_graphical=self.non_graphical,
            new_desktop=self.new_desktop,
            close_on_exit=False,
            student_version=self.student_version,
            machine=self.machine,
            port=self.port,
            aedt_process_id=self.aedt_process_id,
            remove_lock=self.remove_lock,
        )

    def _load_script_helpers(self) -> Dict[str, object]:
        """Expose narrowly-scoped helper symbols used by generated scripts."""
        helpers = {}
        try:
            primitives = importlib.import_module(
                _POLYLINE_SEGMENT_IMPORT_MODULE
            )
        except Exception:
            return helpers

        polyline_segment = getattr(
            primitives, _POLYLINE_SEGMENT_IMPORT_NAME, None
        )
        if polyline_segment is not None:
            helpers[_POLYLINE_SEGMENT_IMPORT_NAME] = polyline_segment
        return helpers

    def _build_script_globals(self) -> Dict[str, object]:
        """Build the execution namespace shared across all generated snippets."""
        strict_hfss = _PyAEDTProxy(self.hfss, path="hfss")
        modeler = getattr(strict_hfss, "modeler", None)
        return {
            "__builtins__": dict(_SAFE_SCRIPT_BUILTINS),
            "hfss": strict_hfss,
            "aedtapp": strict_hfss,
            "app": strict_hfss,
            "modeler": modeler,
            **self._script_helpers,
        }

    def set_build_tasks(self, tasks: Dict[str, str]) -> None:
        """Register ordered HFSS scripts used to build a project."""
        self.history_tasks = dict(tasks or {})

    def set_parameter_tasks(self, tasks: Dict[str, str]) -> None:
        """Register ordered HFSS scripts used to update an existing project."""
        self.parameter_tasks = dict(tasks or {})

    def _read_script_file(self, file_path: str) -> str:
        """Read one generated HFSS script from disk."""
        normalized = canonical_path_text(file_path)
        if not os.path.isfile(normalized):
            raise FileNotFoundError(f"HFSS script not found: {normalized}")
        with open(normalized, "r", encoding="utf-8") as script_file:
            return script_file.read()

    def _execute_script(self, task_name: str, file_path: str) -> None:
        """Execute one generated script in the shared HFSS namespace."""
        code = self._read_script_file(file_path)
        namespace = dict(self._script_globals)
        namespace["__file__"] = canonical_path_text(file_path)
        namespace["__name__"] = "__main__"
        try:
            compiled = _prepare_hfss_script_code(
                code,
                namespace["__file__"],
                extra_load_names=set(self._script_helpers),
                extra_direct_call_names={
                    name
                    for name, value in self._script_helpers.items()
                    if callable(value)
                },
            )
            exec(compiled, namespace, namespace)
        except Exception as exc:
            raise RuntimeError(
                f"HFSS task `{task_name}` failed while executing "
                f"{namespace['__file__']}: {exc}"
            ) from exc

    def run_build_tasks(self) -> None:
        """Execute all registered project-build scripts in insertion order."""
        for task_name, file_path in self.history_tasks.items():
            self._execute_script(task_name, file_path)

    def run_parameter_tasks(self) -> None:
        """Execute all registered parameter-update scripts in insertion order."""
        for task_name, file_path in self.parameter_tasks.items():
            self._execute_script(task_name, file_path)

    def save_project(
        self,
        save_path: Optional[str] = None,
        overwrite: bool = True,
        refresh_ids: bool = False,
    ) -> str:
        """Save the active HFSS project to the requested target path."""
        target_path = canonical_path_text(save_path) if save_path else self.project_path
        if target_path:
            Path(target_path).parent.mkdir(parents=True, exist_ok=True)

        kwargs = {
            "overwrite": overwrite,
            "refresh_ids": refresh_ids,
        }
        if target_path:
            kwargs["file_name"] = target_path

        result = self.hfss.save_project(**kwargs)
        if result is False:
            raise RuntimeError(
                f"HFSS failed to save project to {target_path or '<active project>'}."
            )
        if target_path:
            self.project_path = target_path
        return self.project_path or ""

    def create_project(
        self,
        save_path: str,
        overwrite: bool = True,
        refresh_ids: bool = False,
        save_after_each_task: bool = False,
        close_project_after_save: bool = True,
    ) -> str:
        """Run build tasks, save the HFSS project, and optionally release AEDT."""
        target_path = canonical_path_text(save_path)
        for task_name, file_path in self.history_tasks.items():
            self._execute_script(task_name, file_path)
            if save_after_each_task:
                self.save_project(
                    save_path=target_path,
                    overwrite=overwrite,
                    refresh_ids=refresh_ids,
                )

        self.save_project(
            save_path=target_path,
            overwrite=overwrite,
            refresh_ids=refresh_ids,
        )
        if close_project_after_save:
            self.close_project()
        return target_path

    def apply_parameter_updates(
        self,
        save_path: Optional[str] = None,
        overwrite: bool = True,
        refresh_ids: bool = False,
        close_project_after_save: bool = True,
    ) -> str:
        """Execute parameter-update scripts and save the updated project."""
        self.run_parameter_tasks()
        saved_path = self.save_project(
            save_path=save_path,
            overwrite=overwrite,
            refresh_ids=refresh_ids,
        )
        if close_project_after_save:
            self.close_project()
        return saved_path

    def close_project(self) -> None:
        """Release the HFSS session and optionally close the AEDT desktop."""
        if self.hfss is None:
            return
        self.hfss.release_desktop(True, self.close_desktop_on_exit)
        self.hfss = None
