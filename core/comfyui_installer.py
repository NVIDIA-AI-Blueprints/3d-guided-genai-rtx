"""ComfyUI portable installation and detection."""

import os
import sys
import shutil
import requests
import subprocess
import platform
from pathlib import Path
from typing import Optional, Tuple
from tqdm import tqdm
import py7zr


class ComfyUIInstaller:
    """Handles ComfyUI portable installation and detection."""

    COMFYUI_DOWNLOAD_URL = "https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z"
    DEFAULT_INSTALL_PATH = Path(os.path.expanduser("~")) / "ComfyUI_BP"
    BLENDER_WINGET_ID = "BlenderFoundation.Blender.LTS.4.5"
    SEVENZIP_STANDALONE_URL = "https://www.7-zip.org/a/7zr.exe"

    def __init__(self, install_path: Optional[Path] = None, log_file: Optional[Path] = None):
        """
        Initialize ComfyUI installer.

        Args:
            install_path: Path where ComfyUI should be installed (default: ~/ComfyUI_BP)
            log_file: Optional log file path
        """
        if install_path:
            # Ensure path is properly expanded (handle ~, environment variables, etc.)
            path_str = str(install_path)
            expanded_path = os.path.expanduser(os.path.expandvars(path_str))
            self.install_path = Path(expanded_path).resolve()
        else:
            self.install_path = self.DEFAULT_INSTALL_PATH

        self.log_file = log_file

    def log(self, message: str, level: str = "INFO"):
        """Log message to console and file."""
        print(message)
        if self.log_file:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{level}] {message}\n")

    def check_existing_installation(self) -> bool:
        """
        Check if ComfyUI is already installed at the target location.

        Returns:
            True if installation exists, False otherwise
        """
        if not self.install_path.exists():
            return False

        # Check for key ComfyUI files/directories
        key_files = [
            self.install_path / "ComfyUI" / "main.py",
            self.install_path / "python_embeded"  # Note: ComfyUI uses 'embeded' not 'embedded'
        ]

        return any(f.exists() for f in key_files)

    def get_python_executable(self) -> Optional[Path]:
        """
        Get path to embedded Python executable.

        Returns:
            Path to python.exe if found, None otherwise
        """
        # ComfyUI portable uses 'python_embeded' (not 'embedded')
        possible_paths = [
            self.install_path / "python_embeded" / "python.exe",
            self.install_path / "python_embedded" / "python.exe",  # Just in case
        ]

        for path in possible_paths:
            if path.exists():
                return path

        return None

    def get_comfyui_path(self) -> Optional[Path]:
        """
        Get path to ComfyUI directory.

        Returns:
            Path to ComfyUI folder if found, None otherwise
        """
        comfyui_path = self.install_path / "ComfyUI"
        return comfyui_path if comfyui_path.exists() else None

    def download_comfyui(self, output_path: Path) -> bool:
        """
        Download ComfyUI portable archive.

        Args:
            output_path: Where to save the downloaded .7z file

        Returns:
            True if successful, False otherwise
        """
        self.log(f"Downloading ComfyUI portable from GitHub...")
        self.log(f"URL: {self.COMFYUI_DOWNLOAD_URL}")

        try:
            response = requests.get(self.COMFYUI_DOWNLOAD_URL, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))

            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Download with progress bar
            with open(output_path, 'wb') as f:
                with tqdm(total=total_size, unit='B', unit_scale=True,
                         desc="Downloading ComfyUI", ncols=80) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

            self.log(f"✓ Download complete: {output_path}")
            return True

        except Exception as e:
            self.log(f"✗ Download failed: {e}", "ERROR")
            return False

    def extract_comfyui(self, archive_path: Path, extract_to: Path) -> bool:
        """
        Extract ComfyUI 7z archive.

        The archive contains a top-level directory called 'ComfyUI_windows_portable'.
        We extract to temp first, then move the contents to the final location.

        Args:
            archive_path: Path to .7z file
            extract_to: Final directory to install to

        Returns:
            True if successful, False otherwise
        """
        self.log(f"Extracting ComfyUI...")

        # Extract to temp directory first (same directory as the archive)
        temp_extract = archive_path.parent / "temp_extract"

        try:
            # Ensure temp extraction directory exists
            temp_extract.mkdir(parents=True, exist_ok=True)

            # Try extraction methods
            extraction_success = False

            # Try method 1: Use system 7z.exe (most reliable)
            if self._try_extract_with_7zip(archive_path, temp_extract):
                self.log(f"✓ Extraction complete (using 7-Zip)")
                extraction_success = True

            # Try method 2: Use PowerShell Expand-Archive (Windows fallback)
            if not extraction_success and sys.platform == "win32" and self._try_extract_with_powershell(archive_path, temp_extract):
                self.log(f"✓ Extraction complete (using PowerShell)")
                extraction_success = True

            # Try method 3: Use py7zr (may fail with BCJ2 filter)
            if not extraction_success:
                self.log("Trying py7zr extraction...")
                try:
                    with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                        archive.extractall(path=temp_extract)
                    self.log(f"✓ Extraction complete (using py7zr)")
                    extraction_success = True
                except Exception as e:
                    if "BCJ2" in str(e):
                        self.log(f"✗ py7zr doesn't support this archive format", "ERROR")
                    else:
                        raise

            # Try method 4: Download and use 7zr.exe (final fallback)
            if not extraction_success:
                self.log("Attempting to download standalone 7-Zip extractor...")
                if self._try_extract_with_downloaded_7zr(archive_path, temp_extract):
                    self.log(f"✓ Extraction complete (using downloaded 7zr.exe)")
                    extraction_success = True

            # All methods failed
            if not extraction_success:
                self.log(f"✗ All extraction methods failed", "ERROR")
                self.log(f"  Please install 7-Zip manually from https://www.7-zip.org/", "ERROR")
                return False

            # Now move contents from ComfyUI_windows_portable to final location
            self.log(f"Moving files to final location: {extract_to}")

            # Find the ComfyUI_windows_portable directory
            portable_dir = temp_extract / "ComfyUI_windows_portable"

            if not portable_dir.exists():
                # Check if files were extracted directly
                extracted_items = list(temp_extract.iterdir())
                self.log(f"  Extracted items in temp: {[item.name for item in extracted_items]}", "WARNING")
                self.log(f"  Looking for ComfyUI_windows_portable folder...", "ERROR")
                return False

            # Create final directory
            extract_to.mkdir(parents=True, exist_ok=True)

            # Move all contents from portable_dir to extract_to
            items_to_move = list(portable_dir.iterdir())
            self.log(f"  Moving {len(items_to_move)} items...")

            for item in items_to_move:
                dest = extract_to / item.name
                if dest.exists():
                    # Remove existing item
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                shutil.move(str(item), str(dest))

            self.log(f"✓ Successfully moved all files to {extract_to}")

            # Cleanup temp extraction directory
            shutil.rmtree(temp_extract, ignore_errors=True)

            return True

        except Exception as e:
            self.log(f"✗ Extraction failed: {e}", "ERROR")
            # Cleanup on failure
            if temp_extract.exists():
                shutil.rmtree(temp_extract, ignore_errors=True)
            return False

    def _try_extract_with_7zip(self, archive_path: Path, extract_to: Path) -> bool:
        """
        Try to extract using 7z.exe command-line tool.

        Returns:
            True if successful, False if 7z.exe not found
        """
        # Common 7-Zip installation paths
        possible_7z_paths = [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
            "7z",  # Try PATH
        ]

        for seven_zip_path in possible_7z_paths:
            try:
                # Test if 7z exists
                result = subprocess.run(
                    [seven_zip_path],
                    capture_output=True,
                    timeout=5
                )

                # Ensure extract_to path is absolute and resolved
                extract_to_abs = extract_to.resolve()

                # 7z.exe exists, use it to extract
                self.log(f"Using 7-Zip: {seven_zip_path}")
                self.log(f"  Archive: {archive_path}")
                self.log(f"  Destination: {extract_to_abs}")

                result = subprocess.run(
                    [seven_zip_path, 'x', str(archive_path), f'-o{extract_to_abs}', '-y'],
                    capture_output=True,
                    text=True,
                    timeout=600
                )

                if result.returncode == 0:
                    # Debug: List what was extracted
                    if extract_to_abs.exists():
                        extracted_items = list(extract_to_abs.iterdir())
                        self.log(f"  Extracted {len(extracted_items)} items to {extract_to_abs}")
                        for item in extracted_items[:5]:  # Show first 5 items
                            self.log(f"    - {item.name}")
                        if len(extracted_items) > 5:
                            self.log(f"    ... and {len(extracted_items) - 5} more items")
                    return True
                else:
                    self.log(f"  7-Zip extraction failed: {result.stderr}", "WARNING")
                    return False

            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            except Exception as e:
                self.log(f"  7-Zip error: {e}", "WARNING")
                continue

        return False

    def _try_extract_with_powershell(self, archive_path: Path, extract_to: Path) -> bool:
        """
        Try to extract using PowerShell (Windows only, but won't work for .7z).

        Note: PowerShell Expand-Archive only supports .zip, not .7z
        This is kept as a fallback but will likely not work for ComfyUI.

        Returns:
            True if successful, False otherwise
        """
        # PowerShell can't extract .7z files, only .zip
        if archive_path.suffix.lower() == '.7z':
            return False

        try:
            cmd = [
                'powershell', '-Command',
                f'Expand-Archive -Path "{archive_path}" -DestinationPath "{extract_to}" -Force'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )

            return result.returncode == 0

        except Exception:
            return False

    def _download_7zr(self) -> Optional[Path]:
        """
        Download standalone 7zr.exe to a temp location.

        Returns:
            Path to downloaded 7zr.exe if successful, None otherwise
        """
        try:
            # Store in temp directory
            temp_dir = Path(os.path.expanduser("~")) / "temp_comfyui_install"
            temp_dir.mkdir(parents=True, exist_ok=True)
            seven_zr_path = temp_dir / "7zr.exe"

            # Check if already downloaded
            if seven_zr_path.exists():
                self.log(f"Using cached 7zr.exe: {seven_zr_path}")
                return seven_zr_path

            self.log(f"Downloading standalone 7-Zip extractor (7zr.exe)...")

            response = requests.get(self.SEVENZIP_STANDALONE_URL, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))

            with open(seven_zr_path, 'wb') as f:
                if total_size > 0:
                    with tqdm(total=total_size, unit='B', unit_scale=True,
                             desc="Downloading 7zr.exe", ncols=80) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
                else:
                    # No content-length header, download without progress bar
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            self.log(f"✓ Downloaded 7zr.exe to: {seven_zr_path}")
            return seven_zr_path

        except Exception as e:
            self.log(f"✗ Failed to download 7zr.exe: {e}", "WARNING")
            return None

    def _try_extract_with_downloaded_7zr(self, archive_path: Path, extract_to: Path) -> bool:
        """
        Try to extract using downloaded 7zr.exe.

        Returns:
            True if successful, False otherwise
        """
        seven_zr_path = self._download_7zr()
        if not seven_zr_path:
            return False

        try:
            # Ensure extract_to path is absolute and resolved
            extract_to_abs = extract_to.resolve()
            self.log(f"Using downloaded 7zr.exe for extraction...")
            self.log(f"  Archive: {archive_path}")
            self.log(f"  Destination: {extract_to_abs}")

            result = subprocess.run(
                [str(seven_zr_path), 'x', str(archive_path), f'-o{extract_to_abs}', '-y'],
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode == 0:
                # Debug: List what was extracted
                if extract_to_abs.exists():
                    extracted_items = list(extract_to_abs.iterdir())
                    self.log(f"  Extracted {len(extracted_items)} items to {extract_to_abs}")
                    for item in extracted_items[:5]:  # Show first 5 items
                        self.log(f"    - {item.name}")
                    if len(extracted_items) > 5:
                        self.log(f"    ... and {len(extracted_items) - 5} more items")
                return True
            else:
                self.log(f"  7zr.exe extraction failed: {result.stderr}", "WARNING")
                return False

        except Exception as e:
            self.log(f"  7zr.exe error: {e}", "WARNING")
            return False

    def install_comfyui(self, force_reinstall: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Install ComfyUI portable to the target location.

        Args:
            force_reinstall: If True, reinstall even if already exists

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Check for existing installation
        if self.check_existing_installation() and not force_reinstall:
            # Set environment variable even for existing installation
            self.log("Setting COMFYUI_BASE environment variable...")
            self.set_persistent_env_var("COMFYUI_BASE", str(self.install_path), system_level=False)
            return True, f"ComfyUI already installed at {self.install_path}"

        # Create temp directory for download
        temp_dir = Path(os.path.expanduser("~")) / "temp_comfyui_install"
        temp_dir.mkdir(parents=True, exist_ok=True)
        archive_path = temp_dir / "ComfyUI_portable.7z"

        try:
            # Download
            if not self.download_comfyui(archive_path):
                return False, "Failed to download ComfyUI"

            # Extract
            if not self.extract_comfyui(archive_path, self.install_path):
                return False, "Failed to extract ComfyUI"

            # Verify installation
            self.log("\nVerifying installation...")
            self.log(f"  Looking for ComfyUI files in: {self.install_path}")

            # Debug: Check what exists
            if self.install_path.exists():
                items = list(self.install_path.iterdir())
                self.log(f"  Found {len(items)} items in install directory:")
                for item in items[:10]:
                    self.log(f"    - {item.name}")
                if len(items) > 10:
                    self.log(f"    ... and {len(items) - 10} more items")
            else:
                self.log(f"  Install directory does not exist: {self.install_path}", "ERROR")

            if not self.check_existing_installation():
                self.log("  Looking for: ComfyUI/main.py and python_embeded/", "ERROR")
                return False, "Installation verification failed - required files not found"

            # Set persistent environment variable
            self.log("\nSetting COMFYUI_BASE environment variable...")
            env_success = self.set_persistent_env_var("COMFYUI_BASE", str(self.install_path), system_level=False)
            if env_success:
                self.log(f"  COMFYUI_BASE = {self.install_path}")
            else:
                self.log("  ⚠ Warning: Failed to set COMFYUI_BASE environment variable", "WARNING")
                self.log("  You may need to set it manually", "WARNING")

            # Cleanup
            self.log("\nCleaning up temporary files...")
            shutil.rmtree(temp_dir, ignore_errors=True)

            return True, f"ComfyUI successfully installed to {self.install_path}"

        except Exception as e:
            self.log(f"✗ Installation failed: {e}", "ERROR")
            # Cleanup on failure
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False, f"Installation failed: {e}"

    def get_installation_info(self) -> dict:
        """
        Get information about the ComfyUI installation.

        Returns:
            Dictionary with installation details
        """
        info = {
            'installed': self.check_existing_installation(),
            'install_path': self.install_path,
            'comfyui_path': self.get_comfyui_path(),
            'python_executable': self.get_python_executable(),
            'is_portable': False,
            'platform': sys.platform
        }

        if info['python_executable']:
            info['is_portable'] = True

        return info

    @staticmethod
    def is_admin() -> bool:
        """
        Check if the current process has administrator privileges.

        Returns:
            True if running as admin, False otherwise
        """
        try:
            if platform.system() == "Windows":
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin()
            else:
                # On Unix-like systems, check if effective UID is 0 (root)
                return os.geteuid() == 0
        except Exception:
            return False

    def check_blender_installed(self) -> bool:
        """
        Check if Blender is installed.

        Returns:
            True if Blender is found, False otherwise
        """
        try:
            if platform.system() == "Windows":
                # Check via winget
                result = subprocess.run(
                    ['winget', 'list', '--id', self.BLENDER_WINGET_ID],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                # If Blender is installed, it will appear in the output
                return self.BLENDER_WINGET_ID in result.stdout
            else:
                # On Linux/Mac, check if blender command exists
                result = subprocess.run(
                    ['which', 'blender'],
                    capture_output=True,
                    text=True
                )
                return result.returncode == 0
        except Exception:
            return False

    def install_blender(self) -> Tuple[bool, str]:
        """
        Install Blender 4.5 LTS using winget (Windows only).

        Returns:
            Tuple of (success: bool, message: str)
        """
        if platform.system() != "Windows":
            return False, "Blender installation via winget is only supported on Windows"

        # Check if already installed
        if self.check_blender_installed():
            self.log("✓ Blender 4.5 LTS is already installed")
            return True, "Blender already installed"

        self.log(f"Installing Blender 4.5 LTS via winget...")

        try:
            # Install with winget (silent mode)
            result = subprocess.run(
                ['winget', 'install', '--id', self.BLENDER_WINGET_ID, '--source', 'winget', '--silent', '--accept-package-agreements', '--accept-source-agreements'],
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for download/install
            )

            if result.returncode == 0:
                self.log("✓ Blender 4.5 LTS installed successfully")
                return True, "Blender installed successfully"
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                self.log(f"✗ Blender installation failed: {error_msg}", "ERROR")
                return False, f"Blender installation failed: {error_msg}"

        except subprocess.TimeoutExpired:
            self.log("✗ Blender installation timed out", "ERROR")
            return False, "Blender installation timed out"
        except FileNotFoundError:
            self.log("✗ winget not found. Please install App Installer from Microsoft Store", "ERROR")
            return False, "winget not found"
        except Exception as e:
            self.log(f"✗ Blender installation failed: {e}", "ERROR")
            return False, f"Blender installation failed: {e}"

    def set_persistent_env_var(self, name: str, value: str, system_level: bool = False) -> bool:
        """
        Set a persistent environment variable across OS platforms.

        Args:
            name: Environment variable name
            value: Environment variable value
            system_level: Set at system level (requires admin/root)

        Returns:
            True if successful, False otherwise
        """
        try:
            if platform.system() == "Windows":
                # Windows: Use setx or PowerShell
                if system_level:
                    if not self.is_admin():
                        self.log("⚠ System-level environment variable requires administrator privileges", "WARNING")
                        self.log("  Setting at user level instead...", "WARNING")
                        system_level = False

                if system_level:
                    # Use PowerShell for system-level
                    cmd = [
                        'powershell', '-Command',
                        f'[Environment]::SetEnvironmentVariable("{name}", "{value}", "Machine")'
                    ]
                else:
                    # Use setx for user-level
                    cmd = ['setx', name, value]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )
                scope = "System" if system_level else "User"
                self.log(f"✓ Environment variable '{name}' set ({scope} level)")

                # Also set in current process
                os.environ[name] = value

            else:
                # Linux/macOS: Append to shell config
                shell = os.environ.get('SHELL', '')

                if 'bash' in shell:
                    config_file = Path.home() / '.bashrc'
                elif 'zsh' in shell:
                    config_file = Path.home() / '.zshrc'
                else:
                    config_file = Path.home() / '.profile'

                if system_level:
                    config_file = Path('/etc/environment')
                    if not self.is_admin():
                        self.log("⚠ System-level environment variable requires root privileges", "WARNING")
                        self.log("  Setting at user level instead...", "WARNING")
                        config_file = Path.home() / '.profile'
                        system_level = False

                # Check if variable already exists in file
                export_line = f'export {name}="{value}"'
                file_exists = config_file.exists()

                if file_exists:
                    with config_file.open('r') as f:
                        content = f.read()
                        # Check if variable is already set
                        if f'export {name}=' in content:
                            # Update existing line
                            lines = content.split('\n')
                            updated = False
                            for i, line in enumerate(lines):
                                if line.startswith(f'export {name}='):
                                    lines[i] = export_line
                                    updated = True
                                    break
                            if updated:
                                with config_file.open('w') as f:
                                    f.write('\n'.join(lines))
                            self.log(f"✓ Environment variable '{name}' updated in {config_file}")
                        else:
                            # Append new variable
                            with config_file.open('a') as f:
                                f.write(f'\n{export_line}\n')
                            self.log(f"✓ Environment variable '{name}' added to {config_file}")
                else:
                    # Create new file
                    with config_file.open('w') as f:
                        f.write(f'{export_line}\n')
                    self.log(f"✓ Environment variable '{name}' added to {config_file}")

                # Set in current process
                os.environ[name] = value

            return True

        except subprocess.CalledProcessError as e:
            self.log(f"✗ Error setting environment variable '{name}': {e.stderr}", "ERROR")
            return False
        except PermissionError:
            level = "system" if system_level else "user"
            self.log(f"✗ Permission denied: Cannot set '{name}' at {level} level", "ERROR")
            return False
        except Exception as e:
            self.log(f"✗ Unexpected error setting environment variable '{name}': {str(e)}", "ERROR")
            return False

    @staticmethod
    def prompt_user_action() -> int:
        """
        Prompt user for action when existing installation is found.

        Returns:
            1 for install/resume, 2 for cancel
        """
        print("\n" + "=" * 60)
        print("EXISTING COMFYUI INSTALLATION DETECTED")
        print("=" * 60)
        print("An existing ComfyUI installation was found.")
        print("\nHow would you like to proceed?")
        print("  1. Install or resume install into existing ComfyUI")
        print("  2. Cancel installation")
        print("=" * 60)

        while True:
            try:
                choice = input("\nEnter your choice (1 or 2): ").strip()
                if choice in ['1', '2']:
                    return int(choice)
                else:
                    print("Invalid choice. Please enter 1 or 2.")
            except (KeyboardInterrupt, EOFError):
                print("\n\nCancelled by user.")
                return 2


if __name__ == "__main__":
    """Test the ComfyUI installer."""
    installer = ComfyUIInstaller()

    print("ComfyUI Installation Info:")
    print("-" * 40)
    info = installer.get_installation_info()
    for key, value in info.items():
        print(f"{key}: {value}")

    if not info['installed']:
        print("\n" + "=" * 40)
        print("ComfyUI not found. Install? (y/n): ", end="")
        response = input().strip().lower()
        if response == 'y':
            success, message = installer.install_comfyui()
            print(message)
