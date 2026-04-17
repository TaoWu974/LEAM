"""Session persistence for the LEAM desktop app."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ...utils.path_utils import absolute_path_text, canonical_path_text
from ..services.runner import attachment_kind_for_path, make_session_attachment_path
from ..workflow.models import (
    ArtifactRef,
    AttachmentRef,
    WorkflowSession,
    WorkflowStepState,
)

DEFAULT_RECENTS_PATH = (
    Path.home() / ".leam" / "desktop_recent_sessions.json"
)
DEFAULT_OUTPUT_ROOT = Path.home() / ".leam" / "workspaces"
RUN_DIR_PATTERN = re.compile(r"run_(\d+)_")
WORKSPACE_NAME_PATTERN = re.compile(
    r"(?P<title>.+?)(?:_(?P<backend>cst|hfss))?_(?P<stamp>\d{8}_\d{6})$"
)
WORKSPACE_BACKENDS = {"cst", "hfss"}

ARTIFACT_LABELS_BY_STEP = {
    "initial_solids": {
        "initial_solids.json": "solids_json",
        "solids.json": "solids_json",
    },
    "parameters": {
        "parameters.bas": "parameters_bas",
        "parameters.py": "parameters_py",
        "parameters.json": "parameters_json",
    },
    "materials": {
        "materials.bas": "materials_bas",
        "materials.json": "materials_json",
    },
    "solids": {
        "solids.json": "solids_json",
    },
    "check_solid": {
        "solids_check.json": "check_solid_report",
    },
    "dimensions": {
        "dimensions.json": "dimensions_json",
    },
    "model_3d": {
        "model_3d.bas": "model_3d_bas",
        "model_3d.py": "model_3d_py",
    },
    "model_2d": {
        "model_2d.bas": "model_2d_bas",
        "model_2d.py": "model_2d_py",
    },
    "boolean": {
        "boolean.bas": "boolean_bas",
        "boolean.py": "boolean_py",
        "boolean_ops.py": "boolean_py",
    },
    "parameter_update": {
        "parameter_update.bas": "parameter_update_bas",
        "parameter_update.py": "parameter_update_py",
    },
}


def sanitize_path_component(value: str, default: str = "item") -> str:
    """Normalise one generated path component to an underscore-only form."""

    cleaned = re.sub(r"\s+", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("._")
    return cleaned or default


def sanitize_leaf_filename(filename: str, default_stem: str = "attachment") -> str:
    """Sanitise a generated filename while preserving its extension."""

    path = Path(filename)
    suffix = "".join(path.suffixes)
    stem = path.name[: -len(suffix)] if suffix else path.name
    safe_stem = sanitize_path_component(stem, default_stem)
    safe_suffix = suffix.replace(" ", "_")
    return f"{safe_stem}{safe_suffix}"


class DesktopSessionStore:
    """Save and load workflow sessions from JSON files."""

    def default_workspace_root(self) -> str:
        target = DEFAULT_OUTPUT_ROOT
        target.mkdir(parents=True, exist_ok=True)
        return str(target)

    def create_workspace(
        self,
        title: str = "session",
        output_root: Optional[str] = None,
        backend: Optional[str] = "cst",
    ) -> str:
        root = Path(output_root or self.default_workspace_root())
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = root / self._workspace_folder_name(title, backend, stamp)
        target.mkdir(parents=True, exist_ok=True)
        (target / "artifacts").mkdir(exist_ok=True)
        (target / "attachments").mkdir(exist_ok=True)
        return str(target)

    def ensure_workspace_backend_name(
        self,
        session: WorkflowSession,
        backend: Optional[str],
    ) -> str:
        current_workspace = Path(session.workspace_dir)
        if not session.workspace_dir or not current_workspace.exists():
            return session.workspace_dir

        normalized_backend = self._normalize_workspace_backend(backend)
        if not normalized_backend:
            return session.workspace_dir

        stamp = self._workspace_stamp(current_workspace.name) or datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        target_name = self._workspace_folder_name(
            session.title or self._workspace_title(current_workspace),
            normalized_backend,
            stamp,
        )
        if current_workspace.name == target_name:
            return session.workspace_dir

        target_workspace = current_workspace.with_name(target_name)
        if target_workspace.exists():
            return session.workspace_dir

        shutil.move(str(current_workspace), str(target_workspace))
        self._remap_session_workspace_paths(
            session,
            old_root=current_workspace,
            new_root=target_workspace,
        )
        return str(target_workspace)

    def save_session(
        self,
        session: WorkflowSession,
        payload: dict,
        path: Optional[str] = None,
    ) -> str:
        target = Path(
            path or session.session_file or Path(session.workspace_dir) / "session.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        workspace_root = Path(absolute_path_text(session.workspace_dir or target.parent))
        target = Path(absolute_path_text(target))
        serializable_payload = self._serializable_session_payload(
            payload,
            workspace_root=workspace_root,
            session_file=target,
        )
        with open(target, "w", encoding="utf-8") as output_file:
            json.dump(serializable_payload, output_file, indent=2)
            output_file.write("\n")
        session.session_file = str(target)
        return str(target)

    def load_session(self, path: str) -> WorkflowSession:
        target = Path(absolute_path_text(path))
        with open(target, "r", encoding="utf-8") as source:
            payload = json.load(source)
        session = WorkflowSession.from_dict(payload)
        workspace_root = self._load_workspace_root(payload, target)
        self._resolve_loaded_session_workspace_paths(
            session,
            workspace_root=workspace_root,
            session_file=target,
        )
        return session

    def load_workspace(self, path: str) -> WorkflowSession:
        """Load one workspace folder, preferring `session.json` when available."""
        target = Path(path)
        if target.is_file():
            if target.suffix.lower() == ".json":
                return self.load_session(str(target))
            raise FileNotFoundError(f"Workspace path is not a directory: {path}")
        if not target.exists():
            raise FileNotFoundError(f"Workspace folder not found: {path}")

        session_path = target / "session.json"
        if session_path.exists():
            return self.load_session(str(session_path))
        return self._reconstruct_workspace(target)

    def _reconstruct_workspace(self, workspace: Path) -> WorkflowSession:
        """Rebuild one best-effort session from a workspace folder."""
        workspace = Path(absolute_path_text(workspace))
        artifacts_root = workspace / "artifacts"
        attachments_root = workspace / "attachments"
        now = datetime.now().isoformat()
        session = WorkflowSession(
            title=self._workspace_title(workspace),
            template="strong_description",
            workspace_dir=str(workspace),
            session_file=str(workspace / "session.json"),
            created_at=now,
            updated_at=now,
        )
        session.flags["reconstructed_from_workspace"] = True

        if attachments_root.exists():
            self._restore_workspace_attachments(session, attachments_root)
        artifact_modified_at = self._restore_workspace_artifacts(session, artifacts_root)

        backend = self._infer_backend(session)
        has_25d = self._detect_has_25d(session)
        enable_parameter_update = bool(
            session.steps.get("parameter_update", WorkflowStepState()).description.strip()
            or session.steps.get("parameter_update", WorkflowStepState()).artifact_ids
            or session.steps.get("cst_update", WorkflowStepState()).artifact_ids
            or session.steps.get("hfss_update", WorkflowStepState()).artifact_ids
        )
        if "initial_solids" in session.steps and session.steps["initial_solids"].artifact_ids:
            session.template = "weak_description"

        input_state = session.steps.setdefault("input", WorkflowStepState())
        input_state.settings.update(
            {
                "template": session.template,
                "enable_25d": has_25d,
                "backend": backend,
                "enable_execution": True,
                "enable_parameter_update": enable_parameter_update,
            }
        )
        session.flags["has_25d"] = has_25d
        if artifact_modified_at:
            session.updated_at = artifact_modified_at
        return session

    def _restore_workspace_attachments(
        self,
        session: WorkflowSession,
        attachments_root: Path,
    ) -> None:
        """Restore attachment refs and description text from workspace files."""
        for step_dir in sorted(
            (path for path in attachments_root.iterdir() if path.is_dir()),
            key=lambda item: item.name,
        ):
            step_id = step_dir.name
            state = session.steps.setdefault(step_id, WorkflowStepState())
            for file_path in sorted(
                (path for path in step_dir.iterdir() if path.is_file()),
                key=lambda item: item.name,
            ):
                is_description = file_path.name == "description.txt"
                attachment = AttachmentRef(
                    id=(
                        f"attachment-{step_id}-description"
                        if is_description
                        else f"attachment-{step_id}-{file_path.stem}"
                    ),
                    name=file_path.name,
                    path=str(file_path),
                    kind=attachment_kind_for_path(str(file_path)),
                    editable=attachment_kind_for_path(str(file_path)) == "text",
                    origin="description" if is_description else "user",
                )
                state.attachments.append(attachment)
                if is_description:
                    try:
                        state.description = file_path.read_text(encoding="utf-8")
                    except Exception:
                        state.description = ""

    def _restore_workspace_artifacts(
        self,
        session: WorkflowSession,
        artifacts_root: Path,
    ) -> Optional[str]:
        """Restore latest artifact refs per step from one workspace folder."""
        if not artifacts_root.exists():
            return None

        latest_updated_at: Optional[str] = None
        for step_dir in sorted(
            (path for path in artifacts_root.iterdir() if path.is_dir()),
            key=lambda item: item.name,
        ):
            step_id = step_dir.name
            state = session.steps.setdefault(step_id, WorkflowStepState())
            discovered: Dict[str, tuple[int, float, Path]] = {}
            max_run_index = 0
            latest_mtime = 0.0
            latest_report_payload = None
            for run_dir in sorted(
                (path for path in step_dir.iterdir() if path.is_dir()),
                key=lambda item: item.name,
            ):
                run_index = self._run_index(run_dir.name)
                max_run_index = max(max_run_index, run_index)
                for file_path in sorted(
                    (path for path in run_dir.iterdir() if path.is_file()),
                    key=lambda item: item.name,
                ):
                    label = self._artifact_label_for_file(step_id, file_path)
                    if not label:
                        continue
                    stat = file_path.stat()
                    latest_mtime = max(latest_mtime, stat.st_mtime)
                    discovered[label] = (run_index, stat.st_mtime, file_path)
                    if step_id == "check_solid" and file_path.name == "solids_check.json":
                        try:
                            latest_report_payload = json.loads(
                                file_path.read_text(encoding="utf-8")
                            )
                        except Exception:
                            latest_report_payload = None

            if not discovered:
                continue

            state.artifact_ids = []
            for label, (_, _, file_path) in sorted(
                discovered.items(),
                key=lambda item: item[0],
            ):
                artifact_id = f"{step_id}-{label}"
                session.artifacts[artifact_id] = ArtifactRef(
                    id=artifact_id,
                    step_id=step_id,
                    label=label,
                    path=str(file_path),
                    kind=self._classify_artifact_path(str(file_path)),
                )
                state.artifact_ids.append(artifact_id)

            state.run_count = max_run_index or len(
                [path for path in step_dir.iterdir() if path.is_dir()]
            )
            if latest_mtime:
                state.last_run_at = datetime.fromtimestamp(latest_mtime).isoformat()
                if latest_updated_at is None or state.last_run_at > latest_updated_at:
                    latest_updated_at = state.last_run_at
            state.logs = ["Reconstructed from workspace artifacts."]
            state.status = "success"

            if step_id == "check_solid" and isinstance(latest_report_payload, dict):
                state.raw_issues = [
                    item
                    for item in latest_report_payload.get("issues", []) or []
                    if isinstance(item, dict)
                ]
                if str(latest_report_payload.get("status") or "").strip().lower() == "issues":
                    state.status = "issues"

        return latest_updated_at

    def _infer_backend(self, session: WorkflowSession) -> str:
        """Infer the simulator backend from reconstructed artifact labels."""
        labels = {artifact.label for artifact in session.artifacts.values()}
        if any(label.endswith("_py") or label.startswith("hfss_") for label in labels):
            return "hfss"
        if any(label.endswith("_bas") or label.startswith("cst_") for label in labels):
            return "cst"
        kinds = {artifact.kind for artifact in session.artifacts.values()}
        if "hfss" in kinds:
            return "hfss"
        return "cst"

    def _detect_has_25d(self, session: WorkflowSession) -> bool:
        """Infer whether the workspace contains one 2.5D branch."""
        if session.steps.get("model_2d", WorkflowStepState()).artifact_ids:
            return True
        solids_artifact = session.artifacts.get("solids-solids_json")
        if not solids_artifact:
            return False
        try:
            payload = json.loads(Path(solids_artifact.path).read_text(encoding="utf-8"))
        except Exception:
            return False
        solids = payload.get("solids", []) if isinstance(payload, dict) else []
        return any(
            str(item.get("Type") or "").strip() == "2.5D"
            for item in solids
            if isinstance(item, dict)
        )

    @staticmethod
    def _workspace_title(workspace: Path) -> str:
        """Infer one human-readable title from the workspace folder name."""
        match = WORKSPACE_NAME_PATTERN.match(workspace.name)
        stem = match.group("title") if match else workspace.name
        return stem.replace("_", " ")

    @staticmethod
    def _workspace_stamp(workspace_name: str) -> Optional[str]:
        match = WORKSPACE_NAME_PATTERN.match(workspace_name)
        return match.group("stamp") if match else None

    @staticmethod
    def _normalize_workspace_backend(backend: Optional[str]) -> Optional[str]:
        value = str(backend or "").strip().lower()
        return value if value in WORKSPACE_BACKENDS else None

    @classmethod
    def _workspace_folder_name(
        cls,
        title: str,
        backend: Optional[str],
        stamp: str,
    ) -> str:
        safe_title = sanitize_path_component(title, "session")
        normalized_backend = cls._normalize_workspace_backend(backend)
        if normalized_backend:
            return f"{safe_title}_{normalized_backend}_{stamp}"
        return f"{safe_title}_{stamp}"

    @staticmethod
    def _path_is_within(candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
        except ValueError:
            return False
        return True

    @classmethod
    def _serialize_workspace_path(
        cls,
        value: Optional[str],
        *,
        workspace_root: Path,
    ) -> Optional[str]:
        if not value:
            return value
        candidate = Path(str(value))
        if not candidate.is_absolute():
            return str(candidate)
        candidate = Path(absolute_path_text(candidate))
        if candidate == workspace_root:
            return "."
        if cls._path_is_within(candidate, workspace_root):
            return str(candidate.relative_to(workspace_root))
        return str(candidate)

    @staticmethod
    def _resolve_workspace_path(
        value: Optional[str],
        *,
        workspace_root: Path,
    ) -> Optional[str]:
        if not value:
            return value
        candidate = Path(str(value))
        if candidate == Path("."):
            return str(workspace_root)
        if candidate.is_absolute():
            return absolute_path_text(candidate)
        return absolute_path_text(workspace_root / candidate)

    @classmethod
    def _serializable_session_payload(
        cls,
        payload: dict,
        *,
        workspace_root: Path,
        session_file: Path,
    ) -> dict:
        serializable = copy.deepcopy(payload)
        try:
            serializable["workspace_dir"] = os.path.relpath(
                str(workspace_root),
                start=str(session_file.parent),
            )
        except ValueError:
            serializable["workspace_dir"] = str(workspace_root)
        serializable["session_file"] = cls._serialize_workspace_path(
            str(session_file),
            workspace_root=workspace_root,
        )

        for artifact in (serializable.get("artifacts") or {}).values():
            if isinstance(artifact, dict) and "path" in artifact:
                artifact["path"] = cls._serialize_workspace_path(
                    artifact.get("path"),
                    workspace_root=workspace_root,
                )

        for issue in serializable.get("issues", []) or []:
            if isinstance(issue, dict) and "issue_path" in issue:
                issue["issue_path"] = cls._serialize_workspace_path(
                    issue.get("issue_path"),
                    workspace_root=workspace_root,
                )

        for state in (serializable.get("steps") or {}).values():
            if not isinstance(state, dict):
                continue
            for attachment in state.get("attachments", []) or []:
                if isinstance(attachment, dict) and "path" in attachment:
                    attachment["path"] = cls._serialize_workspace_path(
                        attachment.get("path"),
                        workspace_root=workspace_root,
                    )
            settings = state.get("settings") or {}
            if isinstance(settings, dict) and "last_run_dir" in settings:
                settings["last_run_dir"] = cls._serialize_workspace_path(
                    settings.get("last_run_dir"),
                    workspace_root=workspace_root,
                )
            for issue in state.get("issues", []) or []:
                if isinstance(issue, dict) and "issue_path" in issue:
                    issue["issue_path"] = cls._serialize_workspace_path(
                        issue.get("issue_path"),
                        workspace_root=workspace_root,
                    )
            for raw_issue in state.get("raw_issues", []) or []:
                if not isinstance(raw_issue, dict):
                    continue
                for key in ("path", "issue_path"):
                    if key in raw_issue:
                        raw_issue[key] = cls._serialize_workspace_path(
                            raw_issue.get(key),
                            workspace_root=workspace_root,
                        )

        return serializable

    @staticmethod
    def _load_workspace_root(payload: dict, session_file: Path) -> Path:
        raw_workspace = payload.get("workspace_dir")
        if raw_workspace in (None, "", "."):
            return Path(absolute_path_text(session_file.parent))
        workspace = Path(str(raw_workspace))
        if workspace.is_absolute():
            return Path(absolute_path_text(workspace))
        return Path(absolute_path_text(session_file.parent / workspace))

    @classmethod
    def _resolve_loaded_session_workspace_paths(
        cls,
        session: WorkflowSession,
        *,
        workspace_root: Path,
        session_file: Path,
    ) -> None:
        session.workspace_dir = str(workspace_root)
        session.session_file = str(session_file)
        for artifact in session.artifacts.values():
            artifact.path = str(
                cls._resolve_workspace_path(
                    artifact.path,
                    workspace_root=workspace_root,
                )
                or artifact.path
            )
        for issue in session.issues:
            issue.issue_path = cls._resolve_workspace_path(
                issue.issue_path,
                workspace_root=workspace_root,
            )
        for state in session.steps.values():
            for attachment in state.attachments:
                attachment.path = str(
                    cls._resolve_workspace_path(
                        attachment.path,
                        workspace_root=workspace_root,
                    )
                    or attachment.path
                )
                if attachment.origin == "description":
                    attachment.kind = "text"
                    attachment.editable = True
                else:
                    attachment.kind = attachment_kind_for_path(attachment.path)
                    attachment.editable = attachment.kind == "text"
            last_run_dir = state.settings.get("last_run_dir")
            resolved_run_dir = cls._resolve_workspace_path(
                str(last_run_dir) if last_run_dir else None,
                workspace_root=workspace_root,
            )
            if resolved_run_dir:
                state.settings["last_run_dir"] = resolved_run_dir
            for issue in state.issues:
                issue.issue_path = cls._resolve_workspace_path(
                    issue.issue_path,
                    workspace_root=workspace_root,
                )
            for payload in state.raw_issues:
                for key in ("path", "issue_path"):
                    if key in payload:
                        payload[key] = cls._resolve_workspace_path(
                            str(payload.get(key) or ""),
                            workspace_root=workspace_root,
                        )

    @staticmethod
    def _remap_workspace_path(
        value: Optional[str],
        *,
        old_root: Path,
        new_root: Path,
    ) -> Optional[str]:
        if not value:
            return value
        old_prefix = str(old_root)
        text = str(value)
        if text == old_prefix:
            return str(new_root)
        prefix = old_prefix + os.sep
        if text.startswith(prefix):
            suffix = text[len(prefix) :]
            return str(new_root / suffix)
        return value

    def _remap_session_workspace_paths(
        self,
        session: WorkflowSession,
        *,
        old_root: Path,
        new_root: Path,
    ) -> None:
        session.workspace_dir = str(new_root)
        session.session_file = self._remap_workspace_path(
            session.session_file,
            old_root=old_root,
            new_root=new_root,
        )
        for artifact in session.artifacts.values():
            artifact.path = str(
                self._remap_workspace_path(
                    artifact.path,
                    old_root=old_root,
                    new_root=new_root,
                )
                or artifact.path
            )
        for issue in session.issues:
            issue.issue_path = self._remap_workspace_path(
                issue.issue_path,
                old_root=old_root,
                new_root=new_root,
            )
        for state in session.steps.values():
            for attachment in state.attachments:
                attachment.path = str(
                    self._remap_workspace_path(
                        attachment.path,
                        old_root=old_root,
                        new_root=new_root,
                    )
                    or attachment.path
                )
            last_run_dir = state.settings.get("last_run_dir")
            remapped_run_dir = self._remap_workspace_path(
                str(last_run_dir) if last_run_dir else None,
                old_root=old_root,
                new_root=new_root,
            )
            if remapped_run_dir:
                state.settings["last_run_dir"] = remapped_run_dir
            for issue in state.issues:
                issue.issue_path = self._remap_workspace_path(
                    issue.issue_path,
                    old_root=old_root,
                    new_root=new_root,
                )
            for payload in state.raw_issues:
                for key in ("path", "issue_path"):
                    if key in payload:
                        payload[key] = self._remap_workspace_path(
                            str(payload.get(key) or ""),
                            old_root=old_root,
                            new_root=new_root,
                        )

    @staticmethod
    def _run_index(name: str) -> int:
        """Parse one run directory index such as `run_003_...`."""
        match = RUN_DIR_PATTERN.match(name)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _artifact_label_for_file(step_id: str, file_path: Path) -> Optional[str]:
        """Return the workflow artifact label for one reconstructed file."""
        filename = file_path.name
        if step_id in {"cst_project"} and file_path.suffix.lower() == ".cst":
            return "cst_project"
        if step_id in {"cst_update"} and file_path.suffix.lower() == ".cst":
            return "cst_updated_project"
        if step_id in {"hfss_project"} and file_path.suffix.lower() in {".aedt", ".aedtz"}:
            return "hfss_project"
        if step_id in {"hfss_update"} and file_path.suffix.lower() in {".aedt", ".aedtz"}:
            return "hfss_updated_project"
        return ARTIFACT_LABELS_BY_STEP.get(step_id, {}).get(filename)

    @staticmethod
    def _classify_artifact_path(path: str) -> str:
        """Classify one reconstructed artifact using existing desktop conventions."""
        extension = Path(path).suffix.lower()
        if extension == ".pdf":
            return "pdf"
        if extension == ".json":
            return "json"
        if extension == ".bas":
            return "macro"
        if extension in {".aedt", ".aedtz"}:
            return "hfss"
        if extension == ".cst":
            return "cst"
        if extension in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}:
            return "image"
        if extension in {
            ".cfg",
            ".conf",
            ".csv",
            ".html",
            ".ini",
            ".log",
            ".md",
            ".py",
            ".rst",
            ".text",
            ".toml",
            ".tsv",
            ".txt",
            ".yaml",
            ".yml",
        }:
            return "text"
        return "file"

    def add_text_attachment(
        self,
        session: WorkflowSession,
        step_id: str,
        name: str,
        content: str = "",
    ) -> AttachmentRef:
        safe_name = sanitize_leaf_filename(f"{name}.txt", "attachment")
        target_path = make_session_attachment_path(
            session.workspace_dir,
            step_id,
            safe_name,
        )
        Path(target_path).write_text(content, encoding="utf-8")
        return AttachmentRef(
            id=f"attachment-{step_id}-{Path(target_path).stem}",
            name=Path(target_path).name,
            path=target_path,
            kind="text",
            editable=True,
        )

    def sync_description_attachment(
        self,
        session: WorkflowSession,
        step_id: str,
        content: str,
    ) -> Optional[AttachmentRef]:
        state = session.steps.get(step_id)
        if state is None:
            return None

        existing = next(
            (
                attachment
                for attachment in state.attachments
                if attachment.origin == "description"
            ),
            None,
        )
        text = content or ""
        if not text.strip() and existing is None:
            return None

        target_dir = Path(session.workspace_dir) / "attachments" / step_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / sanitize_leaf_filename("description.txt", "description")
        target_path.write_text(text, encoding="utf-8")

        if existing is None:
            existing = AttachmentRef(
                id=f"attachment-{step_id}-description",
                name=target_path.name,
                path=str(target_path),
                kind="text",
                editable=True,
                origin="description",
            )
            state.attachments.insert(0, existing)
        else:
            existing.name = target_path.name
            existing.path = str(target_path)
            existing.kind = "text"
            existing.editable = True
            existing.origin = "description"
        return existing

    def import_attachment(
        self,
        session: WorkflowSession,
        step_id: str,
        source_path: str,
    ) -> AttachmentRef:
        safe_name = sanitize_leaf_filename(Path(source_path).name, "attachment")
        target_path = make_session_attachment_path(
            session.workspace_dir,
            step_id,
            safe_name,
        )
        shutil.copy2(source_path, target_path)
        kind = attachment_kind_for_path(target_path)
        editable = kind == "text"
        return AttachmentRef(
            id=f"attachment-{step_id}-{Path(target_path).stem}",
            name=Path(target_path).name,
            path=target_path,
            kind=kind,
            editable=editable,
        )

    def write_attachment_text(self, attachment: AttachmentRef, content: str) -> None:
        if not attachment.editable:
            raise ValueError("Only text attachments can be edited.")
        Path(attachment.path).write_text(content, encoding="utf-8")

    def read_attachment_text(self, attachment: AttachmentRef) -> str:
        return Path(attachment.path).read_text(encoding="utf-8")


class RecentSessionStore:
    """Track recently opened session files."""

    def __init__(self, recents_path: Optional[str] = None) -> None:
        self.recents_path = Path(recents_path) if recents_path else DEFAULT_RECENTS_PATH
        self.recents_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, recents: List[str]) -> None:
        with open(self.recents_path, "w", encoding="utf-8") as output_file:
            json.dump(recents, output_file, indent=2)
            output_file.write("\n")

    @staticmethod
    def _normalise_workspace_path(path: str) -> Optional[str]:
        target = Path(path).expanduser()
        if target.is_file():
            if target.name.lower() != "session.json":
                return None
            target = target.parent
        if not target.exists() or not target.is_dir():
            return None
        if not (target / "session.json").exists():
            return None
        return canonical_path_text(target)

    def load(self) -> List[str]:
        if not self.recents_path.exists():
            return []
        try:
            with open(self.recents_path, "r", encoding="utf-8") as source:
                payload = json.load(source)
        except Exception:
            return []
        recents: List[str] = []
        dirty = False
        for item in payload:
            if not isinstance(item, str):
                dirty = True
                continue
            workspace_path = self._normalise_workspace_path(item)
            if workspace_path is None:
                dirty = True
                continue
            if workspace_path in recents:
                dirty = True
                continue
            if workspace_path != item:
                dirty = True
            recents.append(workspace_path)
        recents = recents[:10]
        if dirty:
            self._write(recents)
        return recents

    def add(self, path: str) -> List[str]:
        workspace_path = self._normalise_workspace_path(path)
        recents = self.load()
        if workspace_path is None:
            return recents
        recents = [item for item in recents if item != workspace_path]
        recents.insert(0, workspace_path)
        recents = recents[:10]
        self._write(recents)
        return recents

    def remove(self, path: str) -> List[str]:
        workspace_path = self._normalise_workspace_path(path)
        candidates = {str(path)}
        if workspace_path is not None:
            candidates.add(workspace_path)
        recents = [item for item in self.load() if item not in candidates]
        self._write(recents)
        return recents
