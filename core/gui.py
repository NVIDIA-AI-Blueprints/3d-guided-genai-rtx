# core/gui.py
import sys
import os
import json
from pathlib import Path

try:
    from qtpy.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
        QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
        QCheckBox, QSpinBox, QFormLayout, QDialog, QTextEdit, QComboBox,
        QSpacerItem, QSizePolicy
    )
    from qtpy.QtCore import Qt
    from qtpy.QtGui import QFont, QIcon
    QT_AVAILABLE = True
except Exception:  # pragma: no cover
    QT_AVAILABLE = False


def _add_with_margin(parent_layout: QVBoxLayout, child_item) -> None:
    """Add widget OR layout with consistent left margin for alignment."""
    margin = QWidget()
    margin.setFixedWidth(12)
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    
    if isinstance(child_item, QWidget):
        row.addWidget(margin)
        row.addWidget(child_item, stretch=1)
        parent_layout.addLayout(row)
    elif hasattr(child_item, 'addWidget'):
        row.addWidget(margin)
        row.addLayout(child_item, stretch=1)
        parent_layout.addLayout(row)
    else:
        raise TypeError(f"Unsupported child_item type: {type(child_item)}")


def run_gui(comfy_path: Path | None = None,
            workflow_path: Path | None = None,
            extract_minimal: bool = False,
            port: int = 8000,
            generations: int = 10,
            num_instances: int = 1,
            run_default: bool = False,
            extra_args: list | None = None,
            debug_warmup: bool = False,
            no_cleanup: bool = False,
            use_main_workflow_only: bool = False,
            override: str | None = None,
            force_extract: bool = False,
            timeout: int = 4000) -> dict:
    if not QT_AVAILABLE:
        print("Qt bindings not found — falling back to CLI mode.")
        sys.exit(0)

    app = QApplication(sys.argv)

# ------------------------------------------------------------------
    # SET WINDOW ICON
    # ------------------------------------------------------------------
    # Looks for icon.png or icon.ico in the same directory as this script (core/)
    script_dir = Path(__file__).parent
    icon_path = script_dir / "icon.png"
    if not icon_path.exists():
        icon_path = script_dir / "icon.ico"
        
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    win = QWidget()
    win.setWindowTitle("ComfyUI Benchmark — Select Options")
    # Increased height slightly to accommodate the extra group header
    win.setMinimumSize(680, 480)
    win.resize(680, 480)

    # Main Window Layout
    main_layout = QVBoxLayout()
    main_layout.setContentsMargins(10, 10, 10, 10)
    main_layout.setSpacing(12)
    win.setLayout(main_layout)

    # ==================================================================
    # LOAD WORKFLOW DATA
    # ==================================================================
    base_dir = Path(__file__).resolve().parent.parent
    workflows_dir = base_dir / "workflows"
    json_path = workflows_dir / "workflows.json"
    
    workflow_data = []
    if json_path.exists():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)
        except Exception as e:
            print(f"[GUI] Error loading workflows.json: {e}")

    # ==================================================================
    # SECTION 1: COMFYUI ENVIRONMENT
    # ==================================================================
    env_group = QGroupBox("ComfyUI Environment")
    env_layout = QVBoxLayout()
    env_group.setLayout(env_layout)
    
    # ComfyUI Folder
    comfy_row = QHBoxLayout()
    comfy_row.addWidget(QLabel("ComfyUI folder (-c):"))
    comfy_edit = QLineEdit(str(comfy_path) if comfy_path else "")
    comfy_row.addWidget(comfy_edit, 1)

    def browse_comfy():
        start_dir = comfy_edit.text().strip() or os.getcwd()
        folder = QFileDialog.getExistingDirectory(win, "Select ComfyUI folder", start_dir)
        if folder:
            comfy_edit.setText(folder)

    comfy_btn = QPushButton("Browse...")
    comfy_btn.setFixedWidth(90)
    comfy_btn.clicked.connect(browse_comfy)
    comfy_row.addWidget(comfy_btn)

    _add_with_margin(env_layout, comfy_row)
    main_layout.addWidget(env_group)

    # ==================================================================
    # SECTION 2: WORKFLOW DETAILS
    # ==================================================================
    wf_group = QGroupBox("Workflow Details")
    wf_layout = QVBoxLayout()
    wf_group.setLayout(wf_layout)

    # 1. NVIDIA Filter
    nvidia_row = QHBoxLayout()
    nvidia_check = QCheckBox("Show only workflows recommended for NVIDIA GPUs")
    nvidia_check.setToolTip("Filter list to show only workflows optimized for NVIDIA GPUs")
    nvidia_check.setChecked(False) 
    nvidia_row.addWidget(nvidia_check)
    _add_with_margin(wf_layout, nvidia_row)

    # 2. Workflow Selection
    workflow_row = QHBoxLayout()
    workflow_row.addWidget(QLabel("Workflow (-w):"))
    
    workflow_combo = QComboBox()
    workflow_combo.setEditable(False)
    
    # Checkbox for JSON folders (Defined here so we can reference it below)
    use_folder_check = QCheckBox("Use Folder (for .json)")
    use_folder_check.setChecked(False)
    use_folder_check.setEnabled(False) # Default to Disabled
    
    def update_folder_check_state():
        """Enable checkbox only if the selected file is a .json"""
        data = workflow_combo.currentData()
        if data and data != "CUSTOM" and str(data).lower().endswith(".json"):
            use_folder_check.setEnabled(True)
        else:
            use_folder_check.setChecked(False)
            use_folder_check.setEnabled(False)

    def populate_workflows():
        current_text = workflow_combo.currentText()
        workflow_combo.blockSignals(True)
        workflow_combo.clear()
        
        filter_nvidia = nvidia_check.isChecked()
        
        for item in workflow_data:
            name = item.get("name", "Unknown")
            filename = item.get("file", "")
            is_nvidia = item.get("nvidia_recommended", False)
            
            if os.path.isabs(filename):
                full_path = str(Path(filename))
            else:
                full_path = str(workflows_dir / filename)

            if filter_nvidia and not is_nvidia:
                continue
                
            workflow_combo.addItem(name, userData=full_path)
        
        # Add CLI argument if present
        if workflow_path:
            wf_str = str(workflow_path)
            found_index = workflow_combo.findData(wf_str)
            if found_index == -1:
                workflow_combo.insertItem(0, f"CLI: {Path(wf_str).name}", userData=wf_str)
                workflow_combo.setCurrentIndex(0)
            else:
                workflow_combo.setCurrentIndex(found_index)
        
        workflow_combo.addItem("Custom Workflow...", userData="CUSTOM")
        
        # Restore selection if valid
        if not workflow_path:
            found = workflow_combo.findText(current_text)
            if found != -1:
                workflow_combo.setCurrentIndex(found)
        
        # Update checkbox state based on current selection
        update_folder_check_state()
        workflow_combo.blockSignals(False)

    nvidia_check.toggled.connect(populate_workflows)
    populate_workflows()
    
    workflow_row.addWidget(workflow_combo, 1)
    
    # Use Folder Checkbox
    workflow_row.addWidget(use_folder_check)

    # Custom Workflow Logic
    previous_workflow_index = workflow_combo.currentIndex()
    if previous_workflow_index == -1 and workflow_combo.count() > 0:
        previous_workflow_index = 0
    
    def on_workflow_changed(index):
        nonlocal previous_workflow_index
        data = workflow_combo.itemData(index)
        
        if data == "CUSTOM":
            # Explicit request: Default to "Workflows" folder if it exists
            start_dir = str(workflows_dir) if workflows_dir.exists() else os.getcwd()
            prev_data = workflow_combo.itemData(previous_workflow_index)
            if prev_data and prev_data != "CUSTOM" and os.path.exists(prev_data):
                 start_dir = os.path.dirname(prev_data)

            file, _ = QFileDialog.getOpenFileName(
                win, "Select workflow ZIP or .json", start_dir,
                "Workflow files (*.zip *.json);;All files (*)"
            )
            
            if file:
                existing_index = workflow_combo.findData(file)
                if existing_index != -1:
                    workflow_combo.setCurrentIndex(existing_index)
                else:
                    insert_idx = workflow_combo.count() - 1
                    display_name = Path(file).name
                    workflow_combo.insertItem(insert_idx, display_name, userData=file)
                    workflow_combo.setCurrentIndex(insert_idx)
                previous_workflow_index = workflow_combo.currentIndex()
            else:
                workflow_combo.setCurrentIndex(previous_workflow_index)
        else:
            previous_workflow_index = index
        
        # Update the checkbox enabled/disabled state
        update_folder_check_state()

    workflow_combo.activated.connect(on_workflow_changed)
    _add_with_margin(wf_layout, workflow_row)
    
    main_layout.addWidget(wf_group)

    # ==================================================================
    # SECTION 3: RUN CONFIGURATION
    # ==================================================================
    run_group = QGroupBox("Run Configuration")
    run_layout = QVBoxLayout()
    run_group.setLayout(run_layout)

    # Port
    port_row = QHBoxLayout()
    port_row.addWidget(QLabel("Port (-p):"))
    port_spin = QSpinBox()
    port_spin.setToolTip("Port to use for the ComfyUI server")
    port_spin.setRange(1024, 65535)
    port_spin.setValue(port)
    port_row.addWidget(port_spin)
    port_row.addStretch()
    _add_with_margin(run_layout, port_row)

    # Generations
    gen_row = QHBoxLayout()
    gen_label = QLabel("Number of Generations (-g):")
    gen_label.setToolTip("Number of asset generations to run for each workflow")
    gen_row.addWidget(gen_label)
    generations_spin = QSpinBox()
    generations_spin.setRange(1, 1000)
    generations_spin.setValue(generations)
    generations_spin.setToolTip("Number of asset generations to run for each workflow")
    gen_row.addWidget(generations_spin)
    gen_row.addStretch()
    _add_with_margin(run_layout, gen_row)

    # Package Defaults
    default_check = QCheckBox("Use Package Defaults (-r)")
    default_check.setChecked(run_default)
    default_check.setToolTip("Use package defaults for number of generations and concurrent sessions")

    def toggle_gen_spin(checked: bool):
        generations_spin.setEnabled(not checked)

    default_check.toggled.connect(toggle_gen_spin)
    toggle_gen_spin(run_default)
    _add_with_margin(run_layout, default_check)

    main_layout.addWidget(run_group)

    # ==================================================================
    # SECTION 4: ADVANCED OPTIONS
    # ==================================================================
    advanced_group = QGroupBox("Advanced Options")
    advanced_group.setCheckable(True)
    advanced_group.setChecked(False)
    advanced_group.setFlat(True)

    advanced_container = QWidget()
    advanced_layout = QFormLayout()
    advanced_layout.setContentsMargins(0, 0, 0, 0)
    advanced_container.setLayout(advanced_layout)

    # Content
    instances_spin = QSpinBox()
    instances_spin.setRange(1, 100)
    instances_spin.setValue(num_instances)
    advanced_layout.addRow("Concurrent Sessions (-n):", instances_spin)

    timeout_spin = QSpinBox()
    timeout_spin.setRange(60, 36000)
    timeout_spin.setValue(timeout)
    timeout_spin.setSuffix(" seconds")
    advanced_layout.addRow("Timeout (--timeout):", timeout_spin)

    override_row = QHBoxLayout()
    override_edit = QLineEdit(override or "")
    override_edit.setPlaceholderText("Optional: path to override JSON file")
    override_row.addWidget(override_edit, 1)

    def browse_override():
        start_dir = override_edit.text().strip() or os.getcwd()
        file, _ = QFileDialog.getOpenFileName(
            win, "Select Override JSON File", start_dir,
            "JSON files (*.json);;All files (*)"
        )
        if file:
            override_edit.setText(file)

    override_btn = QPushButton("Browse...")
    override_btn.setFixedWidth(90)
    override_btn.clicked.connect(browse_override)
    override_row.addWidget(override_btn)
    advanced_layout.addRow("Override File (-o):", override_row)

    extra_args_edit = QLineEdit(" ".join(extra_args) if extra_args else "")
    extra_args_edit.setPlaceholderText("--lowvram --force-cpu etc.")
    advanced_layout.addRow("Extra Args:", extra_args_edit)

    minimal_check = QCheckBox("Minimal Extraction (Deprecated) (-e)")
    minimal_check.setChecked(extract_minimal)
    advanced_layout.addRow(minimal_check) 

    debug_check = QCheckBox("Debug Warmup (--debug-warmup)")
    debug_check.setChecked(debug_warmup)
    advanced_layout.addRow(debug_check)

    no_cleanup_check = QCheckBox("Skip Cleanup (--no-cleanup)")
    no_cleanup_check.setChecked(no_cleanup)
    advanced_layout.addRow(no_cleanup_check)

    main_workflow_check = QCheckBox("Use Main Workflow for Warmup (-u)")
    main_workflow_check.setChecked(use_main_workflow_only)
    advanced_layout.addRow(main_workflow_check)

    force_extract_check = QCheckBox("Force Extract All (--force-extract)")
    force_extract_check.setChecked(force_extract)
    advanced_layout.addRow(force_extract_check)

    # Layout plumbing for Advanced Group
    group_layout = QVBoxLayout()
    group_layout.addWidget(advanced_container)
    group_layout.setContentsMargins(20, 10, 20, 10)
    advanced_group.setLayout(group_layout)

    def toggle_advanced(checked):
        advanced_container.setVisible(checked)
        # Force layout update to handle resizing correctly
        QApplication.processEvents()
        win.adjustSize()
        if checked:
            max_h = win.screen().availableGeometry().height() - 100
            if win.height() > max_h:
                win.resize(680, max_h)

    advanced_group.toggled.connect(toggle_advanced)
    toggle_advanced(False)
    
    # Add Advanced Group to Main Layout
    main_layout.addWidget(advanced_group)

    # Spacer to push buttons to bottom
    main_layout.addStretch()

    # ==================================================================
    # BUTTONS
    # ==================================================================
    btn_row = QHBoxLayout()
    btn_row.addStretch()

    ok_btn = QPushButton("OK")
    ok_btn.setDefault(True)

    def on_ok():
        c = Path(comfy_edit.text().strip())
        w_data = workflow_combo.currentData()
        
        if w_data == "CUSTOM" or not w_data:
             QMessageBox.critical(win, "Error", "Please select a valid workflow.")
             return
             
        w = Path(w_data)
        override_path = override_edit.text().strip()

        if not c.exists() or not c.is_dir():
            QMessageBox.critical(win, "Error", "ComfyUI folder does not exist or is not a directory.")
            return
        if not w.exists():
            QMessageBox.critical(win, "Error", f"Workflow path does not exist:\n{w}")
            return
        if override_path and not Path(override_path).exists():
            QMessageBox.critical(win, "Error", "Override file does not exist.")
            return

        # Check checkbox state for .json folders
        if w.suffix.lower() == ".json" and use_folder_check.isChecked():
            w = w.parent
        if w.suffix.lower() != ".zip" and not (w / "workflow.json").exists():
            QMessageBox.critical(win, "Error", "Workflow folder must contain a file named 'workflow.json'.")
            return

        win.result = {
            'comfy_path': c,
            'workflow_path': w,
            'extract_minimal': minimal_check.isChecked(),
            'port': port_spin.value(),
            'generations': generations_spin.value(),
            'num_instances': instances_spin.value(),
            'run_default': default_check.isChecked(),
            'extra_args': extra_args_edit.text().strip().split(),
            'debug_warmup': debug_check.isChecked(),
            'no_cleanup': no_cleanup_check.isChecked(),
            'use_main_workflow_only': main_workflow_check.isChecked(),
            'force_extract': force_extract_check.isChecked(),
            'override': override_path or None,
            'timeout': timeout_spin.value()
        }
        win.close()

    ok_btn.clicked.connect(on_ok)
    btn_row.addWidget(ok_btn)

    # ------------------------------------------------------------------
    # VALIDATE INPUTS (Disable OK if ComfyUI path is empty)
    # ------------------------------------------------------------------
    def validate_inputs():
        """Enable OK button only if ComfyUI folder is provided."""
        path_text = comfy_edit.text().strip()
        ok_btn.setEnabled(bool(path_text))

    # Connect to changes and run once immediately
    comfy_edit.textChanged.connect(validate_inputs)
    validate_inputs()
    # ------------------------------------------------------------------

    cancel_btn = QPushButton("Cancel")
    cancel_btn.clicked.connect(win.close)
    btn_row.addWidget(cancel_btn)

    main_layout.addLayout(btn_row)

    win.result = None
    win.show()
    app.exec_()

    if win.result is None:
        print("GUI cancelled — exiting.")
        sys.exit(0)

    return win.result

def show_restart_required_dialog(package_manager, args, python_exe, script_fpath, log_file=None):
    if not getattr(package_manager, "custom_nodes_extracted", False):
        return

    dialog = QDialog()
    dialog.setWindowTitle("Restart Required")
    dialog.setModal(True)

    layout = QVBoxLayout()
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)
    dialog.setLayout(layout)

    header = QLabel(
        "<b>Custom Nodes were installed into an active ComfyUI session.</b><br>"
        "ComfyUI <u>must be restarted</u> before the benchmark can continue.<br><br>"
        "To run the benchmark with the current settings, run:"
    )
    header.setWordWrap(True)
    layout.addWidget(header)

    cmd_parts = [
        python_exe,
        script_fpath,
        "-c", f'"{args.comfy_path}"',
        "-w", f'"{args.workflow_path}"',
        "-p", str(args.port),
        "-g", str(args.generations),
        "--gui",
    ]
    if getattr(args, "extract_minimal", False): cmd_parts.append("-e")
    if getattr(args, "run_default", False): cmd_parts.append("-r")
    if getattr(args, "debug_warmup", False): cmd_parts.append("--debug-warmup")
    if getattr(args, "no_cleanup", False): cmd_parts.append("--no-cleanup")
    if getattr(args, "use_main_workflow_only", False): cmd_parts.append("-u")
    if getattr(args, "force_extract", False): cmd_parts.append("-f")
    if getattr(args, "override", None): cmd_parts.extend(["-o", f'"{args.override}"'])
    if getattr(args, "num_instances", 1) != 1: cmd_parts.extend(["-n", str(args.num_instances)])
    if getattr(args, "timeout", 4000) != 4000: cmd_parts.extend(["--timeout", str(args.timeout)])
    if getattr(args, "extra_args", []): cmd_parts.extend(args.extra_args)

    full_command = " ".join(cmd_parts)

    cmd_label = QLabel("Command to re-run after restart:")
    cmd_label.setStyleSheet("font-weight: bold;")
    layout.addWidget(cmd_label)

    cmd_edit = QTextEdit()
    cmd_edit.setPlainText(full_command)
    cmd_edit.setFont(QFont("Consolas", 10))
    cmd_edit.setMaximumHeight(80)
    cmd_edit.setStyleSheet("""
        QTextEdit {
            background-color: #f8f8f8;
            color: #1a1a1a;
            padding: 6px;
            border: 1px solid #ccc;
            border-radius: 4px;
        }
    """)
    cmd_edit.setReadOnly(True)
    layout.addWidget(cmd_edit)

    btn_layout = QHBoxLayout()
    btn_layout.setSpacing(8)

    copy_btn = QPushButton("Copy Command")
    copy_btn.setFixedWidth(120)
    copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(full_command))
    btn_layout.addWidget(copy_btn)

    ok_btn = QPushButton("OK")
    ok_btn.setDefault(True)
    ok_btn.setFixedWidth(80)
    ok_btn.clicked.connect(dialog.accept)
    btn_layout.addWidget(ok_btn)

    btn_layout.addStretch()
    layout.addLayout(btn_layout)

    if log_file:
        log_info = QLabel(f"<small>Log: <code>{log_file}</code></small>")
        layout.addWidget(log_info)

        log_copy = QPushButton("Copy Log Path")
        log_copy.setFixedWidth(120)
        log_copy.clicked.connect(lambda: QApplication.clipboard().setText(str(log_file)))
        log_btn_layout = QHBoxLayout()
        log_btn_layout.addStretch()
        log_btn_layout.addWidget(log_copy)
        layout.addLayout(log_btn_layout)

    dialog.resize(680, dialog.sizeHint().height())
    dialog.exec_()

def get_hf_token_dialog(parent=None):
    """
    Open a dialog to request the Hugging Face token from the user.
    Returns the token string if OK is clicked, else None.
    """
    if not QT_AVAILABLE:
        # Fallback for CLI mode
        try:
            return input("\n[Interact] Please enter your Hugging Face Token: ").strip() or None
        except EOFError:
            return None

    # Ensure we have an application instance
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    from qtpy.QtWidgets import QInputDialog, QLineEdit
    
    text, ok = QInputDialog.getText(
        parent, 
        "Hugging Face Token Required",
        "This workflow uses gated models (e.g., Flux).\n"
        "Please enter your Hugging Face Access Token (Read permission):",
        QLineEdit.Password
    )
    
    if ok and text:
        return text.strip()
    return None