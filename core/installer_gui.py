"""GUI for ComfyUI Modular Installer."""

import sys
import os
import zipfile
from pathlib import Path
from typing import Optional
from datetime import datetime

try:
    from qtpy.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
        QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
        QCheckBox, QFormLayout, QTextEdit, QProgressBar, QInputDialog
    )
    from qtpy.QtCore import Qt, QThread, Signal
    from qtpy.QtGui import QFont, QIcon
    QT_AVAILABLE = True
except Exception:
    QT_AVAILABLE = False


class InstallerThread(QThread):
    """Thread for running installer operations."""
    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal(bool, str)
    request_hf_token_signal = Signal()  # Signal to request HF token from main thread

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.hf_token = None  # Will be set by main thread if requested

    def run(self):
        """Run the installation in a separate thread."""
        temp_dir = None  # Track temp directory for cleanup
        try:
            # Import here to avoid circular imports
            from core.comfyui_installer import ComfyUIInstaller
            from core.manifest_handler import ManifestHandler

            self.log_signal.emit("Starting installation...")

            # Install/detect ComfyUI
            if not self.config.get('comfy_path'):
                self.log_signal.emit("Checking for ComfyUI installation...")
                install_path_str = self.config.get('install_path', '~/ComfyUI_BP')
                install_path = Path(os.path.expanduser(install_path_str))
                installer = ComfyUIInstaller(install_path=install_path)

                if not installer.check_existing_installation():
                    msg = f"✗ ComfyUI not found at {install_path}"
                    self.log_signal.emit(msg)
                    print(msg)
                    msg = "→ Installing ComfyUI..."
                    self.log_signal.emit(msg)
                    print(msg)
                    success, message = installer.install_comfyui()
                    if not success:
                        self.finished_signal.emit(False, message)
                        return
                    self.log_signal.emit(f"✓ {message}")
                else:
                    msg = f"✓ ComfyUI found at {install_path}"
                    self.log_signal.emit(msg)
                    print(msg)

                info = installer.get_installation_info()
                comfy_path = info['comfyui_path']
                python_executable = info['python_executable']

                # Install Blender if requested
                if self.config.get('install_blender') and sys.platform == 'win32':
                    self.log_signal.emit("Checking Blender installation...")
                    if not installer.check_blender_installed():
                        msg = "✗ Blender 4.5 LTS not found"
                        self.log_signal.emit(msg)
                        print(msg)
                        msg = "→ Installing Blender 4.5 LTS..."
                        self.log_signal.emit(msg)
                        print(msg)
                        success, message = installer.install_blender()
                        self.log_signal.emit(f"Blender: {message}")
                    else:
                        msg = "✓ Blender 4.5 LTS already installed"
                        self.log_signal.emit(msg)
                        print(msg)
                else:
                    if sys.platform == 'win32':
                        msg = "⊘ Skipping Blender installation (disabled by user)"
                        self.log_signal.emit(msg)
                        print(msg)  # Also print to console
                    else:
                        msg = "⊘ Skipping Blender installation (not supported on this platform)"
                        self.log_signal.emit(msg)
                        print(msg)  # Also print to console
            else:
                # User specified custom ComfyUI path - check for embedded Python
                comfy_path = Path(self.config['comfy_path'])

                # Try to find embedded Python at the specified path
                install_root = comfy_path.parent if comfy_path.name == "ComfyUI" else comfy_path

                possible_python_paths = [
                    install_root / "python_embeded" / "python.exe",
                    install_root / "python_embedded" / "python.exe",
                    comfy_path / ".." / "python_embeded" / "python.exe",
                    comfy_path / ".." / "python_embedded" / "python.exe",
                ]

                python_executable = None
                for py_path in possible_python_paths:
                    resolved_path = py_path.resolve()
                    if resolved_path.exists():
                        python_executable = resolved_path
                        msg = f"✓ Found embedded Python: {python_executable}"
                        self.log_signal.emit(msg)
                        print(msg)
                        break

                if not python_executable:
                    msg = f"⚠ No embedded Python found at {comfy_path}"
                    self.log_signal.emit(msg)
                    print(msg)
                    msg = f"  Will use system Python for pip installations"
                    self.log_signal.emit(msg)
                    print(msg)
                    python_executable = None  # Will fall back to sys.executable

            # Process manifest
            manifest_path = Path(self.config['manifest_path'])
            install_temp_path = None

            # Handle ZIP packages with InstallTemp folder
            if manifest_path.suffix.lower() == '.zip':
                self.log_signal.emit(f"Extracting manifest from ZIP: {manifest_path.name}")

                # Create temp directory for extraction
                temp_dir = comfy_path / f"temp_manifest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                temp_dir.mkdir(parents=True, exist_ok=True)

                with zipfile.ZipFile(manifest_path, 'r') as zf:
                    # Extract manifest
                    manifest_locations = ['manifest.json', 'manifest.yaml', 'manifest.yml']
                    manifest_file = None

                    for loc in manifest_locations:
                        if loc in zf.namelist():
                            manifest_file = loc
                            break

                    if not manifest_file:
                        raise FileNotFoundError("No manifest.json/yaml found in ZIP package")

                    zf.extract(manifest_file, temp_dir)
                    manifest_path = temp_dir / manifest_file
                    self.log_signal.emit(f"✓ Manifest extracted: {manifest_file}")

                    # Check for InstallTemp folder and extract it
                    install_temp_files = [f for f in zf.namelist() if f.startswith('InstallTemp/')]
                    if install_temp_files:
                        self.log_signal.emit(f"Found InstallTemp folder - extracting {len(install_temp_files)} files...")
                        install_temp_path = temp_dir / "InstallTemp"

                        for file in install_temp_files:
                            zf.extract(file, temp_dir)

                        self.log_signal.emit(f"✓ InstallTemp extracted")

                    # Check for ComfyUI folder and merge it into installation
                    comfyui_files = [f for f in zf.namelist() if f.startswith('ComfyUI/') and not f.startswith('ComfyUI/.')]
                    if comfyui_files:
                        self.log_signal.emit(f"Found ComfyUI folder in package - merging {len(comfyui_files)} files...")

                        for file in comfyui_files:
                            # Extract to temp first
                            zf.extract(file, temp_dir)

                            # Determine source and destination
                            source_file = temp_dir / file
                            # Remove 'ComfyUI/' prefix to get relative path
                            relative_path = Path(file).relative_to('ComfyUI')
                            dest_file = comfy_path / relative_path

                            # Skip directories (they're created automatically)
                            if source_file.is_file():
                                dest_file.parent.mkdir(parents=True, exist_ok=True)
                                import shutil
                                shutil.copy2(source_file, dest_file)

                        self.log_signal.emit(f"✓ ComfyUI folder merged into {comfy_path}")

            self.log_signal.emit(f"Loading manifest: {manifest_path.name}")

            handler = ManifestHandler(
                manifest_path=manifest_path,
                comfy_path=comfy_path,
                python_executable=python_executable,
                max_workers=self.config.get('workers', 4),
                install_temp_path=install_temp_path,
                log_callback=self.log_signal.emit  # Pass GUI log callback
            )

            handler.load_manifest()
            handler.validate_manifest()

            # Ensure prerequisites (git, git-lfs) are available
            handler.ensure_prerequisites()

            # Check for gated models and prompt for HF token if needed
            if handler.has_gated_models() and not handler.hf_token:
                self.log_signal.emit("\n⚠ Gated models detected - HuggingFace token required")
                # Request token from main thread and wait for response
                self.request_hf_token_signal.emit()

                # Wait for token to be set (with timeout)
                import time
                timeout = 60  # 60 seconds timeout
                start_time = time.time()
                while self.hf_token is None and (time.time() - start_time) < timeout:
                    time.sleep(0.1)

                if self.hf_token:
                    handler.set_hf_token(self.hf_token)
                    self.log_signal.emit("✓ HuggingFace token provided")
                elif self.hf_token == "":
                    # User cancelled
                    self.log_signal.emit("⚠ No token provided - gated models may fail to download")
                else:
                    # Timeout
                    self.log_signal.emit("⚠ Token prompt timed out - gated models may fail to download")

            self.log_signal.emit("Downloading and installing items...")
            handler.download_items(
                skip_existing=not self.config.get('force', False),
                required_only=self.config.get('required_only', False),
                parallel=True
            )

            self.log_signal.emit("\n✓ Installation completed successfully!")
            self.finished_signal.emit(True, "Installation completed successfully")

        except Exception as e:
            self.log_signal.emit(f"\n✗ Error: {str(e)}")
            self.finished_signal.emit(False, str(e))
        finally:
            # Cleanup temporary files (unless --keep-extracted flag is set)
            if temp_dir and temp_dir.exists():
                if self.config.get('keep_extracted', False):
                    self.log_signal.emit(f"\n⚠ Keeping extracted files for debugging: {temp_dir}")
                else:
                    self.log_signal.emit("\nCleaning up temporary files...")
                    import shutil
                    try:
                        shutil.rmtree(temp_dir)
                        self.log_signal.emit("✓ Cleanup complete")
                    except Exception as e:
                        self.log_signal.emit(f"⚠ Cleanup warning: {str(e)}")


def run_installer_gui() -> dict:
    """Launch the installer GUI."""
    if not QT_AVAILABLE:
        print("Qt bindings not found. Please install PySide6 or PyQt5.")
        sys.exit(1)

    app = QApplication(sys.argv)

    # Set window icon
    script_dir = Path(__file__).parent
    icon_path = script_dir / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    win = InstallerWindow()
    win.show()

    app.exec_()

    if win.result:
        return win.result
    else:
        sys.exit(0)


class InstallerWindow(QWidget):
    """Main installer GUI window."""

    def __init__(self):
        super().__init__()
        self.result = None
        self.installer_thread = None
        self.init_ui()

    def _get_package_name_from_zip(self, zip_path: Path) -> str:
        """
        Extract package name from manifest inside ZIP file.

        Args:
            zip_path: Path to the ZIP package

        Returns:
            Package name from manifest, or default title if not found
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Look for manifest file
                manifest_locations = ['manifest.json', 'manifest.yaml', 'manifest.yml']
                manifest_file = None

                for loc in manifest_locations:
                    if loc in zf.namelist():
                        manifest_file = loc
                        break

                if not manifest_file:
                    return "ComfyUI Modular Installer"

                # Read manifest content
                manifest_content = zf.read(manifest_file).decode('utf-8')

                # Parse based on file type
                if manifest_file.endswith('.json'):
                    import json
                    manifest = json.loads(manifest_content)
                else:  # YAML
                    import yaml
                    manifest = yaml.safe_load(manifest_content)

                # Extract package name
                package_name = manifest.get('package', {}).get('name')
                if package_name:
                    return package_name

        except Exception as e:
            print(f"Warning: Could not read package name from manifest: {e}")

        return "ComfyUI Modular Installer"

    def init_ui(self):
        """Initialize the user interface."""
        # Check for bundled package.zip if running as frozen executable
        bundled_package = None
        package_title = "ComfyUI Modular Installer"  # Default title

        if getattr(sys, 'frozen', False):
            # Check two locations:
            # 1. Inside the executable (PyInstaller --add-data)
            # 2. External file alongside the executable

            if hasattr(sys, '_MEIPASS'):
                # PyInstaller extracts bundled data to _MEIPASS temp directory
                internal_package = Path(sys._MEIPASS) / "package.zip"
                if internal_package.exists():
                    bundled_package = internal_package
                    print(f"Found package.zip bundled inside executable: {bundled_package}")

            if not bundled_package:
                # Check for external package.zip alongside the executable
                exe_dir = Path(sys.executable).parent
                external_package = exe_dir / "package.zip"
                if external_package.exists():
                    bundled_package = external_package
                    print(f"Found package.zip alongside executable: {bundled_package}")

            # If we found a bundled package, extract package name from manifest
            if bundled_package:
                package_title = self._get_package_name_from_zip(bundled_package)

        self.setWindowTitle(package_title)
        self.setMinimumSize(700, 600)
        self.resize(700, 600)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)
        self.setLayout(main_layout)

        # Title
        title = QLabel(package_title)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        main_layout.addWidget(title)

        # === INSTALLATION OPTIONS ===
        install_group = QGroupBox("Installation Options")
        install_layout = QFormLayout()
        install_group.setLayout(install_layout)

        # ComfyUI Path
        comfy_layout = QHBoxLayout()
        self.comfy_path_edit = QLineEdit()
        self.comfy_path_edit.setPlaceholderText("Auto-install to ~/ComfyUI_BP")
        comfy_browse_btn = QPushButton("Browse...")
        comfy_browse_btn.clicked.connect(self.browse_comfy_path)
        comfy_layout.addWidget(self.comfy_path_edit)
        comfy_layout.addWidget(comfy_browse_btn)
        install_layout.addRow("ComfyUI Path (optional):", comfy_layout)

        # Manifest Path
        manifest_layout = QHBoxLayout()
        self.manifest_path_edit = QLineEdit()
        self.manifest_browse_btn = QPushButton("Browse...")
        self.manifest_browse_btn.clicked.connect(self.browse_manifest)

        if bundled_package:
            # Use bundled package and disable editing
            self.manifest_path_edit.setText(str(bundled_package))
            self.manifest_path_edit.setReadOnly(True)
            self.manifest_path_edit.setPlaceholderText("Using bundled package")
            self.manifest_browse_btn.setEnabled(False)
            self.manifest_browse_btn.setToolTip("Package bundled with installer")
        else:
            # Allow user to select manifest
            self.manifest_path_edit.setPlaceholderText("Select manifest.json or package.zip")

        manifest_layout.addWidget(self.manifest_path_edit)
        manifest_layout.addWidget(self.manifest_browse_btn)
        install_layout.addRow("Manifest File*:", manifest_layout)

        main_layout.addWidget(install_group)

        # === DOWNLOAD OPTIONS ===
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()
        options_group.setLayout(options_layout)

        self.force_checkbox = QCheckBox("Force re-download all items")
        self.required_only_checkbox = QCheckBox("Install only required items")
        self.install_blender_checkbox = QCheckBox("Install Blender 4.5 LTS (Windows only)")
        self.install_blender_checkbox.setChecked(True)

        if sys.platform != "win32":
            self.install_blender_checkbox.setEnabled(False)
            self.install_blender_checkbox.setToolTip("Blender auto-install is Windows-only")

        options_layout.addWidget(self.force_checkbox)
        options_layout.addWidget(self.required_only_checkbox)
        options_layout.addWidget(self.install_blender_checkbox)

        main_layout.addWidget(options_group)

        # === PROGRESS ===
        progress_group = QGroupBox("Installation Progress")
        progress_layout = QVBoxLayout()
        progress_group.setLayout(progress_layout)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(200)
        progress_layout.addWidget(self.log_output)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)

        main_layout.addWidget(progress_group)

        # === BUTTONS ===
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.install_btn = QPushButton("Install")
        self.install_btn.setMinimumWidth(120)
        self.install_btn.clicked.connect(self.start_installation)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumWidth(120)
        self.cancel_btn.clicked.connect(self.close)

        button_layout.addWidget(self.install_btn)
        button_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(button_layout)

    def browse_comfy_path(self):
        """Browse for ComfyUI directory."""
        path = QFileDialog.getExistingDirectory(
            self,
            "Select ComfyUI Directory",
            str(Path.home())
        )
        if path:
            self.comfy_path_edit.setText(path)

    def browse_manifest(self):
        """Browse for manifest file or package."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Manifest or Package",
            str(Path.home()),
            "Manifest Files (manifest.json manifest.yaml manifest.yml *.zip);;All Files (*)"
        )
        if path:
            self.manifest_path_edit.setText(path)

    def start_installation(self):
        """Start the installation process."""
        manifest_path = self.manifest_path_edit.text().strip()

        if not manifest_path:
            QMessageBox.warning(self, "Missing Information", "Please select a manifest file or package.")
            return

        if not Path(manifest_path).exists():
            QMessageBox.warning(self, "File Not Found", f"Manifest file not found: {manifest_path}")
            return

        # Disable controls
        self.install_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.log_output.clear()

        # Build configuration
        config = {
            'manifest_path': manifest_path,
            'force': self.force_checkbox.isChecked(),
            'required_only': self.required_only_checkbox.isChecked(),
            'install_blender': self.install_blender_checkbox.isChecked(),
            'keep_extracted': '--keep-extracted' in sys.argv,  # Check for CLI flag
        }

        comfy_path = self.comfy_path_edit.text().strip()
        if comfy_path:
            config['comfy_path'] = comfy_path

        # Start installer thread
        self.installer_thread = InstallerThread(config)
        self.installer_thread.log_signal.connect(self.append_log)
        self.installer_thread.finished_signal.connect(self.installation_finished)
        self.installer_thread.request_hf_token_signal.connect(self.prompt_for_hf_token)
        self.installer_thread.start()

    def append_log(self, message: str):
        """Append message to log output."""
        self.log_output.append(message)
        self.log_output.verticalScrollBar().setValue(
            self.log_output.verticalScrollBar().maximum()
        )

    def installation_finished(self, success: bool, message: str):
        """Handle installation completion."""
        self.progress_bar.setVisible(False)
        self.install_btn.setEnabled(True)

        if success:
            QMessageBox.information(
                self,
                "Installation Complete",
                "ComfyUI and all components have been installed successfully!"
            )
            self.result = {'success': True}
            self.close()
        else:
            QMessageBox.critical(
                self,
                "Installation Failed",
                f"Installation failed:\n\n{message}"
            )

    def prompt_for_hf_token(self):
        """Prompt user for HuggingFace token."""
        text, ok = QInputDialog.getText(
            self,
            "HuggingFace Token Required",
            "This package includes gated models that require a HuggingFace token.\n\n"
            "To get a token:\n"
            "1. Visit https://huggingface.co/settings/tokens\n"
            "2. Create a new token with 'Read' permission\n"
            "3. Accept the license for gated models on HuggingFace\n"
            "4. Paste the token below\n\n"
            "Token:",
            QLineEdit.Password
        )

        if ok and text:
            self.installer_thread.hf_token = text.strip()
        else:
            # User cancelled - set empty string to signal cancellation
            self.installer_thread.hf_token = ""


if __name__ == "__main__":
    run_installer_gui()
