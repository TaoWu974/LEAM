"""Workflow definitions and orchestration for the LEAM desktop app."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

from leam.backends.cst.paths import (
    prompt_path as cst_prompt_path,
)
from leam.backends.cst.paths import (
    resource_path as cst_resource_path,
)
from leam.backends.hfss.paths import (
    prompt_path as hfss_prompt_path,
)
from leam.backends.hfss.paths import (
    resource_path as hfss_resource_path,
)

from ..services.runner import DesktopWorkflowRunner
from .models import (
    ACTIVE_STEP_STATUSES,
    IssueRefill,
    StepResult,
    WorkflowSession,
    WorkflowStepDefinition,
    WorkflowStepState,
)

INPUT_STEP_ID = "input"
READY_UPSTREAM_STATUSES = {"success", "issues"}
VALID_ROUTE_TARGETS = {"parameters", "materials", "solids"}
VALID_BACKENDS = {"cst", "hfss"}


def _prompt_path_for_backend(backend: str, filename: str) -> str:
    """Return one backend-specific prompt path."""
    return (
        cst_prompt_path(filename)
        if backend == "cst"
        else hfss_prompt_path(filename)
    )


def _resource_path_for_backend(backend: str, filename: str) -> str:
    """Return one backend-specific resource path."""
    return (
        cst_resource_path(filename)
        if backend == "cst"
        else hfss_resource_path(filename)
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowEngine:
    """State machine for the LEAM desktop workflow."""

    def __init__(self, runner: Optional[DesktopWorkflowRunner] = None) -> None:
        self.runner = runner or DesktopWorkflowRunner()

    def _normalize_input_settings(self, session: WorkflowSession) -> dict:
        """Migrate legacy workflow settings and apply defaults."""
        input_state = session.steps.setdefault(INPUT_STEP_ID, WorkflowStepState())
        settings = input_state.settings

        backend = str(settings.get("backend") or "").strip().lower()
        legacy_enable_cst = settings.get("enable_cst")
        if backend not in VALID_BACKENDS:
            backend = "cst"

        if "backend" not in settings:
            settings["backend"] = "cst"
        else:
            settings["backend"] = backend

        if "enable_execution" not in settings:
            if legacy_enable_cst is not None:
                settings["enable_execution"] = bool(legacy_enable_cst)
            else:
                settings["enable_execution"] = True

        settings["template"] = str(
            settings.get("template") or "strong_description"
        ).strip() or "strong_description"
        settings["enable_25d"] = bool(settings.get("enable_25d", False))
        settings["enable_execution"] = bool(
            settings.get("enable_execution", False)
        )
        settings["enable_parameter_update"] = bool(
            settings.get("enable_parameter_update", False)
        )
        settings.pop("enable_cst", None)
        settings.pop("execution_project_path", None)
        settings.pop("overwrite_execution_project", None)
        return settings

    def _get_backend(self, session: WorkflowSession) -> str:
        """Return the normalized execution backend for the current session."""
        settings = self._normalize_input_settings(session)
        backend = str(settings.get("backend") or "cst").strip().lower()
        return backend if backend in VALID_BACKENDS else "cst"

    def _is_execution_enabled(self, session: WorkflowSession) -> bool:
        """Return whether project execution steps should be shown."""
        settings = self._normalize_input_settings(session)
        return bool(settings.get("enable_execution", False))

    def create_session(self, workspace_dir: str) -> WorkflowSession:
        session = WorkflowSession(
            workspace_dir=workspace_dir,
            created_at=_timestamp(),
            updated_at=_timestamp(),
        )
        session.steps[INPUT_STEP_ID] = WorkflowStepState(
            settings={
                "template": "strong_description",
                "enable_25d": False,
                "backend": "cst",
                "enable_execution": True,
                "enable_parameter_update": False,
            }
        )
        self.refresh_session(session)
        return session

    def serialise_session(self, session: WorkflowSession) -> Dict[str, object]:
        return asdict(session)

    def refresh_session(self, session: WorkflowSession) -> None:
        self._normalize_input_settings(session)
        session.template = self._get_template(session)
        definitions = self.build_definitions(session)
        for definition in definitions:
            session.steps.setdefault(definition.id, WorkflowStepState())
            self.ensure_default_artifact_selection(session, definition)
        self._recompute_session_status(session)

    def get_step_definitions(
        self,
        session: WorkflowSession,
    ) -> List[WorkflowStepDefinition]:
        self.refresh_session(session)
        return self.build_definitions(session)

    def get_step_definition(
        self,
        session: WorkflowSession,
        step_id: str,
    ) -> WorkflowStepDefinition:
        for definition in self.get_step_definitions(session):
            if definition.id == step_id:
                return definition
        raise KeyError(f"Unknown workflow step: {step_id}")

    def get_visible_step_definitions(
        self,
        session: WorkflowSession,
    ) -> List[WorkflowStepDefinition]:
        return [
            definition
            for definition in self.get_step_definitions(session)
            if self.is_step_visible(session, definition)
        ]

    def is_step_visible(
        self,
        session: WorkflowSession,
        definition: WorkflowStepDefinition,
    ) -> bool:
        if not definition.is_optional:
            return True
        state = session.steps.get(definition.id, WorkflowStepState())
        if state.status != "idle":
            return True
        if (
            state.description.strip()
            or state.refill_notes.strip()
            or state.attachments
            or state.selected_artifact_ids
            or state.artifact_ids
        ):
            return True
        return all(
            session.steps.get(upstream_id, WorkflowStepState()).status
            in READY_UPSTREAM_STATUSES
            for upstream_id in definition.upstream_step_ids
        )

    def get_step_blocker(
        self,
        session: WorkflowSession,
        step_id: str,
    ) -> Optional[str]:
        definition = self.get_step_definition(session, step_id)
        if step_id == INPUT_STEP_ID:
            return None

        for upstream_id in definition.upstream_step_ids:
            upstream_definition = self.get_step_definition(session, upstream_id)
            upstream_state = session.steps.get(upstream_id, WorkflowStepState())
            status = upstream_state.status
            if status == "rerun_required":
                return f"Rerun `{upstream_definition.title}` first."
            if status == "blocked_by_upstream":
                return f"`{upstream_definition.title}` is blocked by an earlier step."
            if status == "error":
                return f"Fix `{upstream_definition.title}` first."
            if status == "stale":
                return f"Rerun `{upstream_definition.title}` first."
            if status not in READY_UPSTREAM_STATUSES:
                return f"Run `{upstream_definition.title}` first."
            if upstream_id != INPUT_STEP_ID and not upstream_state.artifact_ids:
                return f"`{upstream_definition.title}` has no outputs yet."
        return None

    def get_display_status(
        self,
        session: WorkflowSession,
        step_id: str,
    ) -> str:
        state = session.steps.get(step_id, WorkflowStepState())
        if state.status == "idle" and self.get_step_blocker(session, step_id):
            return "waiting"
        return state.status

    def get_available_artifacts(
        self,
        session: WorkflowSession,
        step_id: str,
    ) -> List[object]:
        definition = self.get_step_definition(session, step_id)
        available = []
        for upstream_id in definition.upstream_step_ids:
            upstream_state = session.steps.get(upstream_id)
            if not upstream_state:
                continue
            for artifact_id in upstream_state.artifact_ids:
                artifact = session.artifacts.get(artifact_id)
                if artifact:
                    available.append(artifact)
        return available

    def ensure_default_artifact_selection(
        self,
        session: WorkflowSession,
        definition: WorkflowStepDefinition,
    ) -> None:
        state = session.steps.setdefault(definition.id, WorkflowStepState())
        if state.settings.get("artifact_selection_touched"):
            state.selected_artifact_ids = [
                artifact_id
                for artifact_id in state.selected_artifact_ids
                if artifact_id in session.artifacts
            ]
            return

        selected_ids: List[str] = []
        for upstream_id in definition.upstream_step_ids:
            requested_labels = definition.default_selected_outputs.get(
                upstream_id,
                [],
            )
            upstream_state = session.steps.get(upstream_id)
            if not upstream_state:
                continue
            available = [
                session.artifacts[artifact_id]
                for artifact_id in upstream_state.artifact_ids
                if artifact_id in session.artifacts
            ]
            if not requested_labels:
                selected_ids.extend(artifact.id for artifact in available)
                continue
            for label in requested_labels:
                for artifact in available:
                    if artifact.label == label:
                        selected_ids.append(artifact.id)
                        break
        state.selected_artifact_ids = selected_ids

    def build_definitions(
        self,
        session: WorkflowSession,
    ) -> List[WorkflowStepDefinition]:
        template = self._get_template(session)
        backend = self._get_backend(session)
        input_state = session.steps.get(INPUT_STEP_ID, WorkflowStepState())
        enable_25d = bool(input_state.settings.get("enable_25d", False))
        enable_execution = self._is_execution_enabled(session)
        enable_parameter_update = bool(
            input_state.settings.get("enable_parameter_update", False)
        )

        def prompt_path(filename: str) -> str:
            return _prompt_path_for_backend(backend, filename)

        def resource_path(filename: str) -> str:
            return _resource_path_for_backend(backend, filename)

        parameter_script_label = "parameters_bas" if backend == "cst" else "parameters_py"
        materials_script_label = "materials_bas" if backend == "cst" else "materials_json"
        model_3d_label = "model_3d_bas" if backend == "cst" else "model_3d_py"
        model_2d_label = "model_2d_bas" if backend == "cst" else "model_2d_py"

        definitions = [
            WorkflowStepDefinition(
                id=INPUT_STEP_ID,
                title="Workspace Setup",
                step_type="input",
            )
        ]

        if template == "weak_description":
            definitions.append(
                WorkflowStepDefinition(
                    id="initial_solids",
                    title="Initial Solids",
                    step_type="initial_solids",
                    system_files=[
                        prompt_path("weak_description_to_solids.md"),
                        resource_path("modeling_2d.md"),
                        resource_path("modeling_3d.md"),
                    ],
                    upstream_step_ids=[INPUT_STEP_ID],
                )
            )
            parameter_upstream = ["initial_solids"]
            parameter_defaults = {"initial_solids": ["solids_json"]}
            materials_upstream = ["initial_solids"]
            materials_defaults = {"initial_solids": ["solids_json"]}
            solids_upstream = ["initial_solids", "parameters", "materials"]
            solids_defaults = {
                "initial_solids": ["solids_json"],
                "parameters": ["parameters_json"],
                "materials": ["materials_json"],
            }
            solids_system = [
                prompt_path("weak_description_to_solids.md"),
                resource_path("modeling_2d.md"),
                resource_path("modeling_3d.md"),
            ]
        else:
            parameter_upstream = [INPUT_STEP_ID]
            parameter_defaults = {}
            materials_upstream = [INPUT_STEP_ID]
            materials_defaults = {}
            solids_upstream = ["parameters", "materials"]
            solids_defaults = {
                "parameters": ["parameters_json"],
                "materials": ["materials_json"],
            }
            solids_system = [prompt_path("strong_description_to_solids.md")]

        definitions.extend(
            [
                WorkflowStepDefinition(
                    id="parameters",
                    title="Parameters",
                    step_type="parameters",
                    system_files=[prompt_path("parameter_prompt.md")],
                    upstream_step_ids=parameter_upstream,
                    default_selected_outputs=parameter_defaults,
                ),
                WorkflowStepDefinition(
                    id="materials",
                    title="Materials",
                    step_type="materials",
                    system_files=(
                        [
                            prompt_path("materials_extract_prompt.md"),
                            prompt_path("materials_vba_prompt.md"),
                        ]
                        if backend == "cst"
                        else [
                            prompt_path("materials_extract_prompt.md"),
                            resource_path("material_list.md"),
                        ]
                    ),
                    upstream_step_ids=materials_upstream,
                    default_selected_outputs=materials_defaults,
                ),
                WorkflowStepDefinition(
                    id="solids",
                    title="Solids",
                    step_type="solids",
                    system_files=solids_system,
                    upstream_step_ids=solids_upstream,
                    default_selected_outputs=solids_defaults,
                ),
                WorkflowStepDefinition(
                    id="check_solid",
                    title="Check Solid",
                    step_type="check_solid",
                    system_files=[prompt_path("check_solid_prompt.md")],
                    upstream_step_ids=["solids", "parameters", "materials"],
                    default_selected_outputs={
                        "solids": ["solids_json"],
                        "parameters": ["parameters_json"],
                        "materials": ["materials_json"],
                    },
                ),
                WorkflowStepDefinition(
                    id="dimensions",
                    title="Dimensions",
                    step_type="dimensions",
                    system_files=[prompt_path("dimension_prompt.md")],
                    upstream_step_ids=["solids", "parameters"],
                    default_selected_outputs={
                        "solids": ["solids_json"],
                        "parameters": [
                            parameter_script_label
                            if backend == "cst"
                            else "parameters_json"
                        ],
                    },
                ),
                WorkflowStepDefinition(
                    id="model_3d",
                    title="3D Model",
                    step_type="model_3d",
                    system_files=[
                        prompt_path("modeling_3d_prompt.md"),
                        resource_path("modeling_3d.md"),
                    ],
                    upstream_step_ids=["parameters", "dimensions", "materials"],
                    default_selected_outputs={
                        "parameters": [
                            parameter_script_label
                            if backend == "cst"
                            else "parameters_json"
                        ],
                        "dimensions": ["dimensions_json"],
                        "materials": [materials_script_label],
                    },
                ),
            ]
        )

        if enable_25d:
            definitions.append(
                WorkflowStepDefinition(
                    id="model_2d",
                    title="2.5D Model",
                    step_type="model_2d",
                    system_files=[
                        prompt_path("modeling_2d_prompt.md"),
                        resource_path("modeling_2d.md"),
                        resource_path("extrude.md"),
                    ],
                    upstream_step_ids=[
                        "parameters",
                        "dimensions",
                        "materials",
                        "model_3d",
                    ],
                    default_selected_outputs={
                        "parameters": [
                            parameter_script_label
                            if backend == "cst"
                            else "parameters_json"
                        ],
                        "dimensions": ["dimensions_json"],
                        "materials": [materials_script_label],
                        "model_3d": [model_3d_label],
                    },
                )
            )

        boolean_upstream = ["parameters", "dimensions", "model_3d"]
        boolean_defaults = {
            "parameters": [
                parameter_script_label if backend == "cst" else "parameters_json"
            ],
            "dimensions": ["dimensions_json"],
            "model_3d": [model_3d_label],
        }
        if enable_25d:
            boolean_upstream.append("model_2d")
            boolean_defaults["model_2d"] = [model_2d_label]
        definitions.append(
            WorkflowStepDefinition(
                id="boolean",
                title="Boolean Operations",
                step_type="boolean",
                system_files=[
                    prompt_path("boolean_prompt.md"),
                    resource_path("boolean_operations.md"),
                ],
                upstream_step_ids=boolean_upstream,
                default_selected_outputs=boolean_defaults,
            )
        )

        if enable_execution and backend == "cst":
            cst_upstream = ["parameters", "materials", "model_3d", "boolean"]
            cst_defaults = {
                "parameters": ["parameters_bas"],
                "materials": ["materials_bas"],
                "model_3d": ["model_3d_bas"],
                "boolean": ["boolean_bas"],
            }
            if enable_25d:
                cst_upstream.insert(3, "model_2d")
                cst_defaults["model_2d"] = ["model_2d_bas"]
            definitions.append(
                WorkflowStepDefinition(
                    id="cst_project",
                    title="CST Project",
                    step_type="cst_project",
                    upstream_step_ids=cst_upstream,
                    default_selected_outputs=cst_defaults,
                    is_optional=True,
                )
            )
        elif enable_execution and backend == "hfss":
            hfss_upstream = ["parameters", "materials", "model_3d", "boolean"]
            hfss_defaults = {
                "parameters": ["parameters_py"],
                "materials": ["materials_json"],
                "model_3d": ["model_3d_py"],
                "boolean": ["boolean_py"],
            }
            if enable_25d:
                hfss_upstream.insert(3, "model_2d")
                hfss_defaults["model_2d"] = ["model_2d_py"]
            definitions.append(
                WorkflowStepDefinition(
                    id="hfss_project",
                    title="HFSS Project",
                    step_type="hfss_project",
                    upstream_step_ids=hfss_upstream,
                    default_selected_outputs=hfss_defaults,
                    is_optional=True,
                )
            )

        if enable_parameter_update:
            definitions.append(
                WorkflowStepDefinition(
                    id="parameter_update",
                    title="Parameter Update",
                    step_type="parameter_update",
                    system_files=[prompt_path("parameter_update_prompt.md")],
                    upstream_step_ids=["dimensions", "parameters"],
                    default_selected_outputs={
                        "dimensions": ["dimensions_json"],
                        "parameters": [
                            parameter_script_label
                            if backend == "cst"
                            else "parameters_json"
                        ],
                    },
                    is_optional=True,
                )
            )
            if enable_execution and backend == "cst":
                definitions.append(
                    WorkflowStepDefinition(
                        id="cst_update",
                        title="CST Update",
                        step_type="cst_update",
                        upstream_step_ids=["cst_project", "parameter_update"],
                        default_selected_outputs={
                            "cst_project": ["cst_project"],
                            "parameter_update": ["parameter_update_bas"],
                        },
                        is_optional=True,
                    )
                )
            elif enable_execution and backend == "hfss":
                definitions.append(
                    WorkflowStepDefinition(
                        id="hfss_update",
                        title="HFSS Update",
                        step_type="hfss_update",
                        upstream_step_ids=["hfss_project", "parameter_update"],
                        default_selected_outputs={
                            "hfss_project": ["hfss_project"],
                            "parameter_update": ["parameter_update_py"],
                        },
                        is_optional=True,
                    )
                )

        return definitions

    def run_step(self, session: WorkflowSession, step_id: str) -> StepResult:
        self.refresh_session(session)
        definition = self.get_step_definition(session, step_id)
        state = session.steps[step_id]
        previous_status = state.status

        if step_id == INPUT_STEP_ID:
            state.status = "success"
            state.last_error = ""
            state.last_run_at = _timestamp()
            state.run_count += 1
            session.template = self._get_template(session)
            self.refresh_session(session)
            return StepResult(
                status="success",
                logs=["Saved workflow description and branch selections."],
            )

        if any(
            session.steps.get(upstream_id, WorkflowStepState()).status
            == "rerun_required"
            for upstream_id in definition.upstream_step_ids
        ):
            state.status = "blocked_by_upstream"
            state.logs = ["Step blocked by an upstream `rerun_required` state."]
            state.last_error = "One or more upstream steps require rerun first."
            self._recompute_session_status(session)
            return StepResult(
                status="blocked_by_upstream",
                logs=list(state.logs),
                error=state.last_error,
            )

        state.status = "running"
        state.last_error = ""
        state.logs = [f"Running {definition.title}..."]

        try:
            result = self.runner.run(definition, session)
        except Exception as exc:
            state.status = "error"
            state.last_error = str(exc)
            state.last_run_at = _timestamp()
            state.logs = [f"{definition.title} failed.", str(exc)]
            self._recompute_session_status(session)
            raise

        state.logs = list(result.logs)
        state.last_error = result.error
        state.last_run_at = _timestamp()
        state.run_count += 1
        state.raw_issues = list(result.raw_payload.get("issues", []) or [])
        state.issues = []
        state.artifact_ids = [
            artifact_id
            for artifact_id in result.artifact_ids
            if artifact_id in session.artifacts
        ]

        if step_id == "solids":
            session.flags["has_25d"] = self.runner.detect_25d_from_artifacts(
                session,
                state.artifact_ids,
            )
            self.refresh_session(session)

        if step_id == "check_solid":
            raw_status = str(result.raw_payload.get("status") or result.status)
            if raw_status == "issues":
                state.status = "issues"
                session.issues = self.apply_check_refills(
                    session,
                    definition,
                    state.raw_issues,
                )
            else:
                state.status = "success"
                session.issues = []
        else:
            state.status = result.status
            if previous_status in {"success", "issues", "stale", "rerun_required"}:
                self._mark_descendants_stale(session, step_id)

        self._reconcile_dependency_statuses(session)
        self._recompute_session_status(session)
        return result

    def apply_check_refills(
        self,
        session: WorkflowSession,
        definition: WorkflowStepDefinition,
        issues: Iterable[dict],
    ) -> List[IssueRefill]:
        routed: List[IssueRefill] = []
        grouped: Dict[str, List[IssueRefill]] = defaultdict(list)
        for issue in issues:
            if str(issue.get("severity") or "error") == "warning":
                continue
            target_step_id = self._route_issue_target(issue)
            refill = IssueRefill(
                id=f"issue-{uuid4().hex}",
                source_step_id=definition.id,
                target_step_id=target_step_id,
                category=str(issue.get("category") or "alignment"),
                severity=str(issue.get("severity") or "error"),
                message=str(issue.get("issue") or "Unknown solids issue."),
                issue_path=issue.get("path"),
                solid=issue.get("solid"),
            )
            grouped[target_step_id].append(refill)
            routed.append(refill)

        for target_step_id, target_issues in grouped.items():
            target_state = session.steps.setdefault(target_step_id, WorkflowStepState())
            lines = [
                "The previous `check_solid` run found the issue(s) below.",
                "Fix them in this step and rerun to regenerate a complete result.",
                "",
            ]
            for refill in target_issues:
                scope = []
                if refill.category:
                    scope.append(refill.category)
                if refill.solid:
                    scope.append(f"solid={refill.solid}")
                if refill.issue_path:
                    scope.append(f"path={refill.issue_path}")
                prefix = f"[{', '.join(scope)}] " if scope else ""
                lines.append(f"- {prefix}{refill.message}")
            inserted_text = "\n".join(lines).strip()
            target_issues[0].inserted_text = inserted_text
            if inserted_text and inserted_text not in target_state.refill_notes:
                target_state.refill_notes = (
                    f"{target_state.refill_notes.rstrip()}\n\n{inserted_text}".strip()
                )
            target_state.issues = target_issues
            target_state.status = "rerun_required"

        self._reconcile_dependency_statuses(session)
        return routed

    def _get_template(self, session: WorkflowSession) -> str:
        input_state = session.steps.get(INPUT_STEP_ID, WorkflowStepState())
        template = str(
            input_state.settings.get("template")
            or session.template
            or "strong_description"
        ).strip()
        if template not in {
            "paper_reconstruction",
            "strong_description",
            "weak_description",
        }:
            return "strong_description"
        return template

    def _route_issue_target(self, issue: dict) -> str:
        route_to = str(issue.get("route_to") or "").strip().lower()
        if route_to in VALID_ROUTE_TARGETS:
            return route_to
        category = str(issue.get("category") or "").lower()
        issue_path = str(issue.get("path") or "").lower()
        if category == "parameters" or "parameter" in issue_path:
            return "parameters"
        if category == "materials" or "material" in issue_path:
            return "materials"
        if category in {"alignment", "operations"}:
            return "solids"
        if issue_path.startswith("solids"):
            return "solids"
        return "solids"

    def _mark_descendants_stale(
        self,
        session: WorkflowSession,
        step_id: str,
    ) -> None:
        step_ids = [definition.id for definition in self.build_definitions(session)]
        if step_id not in step_ids:
            return
        position = step_ids.index(step_id)
        for descendant_id in step_ids[position + 1 :]:
            descendant_state = session.steps.get(descendant_id)
            if not descendant_state:
                continue
            if descendant_state.status in {"success", "issues", "stale"}:
                descendant_state.status = "stale"

    def _reconcile_dependency_statuses(self, session: WorkflowSession) -> None:
        step_ids = [definition.id for definition in self.build_definitions(session)]
        rerun_indices = {
            index
            for index, step_id in enumerate(step_ids)
            if session.steps.get(step_id, WorkflowStepState()).status
            == "rerun_required"
        }
        for index, step_id in enumerate(step_ids):
            state = session.steps.get(step_id)
            if not state:
                continue
            if state.status not in ACTIVE_STEP_STATUSES:
                state.status = "idle"
            if any(rerun_index < index for rerun_index in rerun_indices):
                if state.status not in {"rerun_required", "running"}:
                    state.status = "blocked_by_upstream"
            elif state.status == "blocked_by_upstream":
                state.status = "stale"

    def _recompute_session_status(self, session: WorkflowSession) -> None:
        statuses = [state.status for state in session.steps.values()]
        if any(status == "error" for status in statuses):
            session.status = "error"
        elif any(status == "rerun_required" for status in statuses):
            session.status = "needs_attention"
        elif any(status == "running" for status in statuses):
            session.status = "running"
        elif any(status == "blocked_by_upstream" for status in statuses):
            session.status = "blocked"
        elif any(status in {"success", "issues", "stale"} for status in statuses):
            session.status = "active"
        else:
            session.status = "draft"
        session.updated_at = _timestamp()
