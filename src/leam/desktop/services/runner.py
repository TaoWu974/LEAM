"""Service layer that bridges desktop steps to existing LEAM tools."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from leam.config import (
    RECOMMENDED_DESKTOP_INSTALL_COMMAND,
    _ensure_cst_runtime_connected,
    _module_spec_exists,
    load_config,
    resolve_allow_unsafe_execution,
    resolve_cst_path,
    resolve_cst_python_libraries_path,
    resolve_hfss_path,
    validate_cst_path,
    validate_hfss_path,
)
from leam.core.errors import InputValidationError
from leam.utils.document_utils import PDF_INPUT_EXTENSIONS
from leam.utils.file_io import (
    PROMPT_TEXT_EXTENSIONS,
    is_prompt_text_file,
    read_prompt_text_file,
)
from leam.utils.image_utils import MODEL_IMAGE_EXTENSIONS

from ..workflow.models import (
    ArtifactRef,
    StepResult,
    WorkflowSession,
    WorkflowStepDefinition,
)

TEXT_EXTENSIONS = set(PROMPT_TEXT_EXTENSIONS)
IMAGE_EXTENSIONS = set(MODEL_IMAGE_EXTENSIONS) | {
    ".bmp",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
}


def _describe_cst_availability(
    cst_path: Optional[str],
    *,
    cst_ok: bool,
    cst_message: str,
    cst_connected: bool,
    cst_runtime_message: str,
) -> str:
    if cst_ok and cst_connected:
        return ""
    if not cst_path:
        return (
            "CST Studio Suite was not detected on this machine. Install CST "
            "locally first. If LEAM still cannot find it, set `cst_path` / "
            "`CST_PATH` as an advanced override."
        )
    if not cst_ok:
        return cst_message or "CST Studio Suite is not available."
    return cst_runtime_message or cst_message or "CST Studio Suite is not available."


def _describe_hfss_availability(
    hfss_path: Optional[str],
    *,
    hfss_ok: bool,
    hfss_message: str,
    has_pyaedt: bool,
) -> str:
    if hfss_ok and has_pyaedt:
        return ""
    if not hfss_path:
        return (
            "Ansys Electronics Desktop was not detected on this machine. "
            "Install HFSS locally first. If LEAM still cannot find it, set "
            "`hfss_path` / `HFSS_PATH` as an advanced override."
        )
    if not hfss_ok:
        return hfss_message or "HFSS is not available."
    return (
        "HFSS was detected, but the Python package `ansys.aedt.core` is "
        "missing. Reinstall LEAM with "
        f"`{RECOMMENDED_DESKTOP_INSTALL_COMMAND}`."
    )
NON_TEXT_ATTACHMENT_EXTENSIONS = {
    ".7z",
    ".aedt",
    ".aedtz",
    ".bin",
    ".cst",
    ".dll",
    ".dylib",
    ".exe",
    ".gz",
    ".pyc",
    ".pyd",
    ".rar",
    ".so",
    ".zip",
}


def _get_cst_runner_cls():
    from leam.backends.cst.tools import CstRunner

    return CstRunner


def _format_unsupported_model_image_message(paths: List[str]) -> str:
    names = ", ".join(sorted(Path(path).name for path in paths))
    return (
        "Unsupported image attachment(s) for model input: "
        f"{names}. LEAM currently forwards only PNG and JPEG images "
        "to the model. Convert these files to `.png`, `.jpg`, or `.jpeg`, "
        "or disable them before running the step."
    )


class DesktopWorkflowRunner:
    """Run one desktop workflow step against the existing backend tools."""

    def run(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
    ) -> StepResult:
        run_dir = self._create_run_dir(session, definition.id)
        session.steps[definition.id].settings["last_run_dir"] = run_dir
        step_type = definition.step_type
        if step_type == "initial_solids":
            return self._run_initial_solids(definition, session, run_dir)
        if step_type == "parameters":
            return self._run_parameters(definition, session, run_dir)
        if step_type == "materials":
            return self._run_materials(definition, session, run_dir)
        if step_type == "solids":
            return self._run_solids(definition, session, run_dir)
        if step_type == "check_solid":
            return self._run_check_solid(definition, session, run_dir)
        if step_type == "dimensions":
            return self._run_dimensions(definition, session, run_dir)
        if step_type == "model_3d":
            return self._run_model_3d(definition, session, run_dir)
        if step_type == "model_2d":
            return self._run_model_2d(definition, session, run_dir)
        if step_type == "boolean":
            return self._run_boolean(definition, session, run_dir)
        if step_type == "cst_project":
            return self._run_cst_project(definition, session, run_dir)
        if step_type == "parameter_update":
            return self._run_parameter_update(definition, session, run_dir)
        if step_type == "cst_update":
            return self._run_cst_update(definition, session, run_dir)
        if step_type == "hfss_project":
            return self._run_hfss_project(definition, session, run_dir)
        if step_type == "hfss_update":
            return self._run_hfss_update(definition, session, run_dir)
        raise InputValidationError(f"Unsupported desktop step type: {step_type}")

    def detect_25d_from_artifacts(
        self,
        session: WorkflowSession,
        artifact_ids: List[str],
    ) -> bool:
        for artifact_id in artifact_ids:
            artifact = session.artifacts.get(artifact_id)
            if not artifact or artifact.label != "solids_json":
                continue
            try:
                with open(artifact.path, "r", encoding="utf-8") as source:
                    payload = json.load(source)
            except Exception:
                continue
            solids = payload.get("solids", []) if isinstance(payload, dict) else []
            if any(str(item.get("Type") or "").strip() == "2.5D" for item in solids if isinstance(item, dict)):
                return True
        return False

    def get_environment_report(self) -> Dict[str, object]:
        config = load_config()
        cst_path = resolve_cst_path(config)
        cst_ok, cst_message = validate_cst_path(cst_path)
        cst_python_libraries_path = resolve_cst_python_libraries_path(config)
        cst_connected, cst_runtime_message = _ensure_cst_runtime_connected(
            cst_path,
            cst_python_libraries_path,
        )
        has_cst_interface = bool(cst_connected)
        hfss_path = resolve_hfss_path(config)
        hfss_ok, hfss_message = validate_hfss_path(hfss_path)
        has_pyaedt = bool(_module_spec_exists("ansys.aedt.core"))
        cst_available = bool(cst_ok and has_cst_interface)
        hfss_available = bool(hfss_ok and has_pyaedt)
        unsafe_execution_enabled = resolve_allow_unsafe_execution(config)
        cst_available_message = _describe_cst_availability(
            cst_path,
            cst_ok=cst_ok,
            cst_message=str(cst_message or "").strip(),
            cst_connected=has_cst_interface,
            cst_runtime_message=str(cst_runtime_message or "").strip(),
        )
        hfss_available_message = _describe_hfss_availability(
            hfss_path,
            hfss_ok=hfss_ok,
            hfss_message=str(hfss_message or "").strip(),
            has_pyaedt=has_pyaedt,
        )
        available_backends: List[str] = []
        if cst_available:
            available_backends.append("cst")
        if hfss_available:
            available_backends.append("hfss")
        status = {
            "platform": os.name,
            "cst_path": cst_path or "",
            "cst_path_ok": "yes" if cst_ok else "no",
            "cst_path_message": cst_message,
            "cst_interface_ok": "yes" if has_cst_interface else "no",
            "cst_python_libraries_path": cst_python_libraries_path or "",
            "cst_available": cst_available,
            "cst_available_message": cst_available_message,
            "hfss_path": hfss_path or "",
            "hfss_path_ok": "yes" if hfss_ok else "no",
            "hfss_path_message": hfss_message,
            "pyaedt_ok": "yes" if has_pyaedt else "no",
            "hfss_available": hfss_available,
            "hfss_available_message": hfss_available_message,
            "unsafe_execution_enabled": unsafe_execution_enabled,
            "unsafe_execution_message": (
                ""
                if unsafe_execution_enabled
                else "Generated HFSS/CST execution is disabled. Set "
                "LEAM_ALLOW_UNSAFE_EXECUTION=1 or "
                "`allow_unsafe_execution: true` in the LEAM config to run "
                "generated simulator code."
            ),
            "available_backends": available_backends,
            "all_backends_unavailable": not available_backends,
        }
        return status

    @staticmethod
    def _backend(session: WorkflowSession) -> str:
        """Return the active desktop backend for this session."""
        input_state = session.steps.get("input")
        settings = input_state.settings if input_state else {}
        backend = str(settings.get("backend") or "").strip().lower()
        return backend if backend in {"cst", "hfss"} else "cst"

    def _run_initial_solids(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        backend = self._backend(session)
        if backend == "hfss":
            from leam.backends.hfss.tools.weak_description_to_solids import (
                WeakDescriptionToSolids,
            )
        else:
            from leam.backends.cst.tools.weak_description_to_solids import (
                WeakDescriptionToSolids,
            )

        description, image_paths, pdf_paths, prompt_files = self._collect_inputs(
            definition, session
        )
        generator = WeakDescriptionToSolids(save_dir=run_dir)
        generator.get_solids(
            description=description,
            image_paths=image_paths,
            additional_prompt_files=prompt_files,
            pdf_paths=pdf_paths,
            save_as="initial_solids.json",
        )
        artifact_id = self._register_artifact(
            session,
            definition.id,
            label="solids_json",
            path=str(Path(run_dir) / "initial_solids.json"),
        )
        return StepResult(
            status="success",
            artifact_ids=[artifact_id],
            primary_artifact_id=artifact_id,
            preview_text=self._read_preview(session.artifacts[artifact_id].path),
            logs=[
                "Generated initial weak-description solids.",
                f"Run folder: {run_dir}",
            ],
        )

    def _run_parameters(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        backend = self._backend(session)
        if backend == "hfss":
            from leam.backends.hfss.tools.parameter_generator import ParameterGenerator
        else:
            from leam.backends.cst.tools.parameter_generator import ParameterGenerator

        description, image_paths, pdf_paths, prompt_files = self._collect_inputs(
            definition, session
        )
        generator = ParameterGenerator(save_dir=run_dir)
        if backend == "hfss":
            generator.generate_parameters(
                description=description,
                image_paths=image_paths,
                output_file="parameters.py",
                json_file="parameters.json",
                additional_prompt_files=prompt_files,
                pdf_paths=pdf_paths,
            )
        else:
            generator.generate_parameters(
                description=description,
                image_paths=image_paths,
                output_file="parameters.bas",
                json_file="parameters.json",
                additional_prompt_files=prompt_files,
                pdf_paths=pdf_paths,
            )
        script_path = str(
            Path(run_dir) / ("parameters.py" if backend == "hfss" else "parameters.bas")
        )
        json_path = str(Path(run_dir) / "parameters.json")
        script_id = self._register_artifact(
            session,
            definition.id,
            "parameters_py" if backend == "hfss" else "parameters_bas",
            script_path,
        )
        json_id = self._register_artifact(session, definition.id, "parameters_json", json_path)
        return StepResult(
            status="success",
            artifact_ids=[script_id, json_id],
            primary_artifact_id=json_id,
            preview_text=self._read_preview(json_path),
            logs=[
                (
                    "Generated HFSS parameter script and companion JSON."
                    if backend == "hfss"
                    else "Generated CST parameters macro and companion JSON."
                ),
                f"Run folder: {run_dir}",
            ],
        )

    def _run_materials(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        backend = self._backend(session)
        if backend == "hfss":
            from leam.backends.hfss.tools.materials import MaterialsProcessor
        else:
            from leam.backends.cst.tools.materials import MaterialsProcessor

        description, image_paths, pdf_paths, prompt_files = self._collect_inputs(
            definition, session
        )
        processor = MaterialsProcessor(save_dir=run_dir)
        json_path = str(Path(run_dir) / "materials.json")
        json_id = None
        artifact_ids: List[str] = []
        if backend == "hfss":
            processor.generate_materials(
                description=description,
                image_paths=image_paths,
                additional_prompt_files=prompt_files,
                pdf_paths=pdf_paths,
                save_as="materials.json",
            )
            json_id = self._register_artifact(
                session, definition.id, "materials_json", json_path
            )
            artifact_ids = [json_id]
        else:
            processor.generate_materials(
                description=description,
                image_paths=image_paths,
                additional_prompt_files=prompt_files,
                pdf_paths=pdf_paths,
                save_as="materials.json",
                macro_file="materials.bas",
            )
            macro_path = Path(run_dir) / "materials.bas"
            if not macro_path.exists():
                macro_path.write_text("' No custom materials required.\n", encoding="utf-8")
            bas_path = str(macro_path)
            json_id = self._register_artifact(session, definition.id, "materials_json", json_path)
            bas_id = self._register_artifact(session, definition.id, "materials_bas", bas_path)
            artifact_ids = [json_id, bas_id]
        return StepResult(
            status="success",
            artifact_ids=artifact_ids,
            primary_artifact_id=json_id,
            preview_text=self._read_preview(json_path),
            logs=[
                (
                    "Generated HFSS material selection JSON."
                    if backend == "hfss"
                    else "Generated material selection JSON and import macro."
                ),
                f"Run folder: {run_dir}",
            ],
        )

    def _run_solids(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        description, image_paths, pdf_paths, prompt_files = self._collect_inputs(
            definition, session
        )
        template = session.template
        backend = self._backend(session)
        if backend == "hfss":
            if template == "weak_description":
                from leam.backends.hfss.tools.weak_description_to_solids import (
                    WeakDescriptionToSolids as Generator,
                )
            else:
                from leam.backends.hfss.tools.strong_description_to_solids import (
                    StrongDescriptionToSolids as Generator,
                )
        else:
            if template == "weak_description":
                from leam.backends.cst.tools.weak_description_to_solids import (
                    WeakDescriptionToSolids as Generator,
                )
            else:
                from leam.backends.cst.tools.strong_description_to_solids import (
                    StrongDescriptionToSolids as Generator,
                )

        generator = Generator(save_dir=run_dir)
        generator.get_solids(
            description=description,
            image_paths=image_paths,
            additional_prompt_files=prompt_files,
            pdf_paths=pdf_paths,
            save_as="solids.json",
        )
        solids_path = str(Path(run_dir) / "solids.json")
        artifact_id = self._register_artifact(session, definition.id, "solids_json", solids_path)
        return StepResult(
            status="success",
            artifact_ids=[artifact_id],
            primary_artifact_id=artifact_id,
            preview_text=self._read_preview(solids_path),
            logs=[
                "Generated canonical solids JSON.",
                f"Run folder: {run_dir}",
            ],
        )

    def _run_check_solid(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        backend = self._backend(session)
        if backend == "hfss":
            from leam.backends.hfss.tools.check_solid import CheckSolid
        else:
            from leam.backends.cst.tools.check_solid import CheckSolid

        description, image_paths, pdf_paths, _ = self._collect_inputs(
            definition, session
        )
        solids_path = self._require_selected_artifact_path(session, definition.id, "solids_json")
        parameters_path = self._require_selected_artifact_path(session, definition.id, "parameters_json")
        materials_path = self._require_selected_artifact_path(session, definition.id, "materials_json")
        checker = (
            CheckSolid(save_dir=run_dir)
            if backend == "hfss"
            else CheckSolid(save_dir=run_dir, backend=backend)
        )
        result = checker.check(
            description=description,
            image_paths=image_paths,
            solids_file=solids_path,
            parameters_file=parameters_path,
            materials_file=materials_path,
            pdf_paths=pdf_paths,
            save_as="solids_check.json",
        )
        report_path = str(Path(run_dir) / "solids_check.json")
        artifact_id = self._register_artifact(session, definition.id, "check_solid_report", report_path)
        status = "issues" if str(result.get("status") or "") == "issues" else "success"
        return StepResult(
            status=status,
            artifact_ids=[artifact_id],
            primary_artifact_id=artifact_id,
            preview_text=self._read_preview(report_path),
            logs=[
                "Ran `check_solid` on the selected solids, parameters, and materials inputs.",
                f"Issue count: {int(result.get('issue_counts', {}).get('total', 0))}",
                f"Run folder: {run_dir}",
            ],
            raw_payload=result if isinstance(result, dict) else {},
        )

    def _run_dimensions(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        backend = self._backend(session)
        if backend == "hfss":
            from leam.backends.hfss.tools.dimension_generator import DimensionGenerator
        else:
            from leam.backends.cst.tools.dimension_generator import DimensionGenerator

        description, image_paths, pdf_paths, prompt_files = self._collect_inputs(
            definition, session
        )
        generator = DimensionGenerator(save_dir=run_dir)
        generator.generate_dimensions(
            description=description,
            image_paths=image_paths,
            additional_prompt_files=prompt_files,
            pdf_paths=pdf_paths,
            save_as="dimensions.json",
        )
        path = str(Path(run_dir) / "dimensions.json")
        artifact_id = self._register_artifact(session, definition.id, "dimensions_json", path)
        return StepResult(
            status="success",
            artifact_ids=[artifact_id],
            primary_artifact_id=artifact_id,
            preview_text=self._read_preview(path),
            logs=[
                "Generated normalized dimensions JSON.",
                f"Run folder: {run_dir}",
            ],
        )

    def _run_model_3d(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        backend = self._backend(session)
        if backend == "hfss":
            from leam.backends.hfss.tools.model_3d_generator import Model3DGenerator
        else:
            from leam.backends.cst.tools.model_3d_generator import Model3DGenerator

        description, _, _, prompt_files = self._collect_inputs(definition, session)
        generator = Model3DGenerator(save_dir=run_dir)
        if backend == "hfss":
            materials_path = self._require_selected_artifact_path(
                session, definition.id, "materials_json"
            )
            generator.generate_model(
                description=description,
                additional_prompt_files=prompt_files,
                materials_file=materials_path,
                save_as="model_3d.py",
            )
            path = str(Path(run_dir) / "model_3d.py")
            artifact_id = self._register_artifact(
                session, definition.id, "model_3d_py", path
            )
        else:
            generator.generate_model(
                description=description,
                additional_prompt_files=prompt_files,
                save_as="model_3d.bas",
            )
            path = str(Path(run_dir) / "model_3d.bas")
            artifact_id = self._register_artifact(session, definition.id, "model_3d_bas", path)
        return StepResult(
            status="success",
            artifact_ids=[artifact_id],
            primary_artifact_id=artifact_id,
            preview_text=self._read_preview(path),
            logs=[
                (
                    "Generated 3D HFSS Python script."
                    if backend == "hfss"
                    else "Generated 3D CST VBA macro."
                ),
                f"Run folder: {run_dir}",
            ],
        )

    def _run_model_2d(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        backend = self._backend(session)
        if backend == "hfss":
            from leam.backends.hfss.tools.model_2d_generator import Model2DGenerator
        else:
            from leam.backends.cst.tools.model_2d_generator import Model2DGenerator

        description, _, _, prompt_files = self._collect_inputs(definition, session)
        generator = Model2DGenerator(save_dir=run_dir)
        if backend == "hfss":
            materials_path = self._require_selected_artifact_path(
                session, definition.id, "materials_json"
            )
            generator.generate_model(
                description=description,
                additional_prompt_files=prompt_files,
                materials_file=materials_path,
                save_as="model_2d.py",
            )
            path = str(Path(run_dir) / "model_2d.py")
            artifact_id = self._register_artifact(
                session, definition.id, "model_2d_py", path
            )
        else:
            generator.generate_model(
                description=description,
                additional_prompt_files=prompt_files,
                save_as="model_2d.bas",
            )
            path = str(Path(run_dir) / "model_2d.bas")
            artifact_id = self._register_artifact(session, definition.id, "model_2d_bas", path)
        return StepResult(
            status="success",
            artifact_ids=[artifact_id],
            primary_artifact_id=artifact_id,
            preview_text=self._read_preview(path),
            logs=[
                (
                    "Generated 2.5D HFSS Python script."
                    if backend == "hfss"
                    else "Generated 2.5D CST VBA macro."
                ),
                f"Run folder: {run_dir}",
            ],
        )

    def _run_boolean(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        backend = self._backend(session)
        if backend == "hfss":
            from leam.backends.hfss.tools.boolean_ops import BooleanOperationsGenerator
        else:
            from leam.backends.cst.tools.boolean_ops import BooleanOperationsGenerator

        description, _, _, prompt_files = self._collect_inputs(definition, session)
        generator = BooleanOperationsGenerator(save_dir=run_dir)
        if backend == "hfss":
            generator.generate_operations(
                description=description,
                additional_prompt_files=prompt_files,
                save_as="boolean.py",
            )
            path = str(Path(run_dir) / "boolean.py")
            artifact_id = self._register_artifact(
                session, definition.id, "boolean_py", path
            )
        else:
            generator.generate_operations(
                description=description,
                additional_prompt_files=prompt_files,
                save_as="boolean.bas",
            )
            path = str(Path(run_dir) / "boolean.bas")
            artifact_id = self._register_artifact(session, definition.id, "boolean_bas", path)
        return StepResult(
            status="success",
            artifact_ids=[artifact_id],
            primary_artifact_id=artifact_id,
            preview_text=self._read_preview(path),
            logs=[
                (
                    "Generated boolean operations HFSS Python script."
                    if backend == "hfss"
                    else "Generated boolean operations VBA macro."
                ),
                f"Run folder: {run_dir}",
            ],
        )

    def _run_cst_project(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        environment = self.get_environment_report()
        if not environment["cst_available"]:
            raise RuntimeError(str(environment["cst_available_message"] or "CST is not available."))
        if not environment["unsafe_execution_enabled"]:
            raise RuntimeError(str(environment["unsafe_execution_message"]))

        parameters_path = self._require_selected_artifact_path(session, definition.id, "parameters_bas")
        materials_path = self._require_selected_artifact_path(session, definition.id, "materials_bas")
        model_3d_path = self._require_selected_artifact_path(session, definition.id, "model_3d_bas")
        boolean_path = self._require_selected_artifact_path(session, definition.id, "boolean_bas")
        model_2d_path = self._find_selected_artifact_path(session, definition.id, "model_2d_bas")

        runner_cls = _get_cst_runner_cls()
        runner = runner_cls(
            create_new_if_none=False,
            allow_unsafe_execution=bool(environment["unsafe_execution_enabled"]),
        )
        tasks = {
            "Parameters": parameters_path,
            "Materials": materials_path,
            "3D Model": model_3d_path,
        }
        if model_2d_path:
            tasks["2.5D Model"] = model_2d_path
        tasks["Boolean Operations"] = boolean_path
        runner.set_history_tasks(tasks)
        project_path = str(Path(run_dir) / "antenna.cst")
        runner.create_project(
            project_path,
            include_results=False,
            allow_overwrite=True,
            close_project_after_save=True,
        )
        artifact_id = self._register_artifact(session, definition.id, "cst_project", project_path)
        return StepResult(
            status="success",
            artifact_ids=[artifact_id],
            primary_artifact_id=artifact_id,
            preview_text=project_path,
            logs=[
                "Created a CST project from the selected macro artifacts.",
                f"Run folder: {run_dir}",
            ],
        )

    def _run_parameter_update(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        backend = self._backend(session)
        if backend == "hfss":
            from leam.backends.hfss.tools.parameter_update import ParameterUpdater
        else:
            from leam.backends.cst.tools.parameter_update import ParameterUpdater

        description, image_paths, pdf_paths, prompt_files = self._collect_inputs(
            definition, session
        )
        generator = ParameterUpdater(save_dir=run_dir)
        if backend == "hfss":
            generator.generate_update(
                description=description,
                image_paths=image_paths,
                additional_prompt_files=prompt_files,
                pdf_paths=pdf_paths,
                save_as="parameter_update.py",
            )
            path = str(Path(run_dir) / "parameter_update.py")
            artifact_id = self._register_artifact(
                session, definition.id, "parameter_update_py", path
            )
        else:
            generator.generate_update(
                description=description,
                image_paths=image_paths,
                additional_prompt_files=prompt_files,
                pdf_paths=pdf_paths,
                save_as="parameter_update.bas",
            )
            path = str(Path(run_dir) / "parameter_update.bas")
            artifact_id = self._register_artifact(session, definition.id, "parameter_update_bas", path)
        return StepResult(
            status="success",
            artifact_ids=[artifact_id],
            primary_artifact_id=artifact_id,
            preview_text=self._read_preview(path),
            logs=[
                (
                    "Generated HFSS parameter update script."
                    if backend == "hfss"
                    else "Generated parameter update macro."
                ),
                f"Run folder: {run_dir}",
            ],
        )

    def _run_cst_update(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        environment = self.get_environment_report()
        if not environment["cst_available"]:
            raise RuntimeError(str(environment["cst_available_message"] or "CST is not available."))
        if not environment["unsafe_execution_enabled"]:
            raise RuntimeError(str(environment["unsafe_execution_message"]))

        update_macro = self._require_selected_artifact_path(session, definition.id, "parameter_update_bas")
        project_path = self._require_selected_artifact_path(session, definition.id, "cst_project")

        runner_cls = _get_cst_runner_cls()
        runner = runner_cls(
            create_new_if_none=False,
            project_path=project_path,
            allow_unsafe_execution=bool(environment["unsafe_execution_enabled"]),
        )
        runner.set_parameter_tasks({"Update Parameters": update_macro})
        updated_path = str(Path(run_dir) / "antenna_updated.cst")
        runner.apply_parameter_updates(
            save_path=updated_path,
            include_results=False,
            allow_overwrite=True,
            close_project_after_save=True,
        )
        artifact_id = self._register_artifact(session, definition.id, "cst_updated_project", updated_path)
        return StepResult(
            status="success",
            artifact_ids=[artifact_id],
            primary_artifact_id=artifact_id,
            preview_text=updated_path,
            logs=[
                "Applied parameter updates to the selected CST project.",
                f"Run folder: {run_dir}",
            ],
        )

    def _run_hfss_project(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        environment = self.get_environment_report()
        if not environment["hfss_available"]:
            raise RuntimeError(str(environment["hfss_available_message"] or "HFSS is not available."))
        if not environment["unsafe_execution_enabled"]:
            raise RuntimeError(str(environment["unsafe_execution_message"]))

        parameters_path = self._require_selected_artifact_path(session, definition.id, "parameters_py")
        model_3d_path = self._require_selected_artifact_path(session, definition.id, "model_3d_py")
        boolean_path = self._require_selected_artifact_path(session, definition.id, "boolean_py")
        model_2d_path = self._find_selected_artifact_path(session, definition.id, "model_2d_py")
        project_path = str(Path(run_dir) / "antenna.aedt")

        from leam.backends.hfss.tools.hfss_runner import HfssRunner

        runner = HfssRunner(
            project_path=project_path,
            new_desktop=True,
            non_graphical=False,
            allow_unsafe_execution=bool(environment["unsafe_execution_enabled"]),
        )
        tasks = {
            "Parameters": parameters_path,
            "3D Model": model_3d_path,
        }
        if model_2d_path:
            tasks["2.5D Model"] = model_2d_path
        tasks["Boolean Operations"] = boolean_path
        runner.set_build_tasks(tasks)
        runner.create_project(
            save_path=project_path,
            overwrite=True,
            close_project_after_save=True,
        )
        artifact_id = self._register_artifact(session, definition.id, "hfss_project", project_path)
        return StepResult(
            status="success",
            artifact_ids=[artifact_id],
            primary_artifact_id=artifact_id,
            preview_text=project_path,
            logs=[
                "Created an HFSS project from the selected Python artifacts.",
                f"Run folder: {run_dir}",
            ],
        )

    def _run_hfss_update(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        run_dir: str,
    ) -> StepResult:
        environment = self.get_environment_report()
        if not environment["hfss_available"]:
            raise RuntimeError(str(environment["hfss_available_message"] or "HFSS is not available."))
        if not environment["unsafe_execution_enabled"]:
            raise RuntimeError(str(environment["unsafe_execution_message"]))

        update_script = self._require_selected_artifact_path(session, definition.id, "parameter_update_py")
        project_path = self._require_selected_artifact_path(session, definition.id, "hfss_project")

        from leam.backends.hfss.tools.hfss_runner import HfssRunner

        runner = HfssRunner(
            project_path=project_path,
            new_desktop=True,
            non_graphical=False,
            allow_unsafe_execution=bool(environment["unsafe_execution_enabled"]),
        )
        runner.set_parameter_tasks({"Update Parameters": update_script})
        updated_path = str(Path(run_dir) / "antenna_updated.aedt")
        runner.apply_parameter_updates(
            save_path=updated_path,
            overwrite=True,
            close_project_after_save=True,
        )
        artifact_id = self._register_artifact(session, definition.id, "hfss_updated_project", updated_path)
        return StepResult(
            status="success",
            artifact_ids=[artifact_id],
            primary_artifact_id=artifact_id,
            preview_text=updated_path,
            logs=[
                "Applied parameter updates to the selected HFSS project.",
                f"Run folder: {run_dir}",
            ],
        )

    def _artifact_dir(self, session: WorkflowSession) -> str:
        target = Path(session.workspace_dir) / "artifacts"
        target.mkdir(parents=True, exist_ok=True)
        return str(target)

    def _create_run_dir(
        self,
        session: WorkflowSession,
        step_id: str,
    ) -> str:
        base_dir = Path(self._artifact_dir(session)) / step_id
        base_dir.mkdir(parents=True, exist_ok=True)
        next_run_index = int(session.steps[step_id].run_count) + 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = base_dir / f"run_{next_run_index:03d}_{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return str(run_dir)

    def _attachment_dir(self, session: WorkflowSession) -> str:
        target = Path(session.workspace_dir) / "attachments"
        target.mkdir(parents=True, exist_ok=True)
        return str(target)

    def _register_artifact(
        self,
        session: WorkflowSession,
        step_id: str,
        label: str,
        path: str,
    ) -> str:
        artifact_id = f"{step_id}-{label}"
        session.artifacts[artifact_id] = ArtifactRef(
            id=artifact_id,
            step_id=step_id,
            label=label,
            path=path,
            kind=self._classify_path(path),
        )
        return artifact_id

    def _collect_inputs(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
    ) -> Tuple[str, List[str], List[str], List[str]]:
        payload = self.build_prompt_preview_payload(definition, session)
        return (
            str(payload["final_description_text"]),
            list(payload["image_paths"]),
            list(payload["pdf_paths"]),
            list(payload["text_paths"]),
        )

    def build_prompt_preview_payload(
        self,
        definition: WorkflowStepDefinition,
        session: WorkflowSession,
        *,
        description_overrides: Optional[Dict[str, str]] = None,
    ) -> Dict[str, object]:
        input_state = session.steps.get("input")
        current_state = session.steps.get(definition.id)
        overrides = description_overrides or {}
        base_description = str(
            overrides.get("input", input_state.description if input_state else "")
        ).strip()
        current_description = str(
            overrides.get(definition.id, current_state.description if current_state else "")
        ).strip()
        refill_notes = str(current_state.refill_notes if current_state else "").strip()

        parts = [part for part in [base_description, current_description, refill_notes] if part]
        if definition.id == "solids":
            enable_25d = bool(input_state.settings.get("enable_25d", False)) if input_state else False
            parts.append(
                "There should be 2.5D element"
                if enable_25d
                else "There should be no 2.5D element"
            )
        description = "\n\n".join(parts).strip()

        attachments = []
        if input_state:
            attachments.extend(input_state.attachments)
        if current_state and definition.id != "input":
            attachments.extend(current_state.attachments)

        image_paths: List[str] = []
        pdf_paths: List[str] = []
        text_paths: List[str] = []
        unsupported_image_paths: List[str] = []
        included_attachments: List[Dict[str, str]] = []
        for attachment in attachments:
            if not attachment.enabled:
                continue
            if attachment.origin == "description":
                continue
            attachment_kind = attachment_kind_for_path(attachment.path)
            included_attachments.append(
                {
                    "id": attachment.id,
                    "name": attachment.name,
                    "kind": attachment_kind,
                    "path": attachment.path,
                    "origin": attachment.origin,
                }
            )
            extension = Path(attachment.path).suffix.lower()
            if attachment_kind == "image":
                if extension in MODEL_IMAGE_EXTENSIONS:
                    image_paths.append(attachment.path)
                else:
                    unsupported_image_paths.append(attachment.path)
            elif attachment_kind == "pdf":
                pdf_paths.append(attachment.path)
            elif attachment_kind == "text":
                text_paths.append(attachment.path)

        if unsupported_image_paths:
            raise InputValidationError(
                _format_unsupported_model_image_message(
                    unsupported_image_paths
                )
            )

        selected_artifacts: List[Dict[str, str]] = []
        for artifact_id in current_state.selected_artifact_ids if current_state else []:
            artifact = session.artifacts.get(artifact_id)
            if artifact and artifact.kind in {"text", "json", "macro"}:
                selected_artifacts.append(
                    {
                        "id": artifact.id,
                        "label": artifact.label,
                        "kind": artifact.kind,
                        "path": artifact.path,
                        "step_id": artifact.step_id,
                    }
                )
                text_paths.append(artifact.path)

        deduped_text_paths = self._dedupe_paths(text_paths)
        deduped_image_paths = self._dedupe_paths(image_paths)
        deduped_pdf_paths = self._dedupe_paths(pdf_paths)
        return {
            "final_description_text": description,
            "system_files": list(definition.system_files),
            "attachments": included_attachments,
            "selected_artifacts": selected_artifacts,
            "image_paths": deduped_image_paths,
            "pdf_paths": deduped_pdf_paths,
            "text_paths": deduped_text_paths,
        }

    def _require_selected_artifact_path(
        self,
        session: WorkflowSession,
        step_id: str,
        label: str,
    ) -> str:
        path = self._find_selected_artifact_path(session, step_id, label)
        if not path:
            raise InputValidationError(
                f"Step `{step_id}` requires upstream artifact `{label}`."
            )
        return path

    def _find_selected_artifact_path(
        self,
        session: WorkflowSession,
        step_id: str,
        label: str,
    ) -> Optional[str]:
        state = session.steps.get(step_id)
        if not state:
            return None
        for artifact_id in state.selected_artifact_ids:
            artifact = session.artifacts.get(artifact_id)
            if artifact and artifact.label == label:
                return artifact.path
        return None

    def _read_preview(self, path: str) -> str:
        extension = Path(path).suffix.lower()
        if extension not in TEXT_EXTENSIONS and not is_prompt_text_file(path):
            return path
        try:
            return read_prompt_text_file(path)
        except InputValidationError:
            return path

    def _classify_path(self, path: str) -> str:
        extension = Path(path).suffix.lower()
        if extension in IMAGE_EXTENSIONS:
            return "image"
        if extension in PDF_INPUT_EXTENSIONS:
            return "pdf"
        if extension == ".json":
            return "json"
        if extension == ".bas":
            return "macro"
        if extension in {".aedt", ".aedtz"}:
            return "hfss"
        if extension in TEXT_EXTENSIONS or is_prompt_text_file(path):
            return "text"
        if extension == ".cst":
            return "cst"
        return "file"

    @staticmethod
    def _dedupe_paths(paths: List[str]) -> List[str]:
        seen = set()
        deduped: List[str] = []
        for value in paths:
            normalized = os.path.normcase(os.path.abspath(value))
            if normalized in seen:
                continue
            deduped.append(value)
            seen.add(normalized)
        return deduped


def attachment_kind_for_path(path: str) -> str:
    """Classify an attachment by extension, then by readable text content."""

    extension = Path(path).suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in PDF_INPUT_EXTENSIONS:
        return "pdf"
    if extension in NON_TEXT_ATTACHMENT_EXTENSIONS:
        return "file"
    if extension in TEXT_EXTENSIONS or is_prompt_text_file(path):
        return "text"
    return "file"


def make_session_attachment_path(
    workspace_dir: str,
    step_id: str,
    source_name: str,
) -> str:
    """Return a unique workspace path for one copied attachment."""

    target_dir = Path(workspace_dir) / "attachments" / step_id
    target_dir.mkdir(parents=True, exist_ok=True)
    return str(target_dir / f"{uuid4().hex}_{Path(source_name).name}")
