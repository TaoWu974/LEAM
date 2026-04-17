"""Main window for the LEAM desktop app."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from leam.utils.image_utils import MODEL_IMAGE_EXTENSIONS

from ..examples import (
    EXAMPLE_PRESETS,
    apply_example_preset,
    get_example_preset,
    is_example_preset_available,
)
from ..services.structure import (
    SolidPreviewItem,
    StructurePreview,
    load_materials_preview,
    load_parameters_preview,
    load_solids_preview,
)
from ..storage import (
    DesktopSessionStore,
    RecentSessionStore,
    sanitize_path_component,
)
from ..workflow.engine import INPUT_STEP_ID, WorkflowEngine
from ..workflow.models import (
    AttachmentRef,
    IssueRefill,
    WorkflowSession,
)
from .theme import (
    PALETTE,
    apply_theme,
    refresh_style,
    set_role,
    set_tone,
    status_tone,
)

TEMPLATE_CHOICES = {
    "Strong Description": "strong_description",
    "Weak Description": "weak_description",
    "Paper Reconstruction (strong workflow + figures)": "paper_reconstruction",
}
BACKEND_CHOICES = {
    "CST": "cst",
    "HFSS": "hfss",
}
ATTACHMENT_FILE_FILTER = (
    "All Files (*);;"
    "Text and Prompt Files (*.pdf *.txt *.md *.json *.py *.bas *.csv *.yaml "
    "*.yml *.toml *.rst *.log *.ini *.cfg *.conf *.tsv *.text *.html *.mtd);;"
    "Images (*.png *.jpg *.jpeg)"
)
ATTACHMENT_IMAGE_FILTER = (
    "Images (*.png *.jpg *.jpeg);;"
    "All Files (*)"
)

STEP_SUMMARIES = {
    INPUT_STEP_ID: (
        "Set the global case description and shared attachments. "
        "Workflow module selection now lives in the left-side config card."
    ),
    "initial_solids": (
        "Bootstrap solids from a weak description before parameter and material extraction."
    ),
    "parameters": "Extract or refine the parameter set and write simulator-specific parameter artifacts.",
    "materials": "Extract material assignments and write simulator-specific material artifacts.",
    "solids": "Generate the canonical solids JSON that drives the downstream model steps.",
    "check_solid": (
        "Validate the solids output. Any blocking issues are routed back to the earlier step that needs a rerun."
    ),
    "dimensions": "Convert solids and parameters into dimension definitions for model generation.",
    "model_3d": "Generate the 3D simulator model script from parameters, dimensions, and materials.",
    "model_2d": "Generate the 2.5D simulator model script when the solids output contains 2.5D geometry.",
    "boolean": "Generate simulator boolean operations that combine and subtract model pieces.",
    "cst_project": "Build and optionally execute the CST project from the generated macros.",
    "hfss_project": "Build and optionally execute the HFSS project from the generated Python artifacts.",
    "parameter_update": "Generate a follow-up parameter update artifact after the first model pass.",
    "cst_update": "Apply the generated parameter update macro to an existing CST project.",
    "hfss_update": "Apply the generated parameter update script to an existing HFSS project.",
}

STEP_BADGE_LABELS = {
    "idle": "IDLE",
    "waiting": "WAITING",
    "running": "RUNNING",
    "success": "DONE",
    "issues": "ISSUES",
    "blocked_by_upstream": "BLOCKED",
    "rerun_required": "RERUN",
    "stale": "STALE",
    "error": "ERROR",
}


class StepListItemWidget(QFrame):
    """One styled widget used inside the workflow step track."""

    activated = Signal(str)
    run_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.step_id = ""
        self._interaction_enabled = True
        self._action_enabled = False
        self.setProperty("stepItem", True)
        self.setProperty("selected", False)
        refresh_style(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self.title_label = QLabel(self)
        self.title_label.setWordWrap(True)
        self.title_label.setProperty("role", "value")
        refresh_style(self.title_label)

        self.status_badge = QLabel(self)
        self.status_badge.setAlignment(Qt.AlignCenter)
        self.status_badge.setProperty("pill", True)
        refresh_style(self.status_badge)

        self.meta_label = QLabel(self)
        self.meta_label.setWordWrap(True)
        set_role(self.meta_label, "muted")

        self.detail_label = QLabel(self)
        self.detail_label.setWordWrap(True)
        set_role(self.detail_label, "subtitle")
        self.detail_label.hide()

        self.action_button = QPushButton(self)
        self.action_button.setObjectName("PrimaryActionButton")
        self.action_button.hide()
        self.action_button.clicked.connect(self._emit_run_requested)

        header_row.addWidget(self.title_label, 1)
        header_row.addWidget(self.status_badge, 0, Qt.AlignTop)

        layout.addLayout(header_row)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.action_button)

    def update_content(
        self,
        *,
        title: str,
        step_id: str,
        status: str,
        meta_text: str,
    ) -> None:
        """Refresh the displayed title and status."""

        self.step_id = step_id
        self.title_label.setText(title)
        self.meta_label.setText(meta_text)
        self.status_badge.setText(STEP_BADGE_LABELS.get(status, status.replace("_", " ").title()))
        self.status_badge.setMinimumWidth(78)
        set_tone(self.status_badge, status_tone(status))

    def set_selected(self, selected: bool) -> None:
        """Refresh the selected visual state."""

        self.setProperty("selected", selected)
        refresh_style(self)

    def set_expanded(
        self,
        expanded: bool,
        *,
        detail_text: str = "",
        action_text: str = "",
        action_enabled: bool = False,
    ) -> None:
        """Toggle the expanded current-step presentation."""

        self.detail_label.setText(detail_text)
        self.detail_label.setVisible(expanded and bool(detail_text))
        self.action_button.setText(action_text)
        self._action_enabled = action_enabled
        self.action_button.setEnabled(self._interaction_enabled and action_enabled)
        self.action_button.setVisible(expanded and bool(action_text))
        self.adjustSize()

    def set_interaction_enabled(self, enabled: bool) -> None:
        """Allow or block manual interaction without dimming the content."""

        self._interaction_enabled = enabled
        self.action_button.setEnabled(enabled and self._action_enabled)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if not self._interaction_enabled:
            event.ignore()
            return
        self.activated.emit(self.step_id)
        super().mousePressEvent(event)

    def _emit_run_requested(self) -> None:
        if self.step_id:
            self.run_requested.emit(self.step_id)


class StepRunWorker(QObject):
    """Run one workflow step off the UI thread."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        engine: WorkflowEngine,
        session: WorkflowSession,
        step_id: str,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.session = session
        self.step_id = step_id

    @Slot()
    def run(self) -> None:
        try:
            result = self.engine.run_step(self.session, self.step_id)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)


class ProjectEntryDialog(QDialog):
    """Entry dialog that captures a workspace name and export root."""

    def __init__(
        self,
        output_root: str,
        default_name: str,
        default_backend: str = "cst",
        available_backends: Optional[List[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.default_output_root = output_root
        requested_backend = str(default_backend or "cst").strip().lower()
        self.available_backends = [
            backend
            for backend in (available_backends or [])
            if backend in BACKEND_CHOICES.values()
        ]
        if not self.available_backends:
            self.available_backends = [requested_backend or "cst"]
        self.default_backend = (
            requested_backend
            if requested_backend in self.available_backends
            else self.available_backends[0]
        )
        self.setWindowTitle("Create LEAM Workspace")
        self.resize(620, 260)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Choose a workspace name. LEAM Desktop will create a folder using "
            "`workspace_name + backend + timestamp` under the default export root.",
            self,
        )
        intro.setWordWrap(True)
        set_role(intro, "subtitle")
        layout.addWidget(intro)

        form = QFormLayout()
        self.project_name_edit = QLineEdit(default_name, self)
        self.backend_combo = QComboBox(self)
        for label, value in BACKEND_CHOICES.items():
            if value in self.available_backends:
                self.backend_combo.addItem(label, value)
        backend_index = self.backend_combo.findData(self.default_backend)
        if backend_index >= 0:
            self.backend_combo.setCurrentIndex(backend_index)
        self.backend_combo.setEnabled(len(self.available_backends) > 1)
        self.output_root_edit = QLineEdit(output_root, self)
        browse_button = QPushButton("Browse...", self)
        browse_button.clicked.connect(self._browse_output_root)
        output_root_row = QWidget(self)
        output_root_layout = QHBoxLayout(output_root_row)
        output_root_layout.setContentsMargins(0, 0, 0, 0)
        output_root_layout.addWidget(self.output_root_edit)
        output_root_layout.addWidget(browse_button)
        self.preview_label = QLabel(self)
        self.preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        set_role(self.preview_label, "value")
        form.addRow("Workspace name", self.project_name_edit)
        form.addRow("Backend", self.backend_combo)
        form.addRow("Export root", output_root_row)
        form.addRow("Folder preview", self.preview_label)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.project_name_edit.textChanged.connect(self._update_preview)
        self.backend_combo.currentIndexChanged.connect(self._update_preview)
        self.output_root_edit.textChanged.connect(self._update_preview)
        apply_theme(self)
        self._update_preview()

    def project_name(self) -> str:
        return self.project_name_edit.text().strip() or "workspace"

    def output_root(self) -> str:
        return self.output_root_edit.text().strip() or self.default_output_root

    def backend(self) -> str:
        return str(self.backend_combo.currentData() or self.default_backend)

    def _update_preview(self) -> None:
        safe_project_name = sanitize_path_component(self.project_name(), "workspace")
        self.preview_label.setText(
            str(
                Path(self.output_root())
                / f"{safe_project_name}_{self.backend()}_YYYYMMDD_HHMMSS"
            )
        )

    def _browse_output_root(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Export Root",
            self.output_root(),
        )
        if path:
            self.output_root_edit.setText(path)


class MainWindow(QMainWindow):
    """Top-level LEAM Desktop window."""

    def __init__(self) -> None:
        super().__init__()
        self.engine = WorkflowEngine()
        self.session_store = DesktopSessionStore()
        self.recent_store = RecentSessionStore()
        self.session: Optional[WorkflowSession] = None
        self.current_step_id = INPUT_STEP_ID
        self._ui_updating = False
        self._current_attachment_id: Optional[str] = None
        self._run_thread: Optional[QThread] = None
        self._run_worker: Optional[StepRunWorker] = None
        self._running_step_id: Optional[str] = None
        self._step_items: dict[str, QListWidgetItem] = {}
        self._step_item_widgets: dict[str, StepListItemWidget] = {}
        self._step_display_statuses: dict[str, str] = {}
        self._step_definitions_by_id = {}
        self._running_step_title = ""
        self._running_dots = 0
        self._launchpad_runtime_warning_shown = False
        self._launchpad_default_subtitle = ""
        self._launch_example_buttons: List[QPushButton] = []
        self._run_timer = QTimer(self)
        self._run_timer.setInterval(350)
        self._run_timer.timeout.connect(self._advance_running_indicator)

        self.setWindowTitle("LEAM Desktop")
        self.resize(1500, 920)
        self.menuBar().hide()
        self._build_ui()
        apply_theme(self)
        self._rebuild_recent_menu()
        self._refresh_all()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._save_editor_to_state()
        super().closeEvent(event)

    def _build_command_bar(self, parent: QWidget) -> QWidget:
        bar = QFrame(parent)
        bar.setObjectName("TopChromeCard")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(14)

        brand_layout = QVBoxLayout()
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(4)
        chrome_eyebrow = QLabel("LEAM DESKTOP", bar)
        set_role(chrome_eyebrow, "eyebrow")
        self.chrome_title_label = QLabel("Workspace Control Surface", bar)
        set_role(self.chrome_title_label, "value")
        self.chrome_meta_label = QLabel(
            "Create, open, and resume LEAM workspaces from one control bar.",
            bar,
        )
        set_role(self.chrome_meta_label, "muted")
        brand_layout.addWidget(chrome_eyebrow)
        brand_layout.addWidget(self.chrome_title_label)
        brand_layout.addWidget(self.chrome_meta_label)

        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)

        self.chrome_create_button = QPushButton("Create Workspace", bar)
        self.chrome_create_button.setObjectName("LaunchGhostButton")
        self.chrome_create_button.clicked.connect(self._return_to_launchpad)
        self.chrome_create_button.setToolTip(
            "Return to the launchpad to create another workspace or start from an example."
        )

        self.chrome_open_button = QPushButton("Open Workspace", bar)
        self.chrome_open_button.setObjectName("LaunchGhostButton")
        self.chrome_open_button.clicked.connect(self._open_workspace)

        self.recent_menu = QMenu(self)
        self.chrome_recent_button = QPushButton("Recent Workspaces", bar)
        self.chrome_recent_button.setObjectName("LaunchGhostButton")
        self.chrome_recent_button.setMenu(self.recent_menu)

        actions_layout.addWidget(self.chrome_create_button)
        actions_layout.addWidget(self.chrome_open_button)
        actions_layout.addWidget(self.chrome_recent_button)

        layout.addLayout(brand_layout, 1)
        layout.addLayout(actions_layout, 0)
        return bar

    def _build_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 12)
        layout.setSpacing(12)

        self.command_bar = self._build_command_bar(root)
        self.main_stack = QStackedWidget(root)
        self.launchpad_page = self._build_launchpad_page()
        self.workspace_page = QWidget(root)
        workspace_layout = QVBoxLayout(self.workspace_page)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        self.workspace_splitter = QSplitter(Qt.Horizontal, self.workspace_page)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.left_pane_widget = self._build_left_pane()
        self.middle_pane_widget = self._build_middle_pane()
        self.right_pane_widget = self._build_right_pane()
        self.left_pane_widget.setMinimumWidth(210)
        self.middle_pane_widget.setMinimumWidth(560)
        self.right_pane_widget.setMinimumWidth(320)
        self.workspace_splitter.addWidget(self.left_pane_widget)
        self.workspace_splitter.addWidget(self.middle_pane_widget)
        self.workspace_splitter.addWidget(self.right_pane_widget)
        self.workspace_splitter.setStretchFactor(0, 3)
        self.workspace_splitter.setStretchFactor(1, 4)
        self.workspace_splitter.setStretchFactor(2, 2)
        self.workspace_splitter.setSizes([480, 640, 320])
        workspace_layout.addWidget(self.workspace_splitter)

        self.main_stack.addWidget(self.launchpad_page)
        self.main_stack.addWidget(self.workspace_page)

        layout.addWidget(self.command_bar)
        layout.addWidget(self.main_stack)
        root.setLayout(layout)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar(self))

    def _build_launchpad_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        hero_card = QFrame(page)
        hero_card.setObjectName("LaunchHeroCard")
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(24, 24, 24, 24)
        hero_layout.setSpacing(12)

        hero_eyebrow = QLabel("LEAM CONTROL SURFACE", hero_card)
        set_role(hero_eyebrow, "eyebrow")
        self.launchpad_title_label = QLabel("Model antenna workflows from one workspace.", hero_card)
        set_role(self.launchpad_title_label, "heroTitle")
        self.launchpad_subtitle_label = QLabel(
            "Open or create a LEAM workspace to continue the pipeline. "
            "LEAM manages workspaces directly, not external CST/HFSS project files.",
            hero_card,
        )
        self._launchpad_default_subtitle = self.launchpad_subtitle_label.text()
        self.launchpad_subtitle_label.setWordWrap(True)
        set_role(self.launchpad_subtitle_label, "subtitle")

        hero_button_row = QHBoxLayout()
        hero_button_row.setContentsMargins(0, 0, 0, 0)
        hero_button_row.setSpacing(12)
        self.launch_new_button = QPushButton("Create Workspace", hero_card)
        self.launch_new_button.setObjectName("LaunchPrimaryButton")
        self.launch_new_button.setToolTip(
            "Create a new LEAM workspace under the selected export root."
        )
        self.launch_new_button.clicked.connect(self._new_session)
        self.launch_open_button = QPushButton("Open Workspace", hero_card)
        self.launch_open_button.setObjectName("LaunchPrimaryButton")
        self.launch_open_button.setToolTip(
            "Open an existing LEAM workspace directory."
        )
        self.launch_open_button.clicked.connect(self._open_workspace)
        hero_button_row.addWidget(self.launch_new_button)
        hero_button_row.addWidget(self.launch_open_button)
        hero_button_row.addStretch(1)

        hero_layout.addWidget(hero_eyebrow)
        hero_layout.addWidget(self.launchpad_title_label)
        hero_layout.addWidget(self.launchpad_subtitle_label)
        hero_layout.addLayout(hero_button_row)

        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(16)

        recent_card = QFrame(page)
        recent_card.setObjectName("LaunchCard")
        recent_layout = QVBoxLayout(recent_card)
        recent_layout.setContentsMargins(20, 20, 20, 20)
        recent_layout.setSpacing(10)
        recent_eyebrow = QLabel("RECENT WORKSPACES", recent_card)
        set_role(recent_eyebrow, "eyebrow")
        recent_title = QLabel("Resume Workspace", recent_card)
        set_role(recent_title, "title")
        recent_subtitle = QLabel(
            "Choose a recent workspace or open another workspace directory.",
            recent_card,
        )
        recent_subtitle.setWordWrap(True)
        set_role(recent_subtitle, "subtitle")
        self.launch_recent_list = QListWidget(recent_card)
        self.launch_recent_list.itemDoubleClicked.connect(
            lambda _item: self._open_selected_recent_workspace()
        )
        self.launch_recent_list.currentItemChanged.connect(
            lambda _current, _previous: self._refresh_launchpad_recent_actions()
        )
        self.launch_recent_button = QPushButton("Open Selected Workspace", recent_card)
        self.launch_recent_button.setObjectName("LaunchGhostButton")
        self.launch_recent_button.clicked.connect(self._open_selected_recent_workspace)
        self.launch_recent_remove_button = QPushButton("Remove Selected", recent_card)
        self.launch_recent_remove_button.setObjectName("LaunchGhostButton")
        self.launch_recent_remove_button.clicked.connect(
            self._remove_selected_recent_workspace
        )
        recent_actions = QHBoxLayout()
        recent_actions.setContentsMargins(0, 0, 0, 0)
        recent_actions.setSpacing(10)
        recent_actions.addWidget(self.launch_recent_button, 1)
        recent_actions.addWidget(self.launch_recent_remove_button)
        recent_layout.addWidget(recent_eyebrow)
        recent_layout.addWidget(recent_title)
        recent_layout.addWidget(recent_subtitle)
        recent_layout.addWidget(self.launch_recent_list, 1)
        recent_layout.addLayout(recent_actions)

        examples_card = QFrame(page)
        examples_card.setObjectName("LaunchCard")
        examples_layout = QVBoxLayout(examples_card)
        examples_layout.setContentsMargins(20, 20, 20, 20)
        examples_layout.setSpacing(10)
        examples_eyebrow = QLabel("EXAMPLES", examples_card)
        set_role(examples_eyebrow, "eyebrow")
        examples_title = QLabel("Start From Example", examples_card)
        set_role(examples_title, "title")
        examples_subtitle = QLabel(
            "Create a new workspace from a preconfigured antenna example.",
            examples_card,
        )
        examples_subtitle.setWordWrap(True)
        set_role(examples_subtitle, "subtitle")
        examples_layout.addWidget(examples_eyebrow)
        examples_layout.addWidget(examples_title)
        examples_layout.addWidget(examples_subtitle)

        for preset in EXAMPLE_PRESETS.values():
            preset_available = is_example_preset_available(preset)
            button = QPushButton(
                f"{preset.title}\nCST/HFSS | {preset.template.replace('_', ' ')}",
                examples_card,
            )
            button.setObjectName("LaunchGhostButton")
            button.setProperty("exampleAvailable", preset_available)
            if preset_available:
                button.setToolTip(
                    "Create a new workspace from this example preset.\n\n"
                    f"{preset.input_description}"
                )
                button.clicked.connect(
                    lambda checked=False, preset_key=preset.key: self._load_example(
                        preset_key
                    )
                )
            else:
                button.setEnabled(False)
                button.setToolTip(
                    "This example requires repository assets that are not "
                    "included in this installation."
                )
            examples_layout.addWidget(button)
            self._launch_example_buttons.append(button)
        examples_layout.addStretch(1)

        cards_row.addWidget(recent_card, 3)
        cards_row.addWidget(examples_card, 2)

        layout.addWidget(hero_card)
        layout.addLayout(cards_row, 1)
        return page

    def _refresh_launchpad(self) -> None:
        self._refresh_launchpad_recents()
        self._set_launchpad_runtime_state()
        self._sync_view_mode()

    def _refresh_chrome(self) -> None:
        has_session = self.session is not None
        self.command_bar.setVisible(has_session)
        if has_session:
            workspace_name = (
                self.session.title
                or Path(self.session.workspace_dir).name
                or self.session.workspace_dir
            )
            self.chrome_title_label.setText(workspace_name)
            self.chrome_meta_label.setText(self.session.workspace_dir)
            self.chrome_meta_label.setToolTip(self.session.workspace_dir)
            self.chrome_create_button.setToolTip(
                "Return to the launchpad to create another workspace or start from an example."
            )
        else:
            self.chrome_title_label.setText("Workspace Control Surface")
            self.chrome_meta_label.setText(
                "Create, open, or resume a LEAM workspace from this command bar."
            )
            self.chrome_meta_label.setToolTip("")
            self.chrome_create_button.setToolTip(
                "Create a new LEAM workspace under the selected export root."
            )

        has_recent = any(bool(action.data()) for action in self.recent_menu.actions())
        self.chrome_recent_button.setEnabled(has_recent)

    def _refresh_launchpad_recents(self) -> None:
        if not hasattr(self, "launch_recent_list"):
            return
        self.launch_recent_list.clear()
        recents = self.recent_store.load()
        if not recents:
            empty = QListWidgetItem(
                "No recent workspaces yet.\nCreate a workspace or open an existing workspace directory.",
                self.launch_recent_list,
            )
            empty.setFlags(Qt.NoItemFlags)
            empty.setForeground(QColor(PALETTE["text_muted"]))
            self.launch_recent_button.setEnabled(False)
            return

        for path in recents:
            workspace_name = Path(path).name or path
            item = QListWidgetItem(
                f"{workspace_name}\n{path}",
                self.launch_recent_list,
            )
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
        self.launch_recent_list.setCurrentRow(0)
        self._refresh_launchpad_recent_actions()

    def _refresh_launchpad_recent_actions(self) -> None:
        if not hasattr(self, "launch_recent_button"):
            return
        current = self.launch_recent_list.currentItem() if hasattr(self, "launch_recent_list") else None
        has_current = current is not None and bool(current.data(Qt.UserRole))
        self.launch_recent_button.setEnabled(
            has_current
            and not self._all_backends_unavailable()
        )
        if hasattr(self, "launch_recent_remove_button"):
            self.launch_recent_remove_button.setEnabled(has_current)

    def _open_selected_recent_workspace(self) -> None:
        current = self.launch_recent_list.currentItem() if hasattr(self, "launch_recent_list") else None
        if current is None:
            return
        path = current.data(Qt.UserRole)
        if not path:
            return
        self._open_recent(str(path))

    def _remove_selected_recent_workspace(self) -> None:
        current = self.launch_recent_list.currentItem() if hasattr(self, "launch_recent_list") else None
        if current is None:
            return
        path = current.data(Qt.UserRole)
        if not path:
            return
        self.recent_store.remove(str(path))
        self._rebuild_recent_menu()

    def _sync_view_mode(self) -> None:
        target = self.workspace_page if self.session is not None else self.launchpad_page
        if self.main_stack.currentWidget() is not target:
            self.main_stack.setCurrentWidget(target)

    def _environment_report(self) -> dict:
        return dict(self.engine.runner.get_environment_report())

    def _available_backends(self, env: Optional[dict] = None) -> List[str]:
        report = env or self._environment_report()
        values = report.get("available_backends") or []
        return [
            str(value)
            for value in values
            if str(value) in BACKEND_CHOICES.values()
        ]

    def _first_available_backend(self, env: Optional[dict] = None) -> str:
        available_backends = self._available_backends(env)
        return available_backends[0] if available_backends else "cst"

    def _backend_available(self, backend: str, env: Optional[dict] = None) -> bool:
        report = env or self._environment_report()
        return bool(report.get(f"{backend}_available"))

    def _all_backends_unavailable(self, env: Optional[dict] = None) -> bool:
        report = env or self._environment_report()
        return bool(report.get("all_backends_unavailable"))

    def _step_switch_locked(self) -> bool:
        return self._run_thread is not None or self._running_step_id is not None

    def _all_backends_unavailable_message(
        self,
        env: Optional[dict] = None,
    ) -> str:
        report = env or self._environment_report()
        header = (
            "LEAM Desktop needs at least one local CST or HFSS installation "
            "before you can create or open a workspace."
        )
        messages = []
        for backend in ("cst", "hfss"):
            message = str(report.get(f"{backend}_available_message") or "").strip()
            if message:
                messages.append(f"{backend.upper()}: {message}")
        if messages:
            return "\n".join([header, "", *messages])
        return (
            f"{header}\n\n"
            "Install CST Studio Suite or Ansys Electronics Desktop, then "
            "restart LEAM Desktop."
        )

    def _set_backend_combo_item_enabled(self, backend: str, enabled: bool) -> None:
        index = self.backend_combo.findData(backend)
        if index < 0:
            return
        model = self.backend_combo.model()
        item = getattr(model, "item", lambda *_args: None)(index)
        if item is not None:
            item.setEnabled(enabled)

    def _set_launchpad_runtime_state(self, env: Optional[dict] = None) -> None:
        report = env or self._environment_report()
        blocked = self._all_backends_unavailable(report)
        self.launch_new_button.setEnabled(not blocked)
        self.launch_open_button.setEnabled(not blocked)
        self.launch_recent_list.setEnabled(
            not blocked and self.launch_recent_list.count() > 0
        )
        for button in self._launch_example_buttons:
            button.setEnabled(
                bool(button.property("exampleAvailable")) and not blocked
            )
        self.launch_recent_button.setEnabled(
            not blocked and self.launch_recent_list.currentItem() is not None
        )
        if blocked:
            self.launchpad_subtitle_label.setText(
                "LEAM Desktop needs at least one local CST or HFSS "
                "installation. It checks for usable runtimes on startup. Fix "
                "the runtime issue below and restart the app."
            )
            if self.session is None and not self._launchpad_runtime_warning_shown:
                QMessageBox.warning(
                    self,
                    "No Runtime Available",
                    self._all_backends_unavailable_message(report),
                )
                self._launchpad_runtime_warning_shown = True
        else:
            self.launchpad_subtitle_label.setText(self._launchpad_default_subtitle)
            self._launchpad_runtime_warning_shown = False

    def _ensure_launchpad_runtime_ready(self) -> Optional[dict]:
        env = self._environment_report()
        if not self._all_backends_unavailable(env):
            return env
        self._set_launchpad_runtime_state(env)
        if self.session is not None:
            QMessageBox.warning(
                self,
                "No Runtime Available",
                self._all_backends_unavailable_message(env),
            )
        return None

    def _prompt_for_project_config(
        self,
        default_name: str,
        default_backend: str = "cst",
    ) -> Optional[tuple[str, str, str]]:
        env = self._ensure_launchpad_runtime_ready()
        if env is None:
            return None
        available_backends = self._available_backends(env)
        effective_default_backend = (
            default_backend
            if default_backend in available_backends
            else self._first_available_backend(env)
        )
        dialog = ProjectEntryDialog(
            self.session_store.default_workspace_root(),
            default_name,
            effective_default_backend,
            available_backends,
            self,
        )
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.project_name(), dialog.output_root(), dialog.backend()

    def _start_project_flow(
        self,
        *,
        initial: bool = False,
        example_key: Optional[str] = None,
    ) -> bool:
        preset = None
        if example_key:
            try:
                preset = get_example_preset(example_key, require_available=True)
            except (KeyError, ValueError) as exc:
                QMessageBox.warning(
                    self,
                    "Example Unavailable",
                    str(exc),
                )
                return False
        default_name = (
            preset.title if preset else "workspace"
        )
        default_backend = (
            preset.backend if preset else "cst"
        )
        project_config = self._prompt_for_project_config(default_name, default_backend)
        if not project_config:
            return False
        project_name, output_root, selected_backend = project_config

        workspace = self.session_store.create_workspace(
            project_name,
            output_root=output_root,
            backend=selected_backend,
        )
        self.session = self.engine.create_session(workspace)
        self.session.title = project_name
        if preset is not None and example_key is not None:
            apply_example_preset(
                self.session,
                self.engine,
                self.session_store,
                example_key,
            )
        self.session.steps["input"].settings["backend"] = selected_backend
        self.engine.refresh_session(self.session)
        self.current_step_id = self._default_focus_step_id()
        self._autosave_session_snapshot(update_recent=True)
        self._refresh_all()
        if not initial:
            self.statusBar().showMessage(
                f"Created workspace `{project_name}` in {workspace}",
                5000,
            )
        return True

    def _build_left_pane(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        workspace_card = QFrame(pane)
        workspace_card.setObjectName("WorkspaceCard")
        workspace_layout = QVBoxLayout(workspace_card)
        workspace_layout.setContentsMargins(18, 18, 18, 18)
        workspace_layout.setSpacing(8)

        workspace_eyebrow = QLabel("WORKSPACE", workspace_card)
        set_role(workspace_eyebrow, "eyebrow")
        self.session_title_label = QLabel(workspace_card)
        set_role(self.session_title_label, "title")
        self.session_meta_label = QLabel(workspace_card)
        self.session_meta_label.setWordWrap(True)
        set_role(self.session_meta_label, "muted")

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(8)
        self.workspace_status_badge = QLabel(workspace_card)
        self.workspace_status_badge.setProperty("pill", True)
        refresh_style(self.workspace_status_badge)
        self.workspace_backend_badge = QLabel(workspace_card)
        self.workspace_backend_badge.setProperty("pill", True)
        refresh_style(self.workspace_backend_badge)
        self.workspace_template_badge = QLabel(workspace_card)
        self.workspace_template_badge.setProperty("pill", True)
        refresh_style(self.workspace_template_badge)
        badge_row.addWidget(self.workspace_status_badge)
        badge_row.addWidget(self.workspace_backend_badge)
        badge_row.addWidget(self.workspace_template_badge)
        badge_row.addStretch(1)

        self.workspace_detail_label = QLabel(workspace_card)
        self.workspace_detail_label.setWordWrap(True)
        set_role(self.workspace_detail_label, "subtitle")

        workspace_layout.addWidget(workspace_eyebrow)
        workspace_layout.addWidget(self.session_title_label)
        workspace_layout.addWidget(self.session_meta_label)
        workspace_layout.addLayout(badge_row)
        workspace_layout.addWidget(self.workspace_detail_label)

        self.workflow_config_group = QFrame(workspace_card)
        self.workflow_config_group.setObjectName("ConsoleCard")
        self.workflow_config_group.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Maximum,
        )
        workflow_layout = QVBoxLayout(self.workflow_config_group)
        workflow_layout.setContentsMargins(14, 14, 14, 14)
        workflow_layout.setSpacing(8)
        self.workflow_config_stack = QStackedWidget(self.workflow_config_group)
        self.workflow_config_stack.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Maximum,
        )
        workflow_eyebrow = QLabel("WORKFLOW CONFIG", self.workflow_config_group)
        set_role(workflow_eyebrow, "eyebrow")

        self.workflow_config_edit_page = QWidget(self.workflow_config_group)
        workflow_edit_layout = QVBoxLayout(self.workflow_config_edit_page)
        workflow_edit_layout.setContentsMargins(0, 0, 0, 0)
        workflow_edit_layout.setSpacing(8)
        self.workflow_template_combo = QComboBox(self.workflow_config_edit_page)
        for label in TEMPLATE_CHOICES:
            self.workflow_template_combo.addItem(label, TEMPLATE_CHOICES[label])
        self.backend_combo = QComboBox(self.workflow_config_edit_page)
        for label in BACKEND_CHOICES:
            self.backend_combo.addItem(label, BACKEND_CHOICES[label])
        self.enable_3d_checkbox = QCheckBox("3D Model (required)", self.workflow_config_edit_page)
        self.enable_3d_checkbox.setChecked(True)
        self.enable_3d_checkbox.setEnabled(False)
        self.enable_25d_checkbox = QCheckBox("2.5D Model", self.workflow_config_edit_page)
        self.enable_execution_checkbox = QCheckBox(
            "Enable Simulator Execution",
            self.workflow_config_edit_page,
        )
        self.enable_update_checkbox = QCheckBox(
            "Parameter Update",
            self.workflow_config_edit_page,
        )
        self.workflow_warning_label = QLabel(self.workflow_config_edit_page)
        self.workflow_warning_label.setWordWrap(True)
        set_role(self.workflow_warning_label, "statusText")
        set_tone(self.workflow_warning_label, "warning")
        workflow_edit_layout.addWidget(QLabel("Template", self.workflow_config_edit_page))
        workflow_edit_layout.addWidget(self.workflow_template_combo)
        workflow_edit_layout.addWidget(QLabel("EM Simulator", self.workflow_config_edit_page))
        workflow_edit_layout.addWidget(self.backend_combo)
        workflow_edit_layout.addWidget(self.enable_3d_checkbox)
        workflow_edit_layout.addWidget(self.enable_25d_checkbox)
        workflow_edit_layout.addWidget(self.enable_execution_checkbox)
        workflow_edit_layout.addWidget(self.enable_update_checkbox)
        workflow_edit_layout.addWidget(self.workflow_warning_label)
        self.workflow_apply_button = QPushButton(
            "Apply Workspace Setup",
            self.workflow_config_edit_page,
        )
        self.workflow_apply_button.setObjectName("PrimaryActionButton")
        self.workflow_apply_button.clicked.connect(self._run_workspace_setup)
        workflow_edit_layout.addWidget(self.workflow_apply_button)

        self.workflow_config_locked_page = QWidget(self.workflow_config_group)
        workflow_locked_layout = QVBoxLayout(self.workflow_config_locked_page)
        workflow_locked_layout.setContentsMargins(0, 0, 0, 0)
        workflow_locked_layout.setSpacing(8)
        workflow_locked_row = QHBoxLayout()
        workflow_locked_row.setContentsMargins(0, 0, 0, 0)
        workflow_locked_row.setSpacing(8)
        self.workflow_locked_badge = QLabel("LOCKED", self.workflow_config_locked_page)
        self.workflow_locked_badge.setProperty("pill", True)
        refresh_style(self.workflow_locked_badge)
        set_tone(self.workflow_locked_badge, "info")
        self.workflow_locked_backend_badge = QLabel(self.workflow_config_locked_page)
        self.workflow_locked_backend_badge.setProperty("pill", True)
        refresh_style(self.workflow_locked_backend_badge)
        set_tone(self.workflow_locked_backend_badge, "muted")
        self.workflow_locked_template_badge = QLabel(self.workflow_config_locked_page)
        self.workflow_locked_template_badge.setProperty("pill", True)
        refresh_style(self.workflow_locked_template_badge)
        set_tone(self.workflow_locked_template_badge, "muted")
        workflow_locked_row.addWidget(self.workflow_locked_badge)
        workflow_locked_row.addWidget(self.workflow_locked_backend_badge)
        workflow_locked_row.addWidget(self.workflow_locked_template_badge, 1)

        self.workflow_locked_summary_label = QLabel(self.workflow_config_locked_page)
        self.workflow_locked_summary_label.setWordWrap(True)
        set_role(self.workflow_locked_summary_label, "subtitle")
        self.workflow_locked_note_label = QLabel(
            "Workflow branches are locked after Workspace Setup.",
            self.workflow_config_locked_page,
        )
        self.workflow_locked_note_label.setWordWrap(True)
        set_role(self.workflow_locked_note_label, "statusText")
        set_tone(self.workflow_locked_note_label, "info")
        self.workflow_locked_warning_label = QLabel(self.workflow_config_locked_page)
        self.workflow_locked_warning_label.setWordWrap(True)
        set_role(self.workflow_locked_warning_label, "statusText")
        set_tone(self.workflow_locked_warning_label, "warning")

        workflow_locked_layout.addLayout(workflow_locked_row)
        workflow_locked_layout.addWidget(self.workflow_locked_summary_label)
        workflow_locked_layout.addWidget(self.workflow_locked_note_label)
        workflow_locked_layout.addWidget(self.workflow_locked_warning_label)

        self.workflow_config_stack.addWidget(self.workflow_config_edit_page)
        self.workflow_config_stack.addWidget(self.workflow_config_locked_page)
        workflow_layout.addWidget(workflow_eyebrow)
        workflow_layout.addWidget(self.workflow_config_stack)
        workspace_layout.addWidget(self.workflow_config_group)

        self.workflow_rail_card = QFrame(pane)
        self.workflow_rail_card.setObjectName("ActionCard")
        rail_layout = QVBoxLayout(self.workflow_rail_card)
        rail_layout.setContentsMargins(18, 18, 18, 18)
        rail_layout.setSpacing(10)
        rail_eyebrow = QLabel("WORKFLOW RAIL", self.workflow_rail_card)
        set_role(rail_eyebrow, "eyebrow")

        self.step_list = QListWidget(self.workflow_rail_card)
        self.step_list.setObjectName("WorkflowRailList")
        self.step_list.currentItemChanged.connect(self._on_step_changed)
        self.step_list.setUniformItemSizes(False)
        self.step_list.setSpacing(8)
        self.step_list.setSelectionMode(QAbstractItemView.SingleSelection)
        rail_layout.addWidget(rail_eyebrow)
        rail_layout.addWidget(self.step_list, 1)

        self.action_step_label = QLabel(pane)
        self.action_state_badge = QLabel(pane)
        self.action_detail_label = QLabel(pane)
        self.run_button = QPushButton(pane)
        self.run_button.clicked.connect(self._run_current_step)
        self.action_step_label.hide()
        self.action_state_badge.hide()
        self.action_detail_label.hide()
        self.run_button.hide()

        self.workflow_template_combo.currentIndexChanged.connect(
            self._on_workflow_config_changed
        )
        self.backend_combo.currentIndexChanged.connect(self._on_workflow_config_changed)
        self.enable_25d_checkbox.toggled.connect(self._on_workflow_config_changed)
        self.enable_execution_checkbox.toggled.connect(self._on_workflow_config_changed)
        self.enable_update_checkbox.toggled.connect(self._on_workflow_config_changed)

        layout.addWidget(workspace_card)
        layout.addWidget(self.workflow_rail_card, 1)
        return pane

    def _build_middle_pane(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header_card = QFrame(pane)
        header_card.setObjectName("StepHeaderCard")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(20, 20, 20, 20)
        header_layout.setSpacing(10)

        step_eyebrow = QLabel("PROMPT", header_card)
        set_role(step_eyebrow, "eyebrow")

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        self.step_title_label = QLabel(header_card)
        set_role(self.step_title_label, "title")
        self.step_state_badge = QLabel(header_card)
        self.step_state_badge.setProperty("pill", True)
        refresh_style(self.step_state_badge)
        title_row.addWidget(self.step_title_label, 1)
        title_row.addWidget(self.step_state_badge)

        self.step_summary_label = QLabel(header_card)
        self.step_summary_label.setWordWrap(True)
        set_role(self.step_summary_label, "subtitle")
        self.step_gate_label = QLabel(header_card)
        self.step_gate_label.setWordWrap(True)
        set_role(self.step_gate_label, "statusText")
        set_tone(self.step_gate_label, "muted")

        self.run_state_card = QFrame(header_card)
        self.run_state_card.setObjectName("RunStateCard")
        run_state_layout = QVBoxLayout(self.run_state_card)
        run_state_layout.setContentsMargins(14, 14, 14, 14)
        run_state_layout.setSpacing(8)
        run_header = QHBoxLayout()
        run_header.setContentsMargins(0, 0, 0, 0)
        run_header.setSpacing(8)
        self.run_state_badge = QLabel("RUNNING", self.run_state_card)
        self.run_state_badge.setProperty("pill", True)
        refresh_style(self.run_state_badge)
        set_tone(self.run_state_badge, "info")
        self.run_status_label = QLabel(self.run_state_card)
        set_role(self.run_status_label, "statusText")
        set_tone(self.run_status_label, "info")
        self.run_progress_bar = QProgressBar(self.run_state_card)
        self.run_progress_bar.setRange(0, 0)
        self.run_progress_bar.setTextVisible(False)
        run_header.addWidget(self.run_state_badge)
        run_header.addWidget(self.run_status_label, 1)
        run_state_layout.addLayout(run_header)
        run_state_layout.addWidget(self.run_progress_bar)
        self.run_state_card.hide()

        header_layout.addWidget(step_eyebrow)
        header_layout.addLayout(title_row)
        header_layout.addWidget(self.step_summary_label)
        header_layout.addWidget(self.step_gate_label)
        header_layout.addWidget(self.run_state_card)

        self.prompt_scroll = QScrollArea(pane)
        self.prompt_scroll.setWidgetResizable(True)
        self.prompt_scroll.setFrameShape(QFrame.NoFrame)
        prompt_content = QWidget(self.prompt_scroll)
        prompt_layout = QVBoxLayout(prompt_content)
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        prompt_layout.setSpacing(14)

        self.description_edit = QPlainTextEdit(prompt_content)
        self.description_edit.setPlaceholderText(
            "Editable step description. For most steps this is appended to the main case description."
        )
        self.description_edit.textChanged.connect(self._on_description_text_changed)

        self.description_group = QGroupBox("Description", prompt_content)
        description_layout = QVBoxLayout(self.description_group)
        description_layout.setSpacing(10)
        description_layout.addWidget(self.description_edit, 1)

        self.description_append_label = QLabel(
            "Auto-appended feedback for this step",
            self.description_group,
        )
        set_role(self.description_append_label, "eyebrow")
        self.description_append_label.hide()

        self.description_append_preview = QPlainTextEdit(self.description_group)
        self.description_append_preview.setReadOnly(True)
        self.description_append_preview.setMaximumHeight(150)
        self.description_append_preview.hide()
        description_layout.addWidget(self.description_append_label)
        description_layout.addWidget(self.description_append_preview)

        self.attachments_group = QGroupBox("Attachments and Preview", prompt_content)
        attachments_layout = QVBoxLayout(self.attachments_group)
        attachments_layout.setContentsMargins(10, 10, 10, 10)
        attachments_layout.setSpacing(12)
        attachments_layout.addWidget(self._build_attachment_section())

        self.artifacts_group = QGroupBox("Select Artifacts and Preview", prompt_content)
        artifacts_layout = QVBoxLayout(self.artifacts_group)
        artifacts_layout.setContentsMargins(10, 10, 10, 10)
        artifacts_layout.setSpacing(12)
        artifacts_layout.addWidget(self._build_artifact_section())

        prompt_layout.addWidget(self.description_group)
        prompt_layout.addWidget(self.attachments_group)
        prompt_layout.addWidget(self.artifacts_group)
        prompt_layout.addStretch(1)
        self.prompt_scroll.setWidget(prompt_content)

        layout.addWidget(header_card)
        layout.addWidget(self.prompt_scroll, 1)
        return pane

    def _build_right_pane(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header_card = QFrame(pane)
        header_card.setObjectName("ConsoleCard")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(18, 18, 18, 18)
        header_layout.setSpacing(6)
        preview_eyebrow = QLabel("RESULTS", header_card)
        set_role(preview_eyebrow, "eyebrow")
        preview_title = QLabel("Structured outputs, generated files, logs, and review items.", header_card)
        preview_title.setWordWrap(True)
        set_role(preview_title, "subtitle")
        self.tabs = QTabWidget(pane)
        self.structure_tab = self._build_structure_tab()
        self.tabs.addTab(self.structure_tab, "Structure")
        self.tabs.addTab(self._build_outputs_tab(), "Outputs")
        self.tabs.addTab(self._build_review_tab(), "Review")

        header_layout.addWidget(preview_eyebrow)
        header_layout.addWidget(preview_title)
        layout.addWidget(header_card)
        layout.addWidget(self.tabs, 1)
        return pane

    def _build_structure_tab(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)

        self.structure_stack = QStackedWidget(pane)

        self.structure_empty_label = QLabel(pane)
        self.structure_empty_label.setWordWrap(True)
        self.structure_empty_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.structure_stack.addWidget(self.structure_empty_label)

        parameters_page = QWidget(pane)
        parameters_layout = QVBoxLayout(parameters_page)
        self.parameters_summary_label = QLabel(parameters_page)
        self.parameters_summary_label.setWordWrap(True)
        self.parameters_table = QTableWidget(parameters_page)
        self.parameters_table.setColumnCount(3)
        self.parameters_table.setHorizontalHeaderLabels(["Name", "Value", "Notes"])
        self.parameters_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.parameters_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        parameters_layout.addWidget(self.parameters_summary_label)
        parameters_layout.addWidget(self.parameters_table)
        self.structure_stack.addWidget(parameters_page)

        materials_page = QWidget(pane)
        materials_layout = QVBoxLayout(materials_page)
        self.materials_summary_label = QLabel(materials_page)
        self.materials_summary_label.setWordWrap(True)
        self.materials_table = QTableWidget(materials_page)
        self.materials_table.setColumnCount(2)
        self.materials_table.setHorizontalHeaderLabels(["Name", "File"])
        self.materials_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.materials_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        materials_layout.addWidget(self.materials_summary_label)
        materials_layout.addWidget(self.materials_table)
        self.structure_stack.addWidget(materials_page)

        solids_page = QWidget(pane)
        solids_layout = QVBoxLayout(solids_page)
        self.solids_summary_label = QLabel(solids_page)
        self.solids_summary_label.setWordWrap(True)
        self.solids_splitter = QSplitter(Qt.Horizontal, solids_page)
        self.solids_list = QListWidget(self.solids_splitter)
        self.solids_list.currentItemChanged.connect(self._on_solid_selected)
        self.solids_detail = QPlainTextEdit(self.solids_splitter)
        self.solids_detail.setReadOnly(True)
        self.solids_splitter.setSizes([260, 420])
        solids_layout.addWidget(self.solids_summary_label)
        solids_layout.addWidget(self.solids_splitter)
        self.structure_stack.addWidget(solids_page)

        layout.addWidget(self.structure_stack)
        return pane

    def _build_attachment_section(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.attachments_list = QListWidget(pane)
        self.attachments_list.currentItemChanged.connect(
            self._on_attachment_selected
        )
        self.attachments_list.itemChanged.connect(self._on_attachment_toggled)

        button_row = QHBoxLayout()
        self.add_text_button = QPushButton("Add Text", pane)
        self.add_text_button.clicked.connect(self._add_text_attachment)
        self.add_files_button = QPushButton("Add Files", pane)
        self.add_files_button.clicked.connect(self._add_file_attachments)
        self.add_images_button = QPushButton("Add Images", pane)
        self.add_images_button.clicked.connect(self._add_image_attachments)
        self.remove_attachment_button = QPushButton("Remove", pane)
        self.remove_attachment_button.clicked.connect(self._remove_attachment)
        self.move_up_attachment_button = QPushButton("Up", pane)
        self.move_up_attachment_button.clicked.connect(lambda: self._move_attachment(-1))
        self.move_down_attachment_button = QPushButton("Down", pane)
        self.move_down_attachment_button.clicked.connect(lambda: self._move_attachment(1))

        for widget in [
            self.add_text_button,
            self.add_files_button,
            self.add_images_button,
            self.remove_attachment_button,
            self.move_up_attachment_button,
            self.move_down_attachment_button,
        ]:
            button_row.addWidget(widget)

        preview_label = QLabel("Preview", pane)
        set_role(preview_label, "eyebrow")

        self.attachment_preview_stack = QStackedWidget(pane)

        self.attachment_empty_label = QLabel(
            "Select an attachment to preview its content.",
            pane,
        )
        self.attachment_empty_label.setWordWrap(True)
        self.attachment_empty_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.attachment_preview_stack.addWidget(self.attachment_empty_label)

        self.attachment_preview_tabs = QTabWidget(pane)

        text_page = QWidget(pane)
        text_layout = QVBoxLayout(text_page)
        text_layout.setContentsMargins(0, 0, 0, 0)
        self.attachment_editor = QPlainTextEdit(text_page)
        self.attachment_editor.setPlaceholderText(
            "Text attachments can be viewed and edited here."
        )
        self.save_attachment_button = QPushButton(
            "Save Attachment Content",
            text_page,
        )
        self.save_attachment_button.clicked.connect(self._save_attachment_text)
        text_layout.addWidget(self.attachment_editor)
        text_layout.addWidget(self.save_attachment_button)
        self.attachment_preview_tabs.addTab(text_page, "Text")

        image_page = QWidget(pane)
        image_layout = QVBoxLayout(image_page)
        image_layout.setContentsMargins(0, 0, 0, 0)
        self.attachment_image_caption = QLabel(image_page)
        self.attachment_image_caption.setWordWrap(True)
        self.attachment_image_scroll = QScrollArea(image_page)
        self.attachment_image_scroll.setWidgetResizable(True)
        self.attachment_image_label = QLabel(self.attachment_image_scroll)
        self.attachment_image_label.setAlignment(Qt.AlignCenter)
        self.attachment_image_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.attachment_image_scroll.setWidget(self.attachment_image_label)
        image_layout.addWidget(self.attachment_image_caption)
        image_layout.addWidget(self.attachment_image_scroll, 1)
        self.attachment_preview_tabs.addTab(image_page, "Image")

        metadata_page = QWidget(pane)
        metadata_layout = QVBoxLayout(metadata_page)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        self.attachment_metadata_view = QPlainTextEdit(metadata_page)
        self.attachment_metadata_view.setReadOnly(True)
        metadata_layout.addWidget(self.attachment_metadata_view)
        self.attachment_preview_tabs.addTab(metadata_page, "Metadata")

        self.attachment_preview_stack.addWidget(self.attachment_preview_tabs)

        layout.addWidget(self.attachments_list, 1)
        layout.addLayout(button_row)
        layout.addWidget(preview_label)
        layout.addWidget(self.attachment_preview_stack, 1)
        return pane

    def _build_artifact_section(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.artifact_selection_help = QLabel(pane)
        self.artifact_selection_help.setWordWrap(True)
        set_role(self.artifact_selection_help, "muted")

        self.artifact_selection_list = QListWidget(pane)
        self.artifact_selection_list.currentItemChanged.connect(
            self._on_selected_prompt_artifact_changed
        )
        self.artifact_selection_list.itemChanged.connect(
            self._on_artifact_selection_changed
        )

        preview_label = QLabel("Preview", pane)
        set_role(preview_label, "eyebrow")
        self.artifact_selection_preview = QPlainTextEdit(pane)
        self.artifact_selection_preview.setReadOnly(True)

        layout.addWidget(self.artifact_selection_help)
        layout.addWidget(self.artifact_selection_list, 1)
        layout.addWidget(preview_label)
        layout.addWidget(self.artifact_selection_preview, 1)
        return pane

    def _build_outputs_tab(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        outputs_splitter = QSplitter(Qt.Vertical, pane)
        outputs_top = QWidget(outputs_splitter)
        outputs_top_layout = QVBoxLayout(outputs_top)
        outputs_top_layout.setContentsMargins(0, 0, 0, 0)
        outputs_top_layout.setSpacing(12)
        self.artifacts_list = QListWidget(outputs_top)
        self.artifacts_list.currentItemChanged.connect(self._on_artifact_selected)
        self.artifact_preview = QPlainTextEdit(outputs_top)
        self.artifact_preview.setReadOnly(True)
        outputs_top_layout.addWidget(self.artifacts_list, 1)
        outputs_top_layout.addWidget(self.artifact_preview, 2)

        outputs_bottom = QWidget(outputs_splitter)
        outputs_bottom_layout = QVBoxLayout(outputs_bottom)
        outputs_bottom_layout.setContentsMargins(0, 0, 0, 0)
        outputs_bottom_layout.setSpacing(8)
        logs_label = QLabel("Execution Logs", outputs_bottom)
        set_role(logs_label, "eyebrow")
        self.logs_view = QPlainTextEdit(outputs_bottom)
        self.logs_view.setReadOnly(True)
        outputs_bottom_layout.addWidget(logs_label)
        outputs_bottom_layout.addWidget(self.logs_view, 1)
        outputs_splitter.setSizes([420, 180])
        layout.addWidget(outputs_splitter)
        return pane

    def _build_review_tab(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        self.issues_list = QListWidget(pane)
        self.issues_list.currentItemChanged.connect(self._on_issue_selected)
        self.issue_detail = QPlainTextEdit(pane)
        self.issue_detail.setReadOnly(True)
        layout.addWidget(self.issues_list, 1)
        layout.addWidget(self.issue_detail, 2)
        return pane

    def _new_session(self) -> None:
        self._save_editor_to_state()
        if self._ensure_launchpad_runtime_ready() is None:
            return
        self._start_project_flow()

    def _return_to_launchpad(self) -> None:
        self._save_editor_to_state()
        if self._run_thread is not None:
            QMessageBox.information(
                self,
                "Run In Progress",
                "Wait for the current step to finish before switching workspaces.",
            )
            return
        if self.session is not None:
            self._autosave_session_snapshot(update_recent=True)
        self.session = None
        self.current_step_id = INPUT_STEP_ID
        self._current_attachment_id = None
        self._refresh_all()
        self.statusBar().showMessage(
            "Returned to the launchpad. Create, open, or load an example workspace.",
            4000,
        )

    def _open_workspace(self) -> None:
        self._save_editor_to_state()
        if self._ensure_launchpad_runtime_ready() is None:
            return
        path = QFileDialog.getExistingDirectory(
            self,
            "Open LEAM Workspace",
            self.session_store.default_workspace_root(),
        )
        if not path:
            return
        self._load_workspace_path(path)

    def _save_session(self) -> None:
        if self.session is None:
            return
        self._save_editor_to_state()
        self._sync_workspace_folder_backend(update_recent=True)
        path = self._autosave_session_snapshot(
            update_recent=True,
            announce_failures=True,
        )
        if path:
            self.statusBar().showMessage(f"Saved workspace snapshot to {path}", 4000)

    def _save_session_as(self) -> None:
        if self.session is None:
            return
        self._save_editor_to_state()
        self._sync_workspace_folder_backend(update_recent=True)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export LEAM Session JSON",
            self.session.session_file
            or str(Path(self.session.workspace_dir) / "session.json"),
            "LEAM Session (*.json)",
        )
        if not path:
            return
        previous_session_file = self.session.session_file
        payload = self.engine.serialise_session(self.session)
        saved = self.session_store.save_session(self.session, payload, path)
        if self.session.workspace_dir:
            self.session.session_file = str(
                Path(self.session.workspace_dir) / "session.json"
            )
        else:
            self.session.session_file = previous_session_file
        self.statusBar().showMessage(f"Exported session JSON to {saved}", 4000)
        self._refresh_left_pane()

    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.clear()
        for path in self.recent_store.load():
            action = QAction(path, self)
            action.setData(path)
            action.triggered.connect(
                lambda checked=False, session_path=path: self._open_recent(
                    session_path
                )
            )
            self.recent_menu.addAction(action)
        if not self.recent_menu.actions():
            empty = QAction("(No recent sessions)", self)
            empty.setEnabled(False)
            self.recent_menu.addAction(empty)
        self._refresh_launchpad_recents()
        self._refresh_chrome()

    def _open_recent(self, path: str) -> None:
        if self._ensure_launchpad_runtime_ready() is None:
            return
        workspace_path = self.recent_store._normalise_workspace_path(path)
        if workspace_path is None:
            self.recent_store.remove(path)
            self._rebuild_recent_menu()
            QMessageBox.warning(
                self,
                "Missing Workspace",
                f"Workspace is no longer valid and was removed from recents:\n{path}",
            )
            return
        self._load_workspace_path(workspace_path)

    def _load_example(self, preset_key: str) -> None:
        self._save_editor_to_state()
        if self._start_project_flow(example_key=preset_key):
            preset = get_example_preset(preset_key)
            self.statusBar().showMessage(
                f"Loaded built-in example: {preset.title}",
                5000,
            )

    def _refresh_all(self) -> None:
        if self.session is not None:
            self.engine.refresh_session(self.session)
            self._sync_managed_inputs()
            if (
                self.current_step_id == INPUT_STEP_ID
                and self._is_workflow_config_locked()
            ):
                self.current_step_id = self._default_focus_step_id()
        self._refresh_chrome()
        self._refresh_launchpad()
        self._refresh_workflow_config()
        self._refresh_left_pane()
        self._load_current_step()
        self._update_status_bar()
        self._autosave_session_snapshot()

    def _load_workspace_path(self, path: str) -> None:
        """Load one workspace folder or legacy session JSON path."""
        self.session = self.session_store.load_workspace(path)
        self.engine.refresh_session(self.session)
        self._restore_reconstructed_check_solid_issues()
        self.current_step_id = self._default_focus_step_id()
        self._autosave_session_snapshot(update_recent=True)
        self._refresh_all()

    def _restore_reconstructed_check_solid_issues(self) -> None:
        """Rebuild routed refill state for legacy workspaces without `session.json`."""
        if self.session is None:
            return
        check_state = self.session.steps.get("check_solid")
        if not check_state:
            return
        if check_state.status != "issues" or not check_state.raw_issues or check_state.issues:
            return
        definition = self.engine.get_step_definition(self.session, "check_solid")
        self.session.issues = self.engine.apply_check_refills(
            self.session,
            definition,
            check_state.raw_issues,
        )
        self.engine.refresh_session(self.session)

    def _autosave_session_snapshot(
        self,
        *,
        update_recent: bool = False,
        announce_failures: bool = False,
    ) -> Optional[str]:
        """Persist one workspace-local `session.json` snapshot."""
        if self.session is None or not self.session.workspace_dir:
            return None
        try:
            payload = self.engine.serialise_session(self.session)
            path = self.session_store.save_session(
                self.session,
                payload,
                str(Path(self.session.workspace_dir) / "session.json"),
            )
        except Exception as exc:
            if announce_failures:
                QMessageBox.warning(
                    self,
                    "Snapshot Save Failed",
                    str(exc),
                )
            return None
        if update_recent:
            self.recent_store.add(self.session.workspace_dir)
            self._rebuild_recent_menu()
        return path

    def _sync_managed_inputs(self) -> None:
        if self.session is None:
            return
        for step_id, state in self.session.steps.items():
            self.session_store.sync_description_attachment(
                self.session,
                step_id,
                state.description,
            )

    def _input_state(self):
        if self.session is None:
            return None
        return self.session.steps.get(INPUT_STEP_ID)

    def _visible_workflow_definitions(self):
        if self.session is None:
            return []
        return [
            definition
            for definition in self.engine.get_visible_step_definitions(self.session)
            if definition.id != INPUT_STEP_ID
        ]

    def _is_workflow_config_locked(self) -> bool:
        input_state = self._input_state()
        return bool(input_state and input_state.status == "success")

    def _step_track_hint(self, definition, display_status: str) -> str:
        if definition.id == INPUT_STEP_ID:
            if display_status == "success":
                return "Workflow branches locked and ready."
            if display_status == "running":
                return "Applying workspace setup now."
            return "Configure the workspace branches, then apply setup."
        if display_status == "waiting":
            return "Waiting for upstream outputs."
        if display_status == "running":
            return "Currently executing."
        if display_status == "success":
            return "Outputs ready."
        if display_status == "issues":
            return "Issues found. Review before continuing."
        if display_status == "blocked_by_upstream":
            return "Blocked by an earlier step."
        if display_status == "rerun_required":
            return "Needs rerun after upstream changes."
        if display_status == "stale":
            return "Out of date after upstream changes."
        if display_status == "error":
            return "Run failed. Check logs."
        if definition.is_optional:
            return "Optional branch."
        return "Ready when upstream inputs are available."

    def _default_focus_step_id(self) -> str:
        if self.session is None:
            return INPUT_STEP_ID
        visible_definitions = self._visible_workflow_definitions()
        if not visible_definitions:
            return INPUT_STEP_ID
        if not self._is_workflow_config_locked():
            return visible_definitions[0].id

        fallback_step_id: Optional[str] = None
        for definition in visible_definitions:
            if fallback_step_id is None:
                fallback_step_id = definition.id
            if self.engine.get_step_blocker(self.session, definition.id) is None:
                return definition.id
        return fallback_step_id or INPUT_STEP_ID

    def _select_step(self, step_id: str) -> None:
        if self._step_switch_locked():
            return
        item = self._step_items.get(step_id)
        if item is None:
            return
        if self.step_list.currentItem() is item:
            return
        self.step_list.setCurrentItem(item)

    def _sync_current_step_action_controls(self) -> None:
        current_widget = self._step_item_widgets.get(self.current_step_id)
        if current_widget is None:
            return
        current_widget.title_label.setText(self.action_step_label.text())
        current_widget.status_badge.setText(self.action_state_badge.text())
        current_widget.status_badge.setMinimumWidth(78)
        current_widget.status_badge.setProperty(
            "tone",
            self.action_state_badge.property("tone"),
        )
        refresh_style(current_widget.status_badge)
        current_widget.set_expanded(
            True,
            detail_text=self.action_detail_label.text(),
            action_text=self.run_button.text(),
            action_enabled=self.run_button.isEnabled(),
        )
        current_item = self._step_items.get(self.current_step_id)
        if current_item is not None:
            current_item.setSizeHint(current_widget.sizeHint())

    def _sync_workflow_config_height(self) -> None:
        current_page = self.workflow_config_stack.currentWidget()
        if current_page is None:
            return
        target_height = current_page.sizeHint().height()
        if target_height <= 0:
            target_height = current_page.minimumSizeHint().height()
        self.workflow_config_stack.setFixedHeight(max(target_height, 1))

    def _refresh_workflow_config(self) -> None:
        if self.session is None:
            self.workflow_config_group.setEnabled(False)
            self.workflow_warning_label.setText("")
            self.workflow_locked_summary_label.setText("")
            self.workflow_locked_warning_label.setText("")
            self.workflow_apply_button.setEnabled(False)
            self.workflow_apply_button.setText("Apply Workspace Setup")
            self.workflow_config_stack.setCurrentWidget(self.workflow_config_edit_page)
            self.workflow_warning_label.hide()
            self.workflow_locked_warning_label.hide()
            self._sync_workflow_config_height()
            return

        input_state = self._input_state()
        env = self._environment_report()
        self._ui_updating = True
        self.workflow_config_group.setEnabled(True)
        template_value = (
            input_state.settings.get("template", "strong_description")
            if input_state
            else "strong_description"
        )
        combo_index = self.workflow_template_combo.findData(template_value)
        if combo_index >= 0:
            self.workflow_template_combo.setCurrentIndex(combo_index)
        backend_value = (
            input_state.settings.get("backend", "cst")
            if input_state
            else "cst"
        )
        if backend_value not in BACKEND_CHOICES.values():
            backend_value = self._first_available_backend(env)
        backend_index = self.backend_combo.findData(backend_value)
        if backend_index >= 0:
            self.backend_combo.setCurrentIndex(backend_index)
        available_backends = set(self._available_backends(env))
        for backend in BACKEND_CHOICES.values():
            self._set_backend_combo_item_enabled(
                backend,
                backend in available_backends or backend == backend_value,
            )
        self.enable_25d_checkbox.setChecked(
            bool(input_state.settings.get("enable_25d", False)) if input_state else False
        )
        self.enable_execution_checkbox.setChecked(
            bool(input_state.settings.get("enable_execution", False)) if input_state else False
        )
        self.enable_update_checkbox.setChecked(
            bool(input_state.settings.get("enable_parameter_update", False))
            if input_state
            else False
        )
        template_title = next(
            (label for label, value in TEMPLATE_CHOICES.items() if value == template_value),
            template_value.replace("_", " ").title(),
        )
        backend_title = next(
            (label for label, value in BACKEND_CHOICES.items() if value == backend_value),
            str(backend_value).upper(),
        )
        self.workflow_locked_backend_badge.setText(str(backend_title).upper())
        self.workflow_locked_template_badge.setText(template_title)
        self.workflow_locked_template_badge.setToolTip(template_title)
        self.workflow_locked_summary_label.setText(
            " | ".join(
                [
                    f"2.5D {'enabled' if self.enable_25d_checkbox.isChecked() else 'disabled'}",
                    (
                        "Simulator execution enabled"
                        if self.enable_execution_checkbox.isChecked()
                        else "Simulator execution disabled"
                    ),
                    (
                        "Parameter update enabled"
                        if self.enable_update_checkbox.isChecked()
                        else "Parameter update disabled"
                    ),
                ]
            )
        )
        self.workflow_apply_button.setText("Apply Workspace Setup")
        if self._is_workflow_config_locked():
            self.workflow_config_stack.setCurrentWidget(self.workflow_config_locked_page)
        else:
            self.workflow_config_stack.setCurrentWidget(self.workflow_config_edit_page)
        self._ui_updating = False
        self._refresh_workflow_warning()
        self._sync_workflow_config_height()

    def _refresh_workflow_warning(self) -> None:
        if self.session is None:
            self.workflow_warning_label.setText("")
            return
        input_state = self._input_state()
        env = self._environment_report()
        warnings = []
        enable_25d = bool(input_state.settings.get("enable_25d", False)) if input_state else False
        enable_execution = (
            bool(input_state.settings.get("enable_execution", False))
            if input_state
            else False
        )
        backend_value = (
            str(input_state.settings.get("backend", "cst")).strip().lower()
            if input_state
            else "cst"
        )
        solids_state = self.session.steps.get("solids")
        if (
            enable_25d
            and solids_state is not None
            and solids_state.status in {"success", "issues", "stale"}
            and not bool(self.session.flags.get("has_25d"))
        ):
            warnings.append(
                "2.5D is enabled, but the latest solids result does not contain any 2.5D items."
            )
        if enable_execution and not bool(env.get("unsafe_execution_enabled")):
            warnings.append(str(env.get("unsafe_execution_message") or "").strip())
        if backend_value in BACKEND_CHOICES.values() and not self._backend_available(
            backend_value,
            env,
        ):
            backend_message = str(
                env.get(f"{backend_value}_available_message")
                or f"{backend_value.upper()} runtime is not available."
            ).strip()
            warnings.append(f"{backend_value.upper()}: {backend_message}")
        warning_text = "\n".join(warnings)
        self.workflow_warning_label.setText(warning_text)
        self.workflow_warning_label.setVisible(bool(warning_text))
        self.workflow_locked_warning_label.setText(warning_text)
        self.workflow_locked_warning_label.setVisible(bool(warning_text))
        self._sync_workflow_config_height()

    def _confirm_execution_enable_opt_in(self) -> bool:
        input_state = self._input_state()
        if input_state and bool(
            input_state.settings.get("execution_warning_acknowledged", False)
        ):
            return True

        env = self._environment_report()
        message_lines = [
            "Local simulator execution runs generated HFSS Python or CST VBA on this machine.",
            "",
            "Enabling this workspace option exposes the execution steps for this workspace.",
            "Global runtime execution is disabled by default.",
            "If you need to enable it later, use either of these overrides:",
            "- Set LEAM_ALLOW_UNSAFE_EXECUTION=1 for the current shell",
            "- or set `allow_unsafe_execution: true` in your LEAM config",
            "",
            "Only enable this when you trust the prompts, attachments, and generated artifacts.",
        ]
        runtime_message = str(env.get("unsafe_execution_message") or "").strip()
        if runtime_message:
            message_lines.extend(["", f"Current runtime status: {runtime_message}"])
        message_lines.extend(["", "Enable simulator execution for this workspace?"])
        result = QMessageBox.warning(
            self,
            "Enable Local Simulator Execution",
            "\n".join(message_lines),
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if result == QMessageBox.Yes and input_state is not None:
            input_state.settings["execution_warning_acknowledged"] = True
            return True
        return result == QMessageBox.Yes

    def _on_workflow_config_changed(self) -> None:
        if self._ui_updating or self.session is None or self._is_workflow_config_locked():
            return
        self._save_editor_to_state()
        input_state = self._input_state()
        if input_state is None:
            return
        previous_enable_execution = bool(
            input_state.settings.get("enable_execution", False)
        )
        requested_enable_execution = self.enable_execution_checkbox.isChecked()
        if requested_enable_execution and not previous_enable_execution:
            if not self._confirm_execution_enable_opt_in():
                self._ui_updating = True
                self.enable_execution_checkbox.setChecked(False)
                self._ui_updating = False
                self._refresh_workflow_warning()
                return
        input_state.settings["template"] = self.workflow_template_combo.currentData()
        input_state.settings["backend"] = self.backend_combo.currentData()
        input_state.settings["enable_25d"] = self.enable_25d_checkbox.isChecked()
        input_state.settings["enable_execution"] = requested_enable_execution
        input_state.settings["enable_parameter_update"] = (
            self.enable_update_checkbox.isChecked()
        )
        self.engine.refresh_session(self.session)
        self.current_step_id = self._default_focus_step_id()
        self._refresh_all()

    def _refresh_left_pane(self) -> None:
        if self.session is None:
            self.step_list.clear()
            self._step_items.clear()
            self._step_item_widgets.clear()
            self._step_display_statuses.clear()
            self._step_definitions_by_id.clear()
            self.session_title_label.setText("Launchpad Ready")
            self.session_meta_label.setText(
                "Create a workspace or open one to enter the LEAM control surface."
            )
            self.session_meta_label.setToolTip("")
            self.workspace_detail_label.setText(
                "Resume workspace by selecting a directory from Open Workspace or Recent Workspaces."
            )
            self.workspace_detail_label.setVisible(True)
            self.workspace_status_badge.setText("OFFLINE")
            set_tone(self.workspace_status_badge, "muted")
            self.workspace_backend_badge.hide()
            self.workspace_template_badge.hide()
            self._update_interaction_state()
            return
        self._ui_updating = True
        workspace_name = Path(self.session.workspace_dir).name or self.session.workspace_dir
        self.session_title_label.setText(self.session.title or workspace_name)
        self.session_meta_label.setText(self.session.workspace_dir)
        self.session_meta_label.setToolTip(self.session.workspace_dir)
        self.workspace_detail_label.setText("")
        self.workspace_detail_label.setVisible(False)
        self.workspace_status_badge.setText(self._format_step_status(self.session.status))
        set_tone(self.workspace_status_badge, status_tone(self.session.status))
        self.workspace_backend_badge.hide()
        self.workspace_template_badge.hide()
        self.step_list.clear()
        self._step_items = {}
        self._step_item_widgets = {}
        self._step_display_statuses = {}
        self._step_definitions_by_id = {}
        current_item = None
        for definition in self._visible_workflow_definitions():
            display_status = self.engine.get_display_status(
                self.session,
                definition.id,
            )
            self._step_display_statuses[definition.id] = display_status
            self._step_definitions_by_id[definition.id] = definition
            item = QListWidgetItem(definition.title, self.step_list)
            item.setData(Qt.UserRole, definition.id)
            item.setToolTip(
                f"{definition.title}\nStatus: {self._format_step_status(display_status)}"
            )
            widget = StepListItemWidget(self.step_list)
            widget.update_content(
                title=definition.title,
                step_id=definition.id,
                status=display_status,
                meta_text=self._step_track_hint(definition, display_status),
            )
            widget.activated.connect(self._select_step)
            widget.run_requested.connect(lambda _step_id: self._run_current_step())
            item.setSizeHint(widget.sizeHint())
            self.step_list.setItemWidget(item, widget)
            self._step_items[definition.id] = item
            self._step_item_widgets[definition.id] = widget
            if definition.id == self.current_step_id:
                current_item = item
        if current_item is None and self.step_list.count() > 0:
            preferred_step_id = self._default_focus_step_id()
            current_item = self._step_items.get(preferred_step_id, self.step_list.item(0))
            self.current_step_id = current_item.data(Qt.UserRole)
        if current_item is not None:
            self.step_list.setCurrentItem(current_item)
        self._ui_updating = False
        self._sync_step_track_selection()
        self._update_interaction_state()

    def _sync_step_track_selection(self) -> None:
        current_item = self.step_list.currentItem()
        current_step_id = current_item.data(Qt.UserRole) if current_item is not None else None
        for step_id, widget in self._step_item_widgets.items():
            definition = self._step_definitions_by_id.get(step_id)
            display_status = self._step_display_statuses.get(step_id, "idle")
            if definition is not None:
                widget.update_content(
                    title=definition.title,
                    step_id=definition.id,
                    status=display_status,
                    meta_text=self._step_track_hint(definition, display_status),
                )
            is_selected = step_id == current_step_id
            widget.set_selected(is_selected)
            widget.set_expanded(is_selected)
            item = self._step_items.get(step_id)
            if item is not None:
                item.setSizeHint(widget.sizeHint())

    def _refresh_description_appendix(self, refill_notes: str) -> None:
        notes = str(refill_notes).strip()
        has_notes = bool(notes)
        self.description_append_label.setVisible(has_notes)
        self.description_append_preview.setVisible(has_notes)
        self.description_append_preview.setPlainText(notes if has_notes else "")

    def _load_current_step(self) -> None:
        if self.session is None:
            self.step_title_label.setText("No Active Workspace")
            self.step_summary_label.setText(
                "Open or create a workspace from the launchpad. The workflow console will activate after a workspace is loaded."
            )
            self.step_gate_label.setText("")
            self.step_state_badge.setText("IDLE")
            set_tone(self.step_state_badge, "muted")
            self.run_state_card.hide()
            self.description_edit.setPlainText("")
            self._refresh_description_appendix("")
            self.attachments_list.clear()
            self.artifact_selection_list.clear()
            self.artifact_selection_preview.setPlainText(
                "Open a workspace to inspect selected upstream artifacts."
            )
            self.artifact_selection_help.setText("")
            self.artifacts_group.setVisible(False)
            self._show_attachment_empty_preview(
                "Open or create a workspace first, then select an attachment to preview it here."
            )
            self._show_structure_empty(
                "Open or create a workspace first. Structured results will appear here after running parameters, materials, or solids."
            )
            self.artifacts_list.clear()
            self.artifact_preview.setPlainText(
                "Open or create a workspace to start running the LEAM workflow."
            )
            self.issues_list.clear()
            self.issue_detail.setPlainText("")
            self.logs_view.setPlainText("")
            self._update_interaction_state()
            return
        definition = self.engine.get_step_definition(self.session, self.current_step_id)
        state = self.session.steps[self.current_step_id]
        display_status = self.engine.get_display_status(self.session, definition.id)

        self._ui_updating = True
        self.step_title_label.setText(definition.title)
        self.step_state_badge.setText(self._format_step_status(display_status))
        set_tone(self.step_state_badge, status_tone(display_status))
        self.step_summary_label.setText(
            STEP_SUMMARIES.get(
                definition.id,
                "Attach extra notes or files here, then run the current step when its upstream inputs are ready.",
            )
        )
        self.description_edit.setPlainText(state.description)
        self._refresh_description_appendix(state.refill_notes)

        self._refresh_resources_tab()
        self._refresh_structure_tab()
        self._refresh_artifacts_tab()
        self._refresh_issues_tab()
        self._refresh_logs_tab()
        self._ui_updating = False
        self._update_interaction_state()

    def _save_editor_to_state(self) -> None:
        if self._ui_updating or self.session is None:
            return
        state = self.session.steps.get(self.current_step_id)
        if not state:
            return
        state.description = self.description_edit.toPlainText().strip()
        self.session_store.sync_description_attachment(
            self.session,
            self.current_step_id,
            state.description,
        )
        self.engine.refresh_session(self.session)
        self._autosave_session_snapshot()
        self._update_interaction_state()

    def _on_description_text_changed(self) -> None:
        if self._ui_updating:
            return

    def _on_step_changed(self, current, previous) -> None:
        if self._ui_updating or current is None:
            return
        if self._step_switch_locked():
            restore_item = self._step_items.get(self.current_step_id) or previous
            if restore_item is not None and current is not restore_item:
                self._ui_updating = True
                self.step_list.setCurrentItem(restore_item)
                self._ui_updating = False
            return
        self._save_editor_to_state()
        self.current_step_id = current.data(Qt.UserRole)
        self._sync_step_track_selection()
        self._load_current_step()
        self._update_status_bar()

    def _run_current_step(self) -> None:
        self._run_step_by_id(self.current_step_id)

    def _run_workspace_setup(self) -> None:
        self._run_step_by_id(INPUT_STEP_ID)

    def _run_step_by_id(self, step_id: str) -> None:
        if self._run_thread is not None or self.session is None:
            return
        self._save_editor_to_state()
        blocker = self.engine.get_step_blocker(self.session, step_id)
        if blocker:
            self.statusBar().showMessage(blocker, 5000)
            return
        definition = self.engine.get_step_definition(
            self.session,
            step_id,
        )
        self._running_step_id = step_id
        self._set_running_state(True, definition.title)

        self._run_thread = QThread(self)
        self._run_worker = StepRunWorker(
            self.engine,
            self.session,
            step_id,
        )
        self._run_worker.moveToThread(self._run_thread)
        self._run_thread.started.connect(self._run_worker.run)
        self._run_worker.finished.connect(self._on_step_run_success)
        self._run_worker.failed.connect(self._on_step_run_failure)
        self._run_worker.finished.connect(self._run_thread.quit)
        self._run_worker.failed.connect(self._run_thread.quit)
        self._run_thread.finished.connect(self._cleanup_run_worker)
        self._run_thread.start()

    def _set_running_state(self, running: bool, step_title: str = "") -> None:
        self.step_list.setEnabled(not running)
        self.description_edit.setReadOnly(running)
        self.attachment_editor.setReadOnly(True if running else False)
        if running:
            self._running_step_id = self._running_step_id or self.current_step_id
            self._running_step_title = step_title or self.current_step_id
            self._running_dots = 0
            self.run_state_card.show()
            self.run_progress_bar.setRange(0, 0)
            self._advance_running_indicator()
            self._run_timer.start()
        else:
            self._run_timer.stop()
            self.run_state_card.hide()
            self._running_step_id = None
        self._update_interaction_state()

    def _advance_running_indicator(self) -> None:
        self._running_dots = (self._running_dots + 1) % 4
        dots = "." * self._running_dots or "."
        self.run_status_label.setText(
            f"Running {self._running_step_title}{dots}"
        )

    def _on_step_run_success(self, result) -> None:
        executed_step_id = self._running_step_id or self.current_step_id
        self._set_running_state(False)
        message = f"{executed_step_id} -> {result.status}"
        self.statusBar().showMessage(message, 5000)
        if executed_step_id == INPUT_STEP_ID and result.status == "success":
            self._sync_workspace_folder_backend(update_recent=True)
            self.current_step_id = self._default_focus_step_id()
        self._refresh_all()
        if (
            executed_step_id == "check_solid"
            and self.session is not None
            and self.session.issues
        ):
            target_step_id = self.session.issues[0].target_step_id
            if target_step_id in self.session.steps:
                self.current_step_id = target_step_id
                self._refresh_all()
                target_title = self.engine.get_step_definition(
                    self.session,
                    target_step_id,
                ).title
                self.statusBar().showMessage(
                    f"check_solid -> routed to {target_title}",
                    5000,
                )
        if executed_step_id in {"parameters", "materials", "solids"}:
            self.tabs.setCurrentWidget(self.structure_tab)

    def _on_step_run_failure(self, error: str) -> None:
        self._set_running_state(False)
        self._refresh_all()
        QMessageBox.critical(self, "Step Failed", error)

    def _sync_workspace_folder_backend(self, *, update_recent: bool = False) -> None:
        if self.session is None:
            return
        input_state = self._input_state()
        backend = (
            str(input_state.settings.get("backend") or "").strip().lower()
            if input_state is not None
            else ""
        )
        previous_workspace = self.session.workspace_dir
        updated_workspace = self.session_store.ensure_workspace_backend_name(
            self.session,
            backend,
        )
        if updated_workspace and updated_workspace != previous_workspace:
            if update_recent:
                self.recent_store.add(updated_workspace)
                self._rebuild_recent_menu()
            self.statusBar().showMessage(
                f"Workspace renamed to {Path(updated_workspace).name}",
                5000,
            )

    def _cleanup_run_worker(self) -> None:
        if self._run_worker is not None:
            self._run_worker.deleteLater()
            self._run_worker = None
        if self._run_thread is not None:
            self._run_thread.deleteLater()
            self._run_thread = None
        self._update_interaction_state()

    def _refresh_resources_tab(self) -> None:
        definition = self.engine.get_step_definition(self.session, self.current_step_id)
        state = self.session.steps[self.current_step_id]
        previous_attachment_id = self._current_attachment_id
        previous_prompt_artifact_id = (
            self.artifact_selection_list.currentItem().data(Qt.UserRole)
            if self.artifact_selection_list.currentItem() is not None
            else None
        )

        self.attachments_list.clear()
        for attachment in state.attachments:
            attachment_label = (
                f"{attachment.name} (description)"
                if attachment.origin == "description"
                else f"{attachment.name} ({attachment.kind})"
            )
            item = QListWidgetItem(
                attachment_label,
                self.attachments_list,
            )
            item.setData(Qt.UserRole, attachment.id)
            if attachment.origin == "description":
                item.setForeground(QColor(PALETTE["text_muted"]))
            else:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if attachment.enabled else Qt.Unchecked)
            if attachment.id == previous_attachment_id:
                self.attachments_list.setCurrentItem(item)

        self.artifact_selection_list.clear()
        self.engine.ensure_default_artifact_selection(self.session, definition)
        available_artifacts = self.engine.get_available_artifacts(
            self.session,
            self.current_step_id,
        )
        self.artifacts_group.setVisible(True)
        self.artifact_selection_help.setText(
            ""
            if available_artifacts
            else "This step does not have any upstream artifacts to select yet."
        )
        for artifact in available_artifacts:
            item = QListWidgetItem(
                f"{artifact.label}: {Path(artifact.path).name}",
                self.artifact_selection_list,
            )
            item.setData(Qt.UserRole, artifact.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked
                if artifact.id in state.selected_artifact_ids
                else Qt.Unchecked
            )
            if artifact.id == previous_prompt_artifact_id:
                self.artifact_selection_list.setCurrentItem(item)

        if (
            self.artifact_selection_list.count() > 0
            and self.artifact_selection_list.currentItem() is None
        ):
            self.artifact_selection_list.setCurrentRow(0)
        if self.artifact_selection_list.currentItem() is None:
            self.artifact_selection_preview.setPlainText(
                "Select an upstream artifact to preview the exact content that can be forwarded to the LLM."
            )

        if (
            self.attachments_list.currentItem() is None
            or self._find_attachment(previous_attachment_id) is None
        ):
            self._current_attachment_id = None
            self._show_attachment_empty_preview(
                "Select an attachment to inspect it here."
            )
        self._update_interaction_state()

    def _refresh_structure_tab(self) -> None:
        if self.session is None:
            self._show_structure_empty(
                "Structured results will appear here for parameters, materials, and solids."
            )
            return

        try:
            preview = self._current_step_structure_preview()
        except Exception as exc:
            self._show_structure_empty(f"Unable to render structured preview.\n{exc}")
            return

        if preview is None:
            self._show_structure_empty(
                "This step does not have a structured model view yet. Use Artifacts or Logs for the raw files."
            )
            return

        if preview.kind == "parameters":
            self.parameters_summary_label.setText(
                f"{preview.summary}\nSource: {Path(preview.source_path).name}"
            )
            self._populate_structure_table(self.parameters_table, preview.rows)
            self.structure_stack.setCurrentIndex(1)
            return

        if preview.kind == "materials":
            self.materials_summary_label.setText(
                f"{preview.summary}\nSource: {Path(preview.source_path).name}"
            )
            self._populate_structure_table(self.materials_table, preview.rows)
            self.structure_stack.setCurrentIndex(2)
            return

        if preview.kind == "solids":
            summary_lines = [
                preview.summary,
                f"Source: {Path(preview.source_path).name}",
            ]
            if (
                self.session.steps.get(INPUT_STEP_ID, None) is not None
                and bool(self.session.steps[INPUT_STEP_ID].settings.get("enable_25d", False))
                and not bool(self.session.flags.get("has_25d"))
            ):
                summary_lines.append(
                    "Warning: 2.5D is enabled, but the latest solids result does not contain any 2.5D items."
                )
            self.solids_summary_label.setText("\n".join(summary_lines))
            self.solids_list.clear()
            self.solids_detail.setPlainText("")
            for solid in preview.solids:
                item = QListWidgetItem(
                    f"{solid.name}\n{solid.solid_type} | {solid.role} | {solid.material}",
                    self.solids_list,
                )
                item.setData(Qt.UserRole, solid)
            if self.solids_list.count() > 0:
                self.solids_list.setCurrentRow(0)
            else:
                self.solids_detail.setPlainText("No solids found in the current preview.")
            self.structure_stack.setCurrentIndex(3)
            return

        self._show_structure_empty(
            "This step does not have a structured model view yet. Use Artifacts or Logs for the raw files."
        )

    def _show_structure_empty(self, message: str) -> None:
        self.parameters_table.setRowCount(0)
        self.materials_table.setRowCount(0)
        self.solids_list.clear()
        self.solids_detail.setPlainText("")
        self.structure_empty_label.setText(message)
        self.structure_stack.setCurrentIndex(0)

    def _populate_structure_table(
        self,
        table: QTableWidget,
        rows: list[list[str]],
    ) -> None:
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                item = QTableWidgetItem(value)
                table.setItem(row_index, column_index, item)
        table.resizeColumnsToContents()

    def _current_step_structure_preview(self) -> Optional[StructurePreview]:
        if self.session is None:
            return None
        state = self.session.steps.get(self.current_step_id)
        if state is None:
            return None
        artifact_lookup = {
            "parameters": "parameters_json",
            "materials": "materials_json",
            "solids": "solids_json",
        }
        target_label = artifact_lookup.get(self.current_step_id)
        if not target_label:
            return None
        artifact = next(
            (
                self.session.artifacts[artifact_id]
                for artifact_id in state.artifact_ids
                if artifact_id in self.session.artifacts
                and self.session.artifacts[artifact_id].label == target_label
            ),
            None,
        )
        if artifact is None or not Path(artifact.path).exists():
            return None
        if self.current_step_id == "parameters":
            return load_parameters_preview(artifact.path)
        if self.current_step_id == "materials":
            return load_materials_preview(artifact.path)
        if self.current_step_id == "solids":
            return load_solids_preview(artifact.path)
        return None

    def _refresh_artifacts_tab(self) -> None:
        state = self.session.steps[self.current_step_id]
        self.artifacts_list.clear()
        self.artifact_preview.setPlainText("")
        for artifact_id in state.artifact_ids:
            artifact = self.session.artifacts.get(artifact_id)
            if not artifact:
                continue
            item = QListWidgetItem(
                f"{artifact.label}: {Path(artifact.path).name}",
                self.artifacts_list,
            )
            item.setData(Qt.UserRole, artifact.id)

    def _on_solid_selected(self, current, previous) -> None:
        if current is None:
            self.solids_detail.setPlainText("")
            return
        solid = current.data(Qt.UserRole)
        if not isinstance(solid, SolidPreviewItem):
            self.solids_detail.setPlainText("")
            return
        self.solids_detail.setPlainText(self._format_solid_detail(solid))

    def _format_solid_detail(self, solid: SolidPreviewItem) -> str:
        lines = [
            f"Name: {solid.name}",
            f"Type: {solid.solid_type or '-'}",
            f"Role: {solid.role or '-'}",
            f"Material: {solid.material or '-'}",
            "",
            "Dimensions:",
            solid.dimensions_text or "-",
            "",
            "Operations:",
            solid.operations_text or "-",
        ]
        if solid.notes:
            lines.extend(["", "Notes:", solid.notes])
        return "\n".join(lines).strip()

    def _refresh_issues_tab(self) -> None:
        state = self.session.steps[self.current_step_id]
        self.issues_list.clear()
        self.issue_detail.setPlainText("")

        if self.current_step_id == "check_solid":
            for issue in state.raw_issues:
                message = str(issue.get("issue") or "Issue")
                route_to = str(issue.get("route_to") or "").strip()
                if route_to:
                    message = f"[{route_to}] {message}"
                item = QListWidgetItem(message, self.issues_list)
                item.setData(Qt.UserRole, issue)
        else:
            for issue in state.issues:
                item = QListWidgetItem(issue.message, self.issues_list)
                item.setData(Qt.UserRole, issue)

    def _refresh_logs_tab(self) -> None:
        state = self.session.steps[self.current_step_id]
        self.logs_view.setPlainText("\n".join(state.logs))

    def _update_status_bar(self) -> None:
        if self.session is None:
            env = self._environment_report()
            if self._all_backends_unavailable(env):
                self.statusBar().showMessage(self._all_backends_unavailable_message(env))
                return
            self.statusBar().showMessage(
                "Launchpad ready. Open or create a LEAM workspace to continue."
            )
            return
        env = self._environment_report()
        cst_state = "ready" if env.get("cst_available") else "missing"
        hfss_state = "ready" if env.get("hfss_available") else "missing"
        self.statusBar().showMessage(
            f"Workspace={self.session.title or Path(self.session.workspace_dir).name} | "
            f"Workflow={self.session.status} | Template={self.session.template} | "
            f"CST={cst_state} | HFSS={hfss_state}"
        )

    def _show_attachment_empty_preview(self, message: str) -> None:
        self.attachment_empty_label.setText(message)
        self.attachment_metadata_view.setPlainText("")
        self.attachment_preview_stack.setCurrentIndex(0)

    def _show_attachment_text_preview(
        self,
        attachment: AttachmentRef,
        content: str,
        editable: bool,
    ) -> None:
        self.attachment_editor.setPlainText(content)
        self.attachment_editor.setReadOnly(not editable)
        self.attachment_metadata_view.setPlainText(
            self._format_attachment_metadata(attachment)
        )
        self.attachment_preview_tabs.setCurrentIndex(0)
        self.attachment_preview_stack.setCurrentIndex(1)

    def _show_attachment_image_preview(self, attachment: AttachmentRef) -> None:
        self.attachment_image_caption.setText(str(Path(attachment.path)))
        pixmap = QPixmap(attachment.path)
        if pixmap.isNull():
            self.attachment_image_label.setPixmap(QPixmap())
            self.attachment_image_label.setText(
                f"Unable to load image preview.\n{attachment.path}"
            )
        else:
            self.attachment_image_label.setText("")
            self.attachment_image_label.setPixmap(pixmap)
        self.attachment_metadata_view.setPlainText(
            self._format_attachment_metadata(attachment)
        )
        self.attachment_preview_tabs.setCurrentIndex(1)
        self.attachment_preview_stack.setCurrentIndex(1)

    def _show_attachment_metadata_preview(
        self,
        attachment: AttachmentRef,
        intro_message: Optional[str] = None,
    ) -> None:
        lines = []
        if intro_message:
            lines.append(intro_message)
            lines.append("")
        lines.append(self._format_attachment_metadata(attachment))
        self.attachment_metadata_view.setPlainText("\n".join(lines).strip())
        self.attachment_preview_tabs.setCurrentIndex(2)
        self.attachment_preview_stack.setCurrentIndex(1)

    def _format_attachment_metadata(self, attachment: AttachmentRef) -> str:
        path = Path(attachment.path)
        lines = [
            f"Name: {attachment.name}",
            f"Kind: {attachment.kind}",
            f"Origin: {attachment.origin}",
            f"Enabled for run: {'yes' if attachment.enabled else 'no'}",
            f"Editable: {'yes' if attachment.editable else 'no'}",
            f"Path: {attachment.path}",
        ]
        if path.exists():
            lines.append(f"Size bytes: {path.stat().st_size}")
        else:
            lines.append("Size bytes: missing")
        return "\n".join(lines)

    def _format_step_status(self, status: str) -> str:
        return status.replace("_", " ").title()

    def _update_interaction_state(self) -> None:
        has_session = self.session is not None
        is_running = self._step_switch_locked()
        config_locked = self._is_workflow_config_locked() if has_session else False
        available_backends = self._available_backends() if has_session else []
        current_backend = (
            str(self._input_state().settings.get("backend", "cst")).strip().lower()
            if has_session and self._input_state() is not None
            else "cst"
        )
        self.step_list.setEnabled(has_session and not is_running)
        self.tabs.setEnabled(has_session and not is_running)
        for widget in self._step_item_widgets.values():
            widget.set_interaction_enabled(has_session and not is_running)

        if not has_session:
            self.action_step_label.setText("Workspace Required")
            self.action_state_badge.setText("OFFLINE")
            set_tone(self.action_state_badge, "muted")
            self.action_detail_label.setText(
                "Use the launchpad to create a workspace or open an existing LEAM workspace."
            )
            self.run_button.setText("Create Workspace First")
            self.run_button.setEnabled(False)
            self.workflow_config_group.setEnabled(False)
            self.workflow_apply_button.setText("Apply Workspace Setup")
            self.workflow_apply_button.setEnabled(False)
            self.workflow_template_combo.setEnabled(False)
            self.enable_25d_checkbox.setEnabled(False)
            self.backend_combo.setEnabled(False)
            self.enable_execution_checkbox.setEnabled(False)
            self.enable_update_checkbox.setEnabled(False)
            self.description_edit.setReadOnly(True)
            self.attachment_editor.setReadOnly(True)
            self.attachment_preview_tabs.setEnabled(False)
            self.add_text_button.setEnabled(False)
            self.add_files_button.setEnabled(False)
            self.add_images_button.setEnabled(False)
            self.remove_attachment_button.setEnabled(False)
            self.move_up_attachment_button.setEnabled(False)
            self.move_down_attachment_button.setEnabled(False)
            self.save_attachment_button.setEnabled(False)
            self.artifact_selection_list.setEnabled(False)
            return

        blocker = self.engine.get_step_blocker(self.session, self.current_step_id)
        definition = self.engine.get_step_definition(self.session, self.current_step_id)
        self.action_step_label.setText(definition.title)
        self.run_button.setText("Run This Step")
        self.run_button.setEnabled(not is_running and blocker is None)
        self.workflow_config_group.setEnabled(has_session)
        self.workflow_apply_button.setText(
            "Applying Workspace Setup..."
            if is_running and self._running_step_id == INPUT_STEP_ID
            else "Apply Workspace Setup"
        )
        self.workflow_apply_button.setEnabled(
            has_session and not is_running and not config_locked
        )
        self.workflow_template_combo.setEnabled(not is_running and not config_locked)
        self.enable_25d_checkbox.setEnabled(not is_running and not config_locked)
        self.backend_combo.setEnabled(
            not is_running
            and not config_locked
            and bool(available_backends)
            and (
                len(available_backends) > 1
                or current_backend not in available_backends
            )
        )
        self.enable_execution_checkbox.setEnabled(not is_running and not config_locked)
        self.enable_update_checkbox.setEnabled(not is_running and not config_locked)
        self.description_edit.setReadOnly(is_running)

        attachment = self._find_attachment(self._current_attachment_id)
        attachment_index = self._current_user_attachment_position(
            self._current_attachment_id
        )
        attachment_count = self._user_attachment_count()
        self.attachment_preview_tabs.setEnabled(attachment is not None)
        self.add_text_button.setEnabled(not is_running)
        self.add_files_button.setEnabled(not is_running)
        self.add_images_button.setEnabled(not is_running)
        self.remove_attachment_button.setEnabled(
            not is_running
            and attachment is not None
            and attachment.origin == "user"
        )
        self.move_up_attachment_button.setEnabled(
            not is_running
            and attachment is not None
            and attachment.origin == "user"
            and attachment_index is not None
            and attachment_index > 0
        )
        self.move_down_attachment_button.setEnabled(
            not is_running
            and attachment is not None
            and attachment.origin == "user"
            and attachment_index is not None
            and attachment_index < attachment_count - 1
        )
        self.save_attachment_button.setEnabled(
            not is_running and attachment is not None and attachment.editable
        )
        self.attachment_editor.setReadOnly(
            True if is_running or attachment is None or not attachment.editable else False
        )
        self.artifact_selection_list.setEnabled(
            not is_running and self.artifact_selection_list.count() > 0
        )

        if is_running:
            self.action_state_badge.setText("RUNNING")
            set_tone(self.action_state_badge, "info")
            self.action_detail_label.setText(
                f"{self._running_step_title or definition.title} is currently executing."
            )
            self.step_gate_label.setText(
                f"Next action: wait for {self._running_step_title or definition.title} to finish."
            )
            set_tone(self.step_gate_label, "info")
        elif blocker:
            self.action_state_badge.setText("BLOCKED")
            set_tone(self.action_state_badge, "warning")
            self.action_detail_label.setText(blocker)
            self.step_gate_label.setText(f"Next action: {blocker}")
            set_tone(self.step_gate_label, "warning")
        else:
            self.action_state_badge.setText("READY")
            set_tone(self.action_state_badge, "success")
            self.action_detail_label.setText(
                "Upstream outputs are ready. You can run this step now."
            )
            self.step_gate_label.setText(
                "Next action: upstream outputs are ready. You can run this step now."
            )
            set_tone(self.step_gate_label, "success")

        self._sync_current_step_action_controls()

    def _add_text_attachment(self) -> None:
        if self.session is None:
            return
        name, ok = QInputDialog.getText(
            self,
            "New Text Attachment",
            "Attachment name:",
        )
        if not ok or not name.strip():
            return
        attachment = self.session_store.add_text_attachment(
            self.session,
            self.current_step_id,
            name.strip(),
        )
        self.session.steps[self.current_step_id].attachments.append(attachment)
        self._refresh_resources_tab()
        self._autosave_session_snapshot()

    def _add_file_attachments(self) -> None:
        if self.session is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add File Attachments",
            str(Path.cwd()),
            ATTACHMENT_FILE_FILTER,
        )
        if not paths:
            return
        state = self.session.steps[self.current_step_id]
        for path in paths:
            attachment = self.session_store.import_attachment(
                self.session,
                self.current_step_id,
                path,
            )
            state.attachments.append(attachment)
        self._refresh_resources_tab()
        self._autosave_session_snapshot()

    def _add_image_attachments(self) -> None:
        if self.session is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Image Attachments",
            str(Path.cwd()),
            ATTACHMENT_IMAGE_FILTER,
        )
        if not paths:
            return
        supported_paths = []
        unsupported_paths = []
        for path in paths:
            if Path(path).suffix.lower() in MODEL_IMAGE_EXTENSIONS:
                supported_paths.append(path)
            else:
                unsupported_paths.append(path)
        if unsupported_paths:
            QMessageBox.warning(
                self,
                "Unsupported Images",
                "LEAM currently forwards only PNG and JPEG images to the model.\n\n"
                "Unsupported image file(s):\n"
                + "\n".join(Path(path).name for path in unsupported_paths),
            )
        if not supported_paths:
            return
        state = self.session.steps[self.current_step_id]
        for path in supported_paths:
            attachment = self.session_store.import_attachment(
                self.session,
                self.current_step_id,
                path,
            )
            state.attachments.append(attachment)
        self._refresh_resources_tab()
        self._autosave_session_snapshot()

    def _remove_attachment(self) -> None:
        if self.session is None:
            return
        item = self.attachments_list.currentItem()
        if item is None:
            return
        attachment_id = item.data(Qt.UserRole)
        attachment = self._find_attachment(attachment_id)
        if attachment is None or attachment.origin != "user":
            return
        state = self.session.steps[self.current_step_id]
        state.attachments = [
            attachment
            for attachment in state.attachments
            if attachment.id != attachment_id
        ]
        self._refresh_resources_tab()
        self._autosave_session_snapshot()

    def _move_attachment(self, delta: int) -> None:
        if self.session is None:
            return
        item = self.attachments_list.currentItem()
        if item is None:
            return
        attachment_id = item.data(Qt.UserRole)
        state = self.session.steps[self.current_step_id]
        selected_attachment = self._find_attachment(attachment_id)
        if selected_attachment is None or selected_attachment.origin != "user":
            return
        user_indices = [
            position
            for position, attachment in enumerate(state.attachments)
            if attachment.origin == "user"
        ]
        index = next(
            (
                position
                for position, candidate_index in enumerate(user_indices)
                if state.attachments[candidate_index].id == attachment_id
            ),
            None,
        )
        if index is None:
            return
        target_position = index + delta
        if target_position < 0 or target_position >= len(user_indices):
            return
        source_index = user_indices[index]
        target_index = user_indices[target_position]
        attachment = state.attachments.pop(source_index)
        if source_index < target_index:
            target_index -= 1
        state.attachments.insert(target_index, attachment)
        self._refresh_resources_tab()
        self._autosave_session_snapshot()

    def _on_attachment_selected(self, current, previous) -> None:
        if self._ui_updating:
            return
        if current is None:
            self._current_attachment_id = None
            self._show_attachment_empty_preview(
                "Select an attachment to inspect it here."
            )
            self._update_interaction_state()
            return
        attachment_id = current.data(Qt.UserRole)
        attachment = self._find_attachment(attachment_id)
        if not attachment:
            return
        self._current_attachment_id = attachment.id
        if attachment.editable:
            self._show_attachment_text_preview(
                attachment,
                self.session_store.read_attachment_text(attachment),
                True,
            )
        elif attachment.kind == "text":
            self._show_attachment_text_preview(
                attachment,
                self.session_store.read_attachment_text(attachment),
                False,
            )
        elif attachment.kind == "image":
            self._show_attachment_image_preview(attachment)
        elif attachment.kind == "pdf":
            self._show_attachment_metadata_preview(
                attachment,
                "PDF attachments are forwarded as document inputs. Inline preview is not available yet.",
            )
        else:
            self._show_attachment_metadata_preview(
                attachment,
                "This attachment stays in the workspace. Readable text-like files are forwarded to the LLM; opaque binary files remain local-only.",
            )
        self._update_interaction_state()

    def _on_attachment_toggled(self, item: QListWidgetItem) -> None:
        if self._ui_updating:
            return
        attachment = self._find_attachment(item.data(Qt.UserRole))
        if not attachment or attachment.origin != "user":
            return
        attachment.enabled = item.checkState() == Qt.Checked
        self._autosave_session_snapshot()
        self._update_interaction_state()

    def _save_attachment_text(self) -> None:
        attachment = self._find_attachment(self._current_attachment_id)
        if not attachment or not attachment.editable:
            return
        content = self.attachment_editor.toPlainText()
        if attachment.origin == "description" and self.session is not None:
            state = self.session.steps.get(self.current_step_id)
            if state is not None:
                state.description = content
                self._ui_updating = True
                self.description_edit.setPlainText(content)
                self._ui_updating = False
                self.session_store.sync_description_attachment(
                    self.session,
                    self.current_step_id,
                    content,
                )
                self.engine.refresh_session(self.session)
        self.session_store.write_attachment_text(
            attachment,
            content,
        )
        self._autosave_session_snapshot()
        self.statusBar().showMessage(
            f"Saved attachment {attachment.name}",
            3000,
        )
        self._update_interaction_state()

    def _on_artifact_selection_changed(self, item: QListWidgetItem) -> None:
        if self._ui_updating:
            return
        state = self.session.steps[self.current_step_id]
        selected_ids = []
        for index in range(self.artifact_selection_list.count()):
            candidate = self.artifact_selection_list.item(index)
            if candidate.checkState() == Qt.Checked:
                selected_ids.append(candidate.data(Qt.UserRole))
        state.selected_artifact_ids = selected_ids
        state.settings["artifact_selection_touched"] = True
        self._autosave_session_snapshot()

    def _on_artifact_selected(self, current, previous) -> None:
        if current is None:
            self.artifact_preview.setPlainText("")
            return
        artifact_id = current.data(Qt.UserRole)
        artifact = self.session.artifacts.get(artifact_id)
        if not artifact:
            return
        preview = self.engine.runner._read_preview(artifact.path)
        self.artifact_preview.setPlainText(preview)

    def _on_selected_prompt_artifact_changed(self, current, previous) -> None:
        if current is None or self.session is None:
            self.artifact_selection_preview.setPlainText(
                "Select an upstream artifact to preview the exact content that can be forwarded to the LLM."
            )
            return
        artifact_id = current.data(Qt.UserRole)
        artifact = self.session.artifacts.get(artifact_id)
        if artifact is None:
            self.artifact_selection_preview.setPlainText("")
            return
        preview = self.engine.runner._read_preview(artifact.path)
        self.artifact_selection_preview.setPlainText(preview)

    def _on_issue_selected(self, current, previous) -> None:
        if current is None:
            self.issue_detail.setPlainText("")
            return
        payload = current.data(Qt.UserRole)
        if isinstance(payload, IssueRefill):
            lines = [
                f"Category: {payload.category}",
                f"Severity: {payload.severity}",
                f"Path: {payload.issue_path or '-'}",
                f"Solid: {payload.solid or '-'}",
                "",
                payload.message,
                "",
                payload.inserted_text,
            ]
            self.issue_detail.setPlainText("\n".join(lines).strip())
        elif isinstance(payload, dict):
            lines = []
            for key in [
                "category",
                "severity",
                "route_to",
                "solid",
                "path",
                "issue",
            ]:
                if key in payload:
                    lines.append(f"{key}: {payload[key]}")
            self.issue_detail.setPlainText("\n".join(lines))

    def _find_attachment(self, attachment_id: Optional[str]) -> Optional[AttachmentRef]:
        if not attachment_id:
            return None
        if self.session is None:
            return None
        state = self.session.steps.get(self.current_step_id)
        if not state:
            return None
        for attachment in state.attachments:
            if attachment.id == attachment_id:
                return attachment
        return None

    def _current_attachment_index(self, attachment_id: Optional[str]) -> Optional[int]:
        if not attachment_id or self.session is None:
            return None
        state = self.session.steps.get(self.current_step_id)
        if not state:
            return None
        for index, attachment in enumerate(state.attachments):
            if attachment.id == attachment_id:
                return index
        return None

    def _current_user_attachment_position(
        self,
        attachment_id: Optional[str],
    ) -> Optional[int]:
        if not attachment_id or self.session is None:
            return None
        state = self.session.steps.get(self.current_step_id)
        if not state:
            return None
        user_position = 0
        for attachment in state.attachments:
            if attachment.origin != "user":
                continue
            if attachment.id == attachment_id:
                return user_position
            user_position += 1
        return None

    def _user_attachment_count(self) -> int:
        if self.session is None:
            return 0
        state = self.session.steps.get(self.current_step_id)
        if not state:
            return 0
        return sum(1 for attachment in state.attachments if attachment.origin == "user")
