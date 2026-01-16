# core/manifest_handler.py
import os
import sys
import json
import yaml
import hashlib
import shutil
import subprocess
import requests
import uuid  
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from huggingface_hub import hf_hub_download, HfApi
from tqdm import tqdm
import time


class ManifestHandler:
    """Handles manifest-based installation of ComfyUI resources."""

    SUPPORTED_SOURCES = ['bundled', 'huggingface', 'git', 'url', 'local', 'pip', 'install_temp', 'winget']
    SUPPORTED_TYPES = ['model', 'custom_node', 'file', 'directory', 'pip_package', 'config', 'application']
    SUPPORTED_PATH_BASES = ['comfyui', 'home', 'temp', 'appdata', 'absolute', 'install_temp']

    def __init__(self, manifest_path: Path, comfy_path: Path, log_file: Optional[Path] = None,
                 max_workers: int = 4, resume_downloads: bool = True, python_executable: Optional[Path] = None,
                 install_temp_path: Optional[Path] = None, hf_token: Optional[str] = None, log_callback=None):
        """
        Initialize ManifestHandler.

        Args:
            manifest_path: Path to manifest file (YAML or JSON)
            comfy_path: Path to ComfyUI installation
            log_file: Optional path to log file
            max_workers: Number of parallel download workers (default: 4)
            resume_downloads: Enable resume capability for interrupted downloads (default: True)
            python_executable: Optional path to Python executable for pip installs (default: sys.executable)
            install_temp_path: Optional path to InstallTemp folder from ZIP package
            hf_token: Optional HuggingFace token for gated models (overrides HF_TOKEN env var)
            log_callback: Optional callback function for log messages (for GUI integration)
        """
        self.manifest_path = Path(manifest_path)
        self.comfy_path = Path(comfy_path)
        self.log_file = log_file
        self.log_callback = log_callback
        self.manifest = None
        # Use provided token, or fall back to environment variable
        self.hf_token = hf_token or os.getenv('HF_TOKEN')
        self.max_workers = max_workers
        self.resume_downloads = resume_downloads
        self.python_executable = Path(python_executable) if python_executable else Path(sys.executable)
        self.partial_download_dir = self.comfy_path / ".partial_downloads"
        self.install_temp_path = Path(install_temp_path) if install_temp_path else None
        
        # Track what was actually downloaded vs skipped
        self.downloaded_items = []
        self.skipped_items = []

        # Git executable path (cached after first check)
        self._git_executable = None
        self._git_checked = False

        # Cache for file status to verify checksums only once
        self._file_status_cache = None

        # Create partial download directory if resume is enabled
        if self.resume_downloads:
            self.partial_download_dir.mkdir(parents=True, exist_ok=True)
        
    def log(self, message: str, level: str = "INFO"):
        """Log message to console and file with timestamp."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] [{level}] {message}"
        print(formatted_message)
        if self.log_file:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(formatted_message + '\n')

        # Call GUI callback if provided
        if self.log_callback:
            self.log_callback(message)

    def has_gated_models(self) -> bool:
        """
        Check if manifest contains any gated models from HuggingFace.

        Returns:
            True if manifest contains gated models, False otherwise
        """
        if not self.manifest:
            return False

        for item in self.manifest.get('resources', []):
            if item.get('source') == 'huggingface' and item.get('gated', False):
                return True
        return False

    def set_hf_token(self, token: str):
        """
        Set HuggingFace token for accessing gated models.

        Args:
            token: HuggingFace access token
        """
        self.hf_token = token.strip() if token else None

    def _ensure_git_available(self) -> str:
        """
        Ensure git is available, installing it if necessary.

        Returns:
            Path to git executable as string

        Raises:
            RuntimeError: If git cannot be found or installed
        """
        if self._git_checked and self._git_executable:
            return self._git_executable

        # Try to find git in PATH first
        try:
            result = subprocess.run(['git', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self._git_executable = 'git'
                self._git_checked = True
                return self._git_executable
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Try common installation locations on Windows
        if sys.platform == 'win32':
            common_paths = [
                r"C:\Program Files\Git\bin\git.exe",
                r"C:\Program Files (x86)\Git\bin\git.exe",
                Path.home() / "AppData" / "Local" / "Programs" / "Git" / "bin" / "git.exe",
            ]

            for git_path in common_paths:
                if Path(git_path).exists():
                    try:
                        result = subprocess.run([str(git_path), '--version'], capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            self._git_executable = str(git_path)
                            self._git_checked = True
                            # Add to current process PATH
                            git_bin_dir = str(Path(git_path).parent)
                            if git_bin_dir not in os.environ['PATH']:
                                os.environ['PATH'] = git_bin_dir + os.pathsep + os.environ['PATH']
                            self.log(f"✓ Found git at: {git_path}")
                            return self._git_executable
                    except (subprocess.TimeoutExpired, Exception):
                        continue

        # Git not found - try to install it via winget on Windows
        if sys.platform == 'win32':
            self.log("✗ Git not found - attempting to install via winget...")
            try:
                # Install Git via winget
                result = subprocess.run(
                    ['winget', 'install', '--id', 'Git.Git', '--source', 'winget', '--silent', '--accept-package-agreements', '--accept-source-agreements'],
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )

                if result.returncode == 0 or 'already installed' in result.stdout.lower():
                    self.log("✓ Git installed successfully")

                    # Try to find git again after installation
                    time.sleep(2)  # Give it a moment to finalize

                    for git_path in common_paths:
                        if Path(git_path).exists():
                            try:
                                result = subprocess.run([str(git_path), '--version'], capture_output=True, text=True, timeout=5)
                                if result.returncode == 0:
                                    self._git_executable = str(git_path)
                                    self._git_checked = True
                                    # Add to current process PATH
                                    git_bin_dir = str(Path(git_path).parent)
                                    if git_bin_dir not in os.environ['PATH']:
                                        os.environ['PATH'] = git_bin_dir + os.pathsep + os.environ['PATH']
                                    self.log(f"✓ Git ready at: {git_path}")

                                    # Also install Git LFS if needed
                                    self._ensure_git_lfs_available()

                                    return self._git_executable
                            except Exception:
                                continue

                    # If still not found, it might need a PATH refresh
                    raise RuntimeError(
                        "Git was installed but not found. Please restart the installer or add Git to your PATH manually."
                    )
                else:
                    error_msg = result.stderr if result.stderr else result.stdout
                    raise RuntimeError(f"Failed to install Git via winget: {error_msg}")

            except FileNotFoundError:
                raise RuntimeError(
                    "Git not found and winget is not available. Please install Git manually from https://git-scm.com/downloads"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to install Git: {e}")

        # Non-Windows platforms
        self._git_checked = True
        raise RuntimeError(
            "Git not found. Please install Git:\n"
            "  - Windows: https://git-scm.com/downloads\n"
            "  - Linux: sudo apt install git (Ubuntu/Debian) or sudo yum install git (RedHat/CentOS)\n"
            "  - Mac: brew install git"
        )

    def _ensure_git_lfs_available(self):
        """
        Ensure Git LFS is available, installing it if necessary.
        Only called after git is confirmed to be available.
        """
        try:
            # Check if git lfs is already installed
            result = subprocess.run(
                [self._git_executable, 'lfs', 'version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                self.log("✓ Git LFS already installed")
                return
        except Exception:
            pass

        # Try to install Git LFS on Windows via winget
        if sys.platform == 'win32':
            self.log("Installing Git LFS...")
            try:
                result = subprocess.run(
                    ['winget', 'install', '--id', 'GitHub.GitLFS', '--source', 'winget', '--silent', '--accept-package-agreements', '--accept-source-agreements'],
                    capture_output=True,
                    text=True,
                    timeout=120
                )

                if result.returncode == 0 or 'already installed' in result.stdout.lower():
                    # Initialize git lfs
                    subprocess.run([self._git_executable, 'lfs', 'install'], capture_output=True, timeout=10)
                    self.log("✓ Git LFS installed and initialized")
                else:
                    self.log("⚠ Git LFS installation failed - large files may not download correctly", "WARNING")
            except Exception as e:
                self.log(f"⚠ Could not install Git LFS: {e}", "WARNING")

    def resolve_path_base(self, path_base: str) -> Path:
        """
        Resolve base path for different path_base types.

        Args:
            path_base: Type of base path (comfyui, home, temp, appdata, absolute, install_temp)

        Returns:
            Resolved base path
        """
        if path_base == 'comfyui':
            return self.comfy_path
        elif path_base == 'home':
            return Path.home()
        elif path_base == 'temp':
            if sys.platform == 'win32':
                return Path(os.getenv('TEMP', os.path.expanduser('~/temp')))
            else:
                return Path(os.getenv('TMPDIR', '/tmp'))
        elif path_base == 'appdata':
            if sys.platform == 'win32':
                return Path(os.getenv('APPDATA', os.path.expanduser('~/AppData/Roaming')))
            elif sys.platform == 'darwin':
                return Path.home() / 'Library' / 'Application Support'
            else:  # Linux
                return Path.home() / '.local' / 'share'
        elif path_base == 'absolute':
            return Path('/')  # Will be replaced by absolute path in item
        elif path_base == 'install_temp':
            if self.install_temp_path and self.install_temp_path.exists():
                return self.install_temp_path
            else:
                self.log(f"⚠ InstallTemp path not available, defaulting to comfyui", "WARNING")
                return self.comfy_path
        else:
            self.log(f"⚠ Unknown path_base: {path_base}, defaulting to comfyui", "WARNING")
            return self.comfy_path

    def resolve_item_path(self, item: Dict) -> Path:
        """
        Resolve full path for an item based on its path and path_base.

        Args:
            item: Manifest item dictionary

        Returns:
            Resolved absolute path
        """
        if 'path' not in item:
            return None

        path_base = item.get('path_base', 'comfyui')
        item_path = item['path']

        if path_base == 'absolute':
            # For absolute paths, use the path directly
            return Path(item_path)
        else:
            # Resolve base and join with relative path
            base_path = self.resolve_path_base(path_base)
            return base_path / item_path

    def load_manifest(self) -> Dict:
        """Load and validate manifest file."""
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {self.manifest_path}")
        
        # Support both JSON and YAML
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            if self.manifest_path.suffix in ['.yaml', '.yml']:
                self.manifest = yaml.safe_load(f)
            else:
                self.manifest = json.load(f)
        
        package_name = self.manifest.get('package', {}).get('name', 'unknown')
        self.log(f"Loaded manifest: {package_name}")
        return self.manifest
    
    def validate_manifest(self) -> bool:
        """Basic manifest validation."""
        if not self.manifest:
            raise ValueError("Manifest not loaded")

        required_keys = ['package', 'items']
        for key in required_keys:
            if key not in self.manifest:
                raise ValueError(f"Manifest missing required key: {key}")

        # Validate items
        for item in self.manifest['items']:
            if 'name' not in item or 'type' not in item or 'source' not in item:
                raise ValueError(f"Item missing required fields: {item}")

            if item['type'] not in self.SUPPORTED_TYPES:
                raise ValueError(f"Unsupported item type: {item['type']}")

            if item['source'] not in self.SUPPORTED_SOURCES:
                raise ValueError(f"Unsupported source: {item['source']}")

            # Validate path_base if specified
            if 'path_base' in item:
                if item['path_base'] not in self.SUPPORTED_PATH_BASES:
                    raise ValueError(f"Unsupported path_base '{item['path_base']}' for item '{item['name']}'")

        self.log("Manifest validation passed")
        return True

    def ensure_prerequisites(self):
        """
        Ensure required tools (git, git-lfs) are available before starting downloads.
        Only checks/installs if manifest contains items requiring those tools.
        """
        if not self.manifest:
            return

        # Check if manifest contains any git sources
        has_git_sources = any(item.get('source') == 'git' for item in self.manifest.get('items', []))

        if has_git_sources:
            self.log("Checking git availability...")
            try:
                self._ensure_git_available()
                self.log("✓ Git is ready")
            except RuntimeError as e:
                self.log(f"✗ Git setup failed: {e}", "ERROR")
                raise

    def check_existing_files(self, force_recheck: bool = False) -> Dict[str, Dict]:
        """
        Check which files already exist and their status.
        Uses internal cache to prevent double-verification unless force_recheck is True.
        """
        if self._file_status_cache is not None and not force_recheck:
            return self._file_status_cache

        existing = {}
        for item in self.manifest['items']:
            if item['source'] == 'bundled':
                continue

            # Handle pip packages and winget applications (no file path)
            if item['source'] in ['pip', 'winget']:
                existing[item['name']] = {
                    'exists': False,
                    'valid': False,
                    'needs_download': True,
                    'reason': f"{item['source']}_package",
                    'partial_exists': False,
                    'partial_size': 0
                }
                continue

            # Skip items without a path
            if 'path' not in item:
                self.log(f"⚠ Item {item['name']} has no path, skipping check", "WARNING")
                continue

            path = self.resolve_item_path(item)
            
            status = {
                'exists': False,
                'valid': False,
                'needs_download': True,
                'reason': None,
                'partial_exists': False,
                'partial_size': 0
            }
            
            # Check for partial downloads
            if self.resume_downloads:
                partial_path = self._get_partial_path(item['path'])
                if partial_path.exists():
                    status['partial_exists'] = True
                    status['partial_size'] = partial_path.stat().st_size
            
            if path.exists():
                status['exists'] = True

                # Install_temp sources should always be copied (they're bundled and authoritative)
                if item['source'] == 'install_temp':
                    status['valid'] = False
                    status['needs_download'] = True
                    status['reason'] = 'install_temp_always_copy'
                    self.log(f"⊘ {item['name']} will be copied from package")
                # Verify checksum if provided (support both 'sha256' and 'sha')
                elif item.get('sha256') or item.get('sha'):
                    checksum = item.get('sha256') or item.get('sha')
                    if self._verify_checksum(path, checksum):
                        status['valid'] = True
                        status['needs_download'] = False
                        status['reason'] = 'exists_and_valid'
                        self.log(f"✓ {item['name']} exists and checksum matches")
                    else:
                        status['valid'] = False
                        status['needs_download'] = True
                        status['reason'] = 'checksum_mismatch'
                        self.log(f"⚠ {item['name']} exists but checksum mismatch - will re-download", "WARNING")
                else:
                    # No checksum provided - trust existing file
                    status['valid'] = True
                    status['needs_download'] = False
                    status['reason'] = 'exists_no_checksum'
                    self.log(f"✓ {item['name']} exists (no checksum to verify)")
            else:
                status['exists'] = False
                status['valid'] = False
                status['needs_download'] = True
                status['reason'] = 'missing'

                # Use different message for install_temp sources
                if item['source'] == 'install_temp':
                    self.log(f"⊘ {item['name']} will be copied from package")
                else:
                    resume_msg = f" (partial: {status['partial_size'] / 1024 / 1024:.1f}MB)" if status['partial_exists'] else ""
                    self.log(f"⊘ {item['name']} not found - will download{resume_msg}")
            
            existing[item['name']] = status
        
        self._file_status_cache = existing
        return existing
    
    def download_items(self, skip_existing: bool = True, required_only: bool = False, 
                      verify_checksums: bool = True, dry_run: bool = False, parallel: bool = True):
        """
        Download all items from manifest.
        
        Args:
            skip_existing: Skip files that already exist with valid checksums
            required_only: Only download items marked as required
            verify_checksums: Verify SHA256 checksums after download
            dry_run: Preview actions without executing downloads
            parallel: Use parallel downloads for improved speed
        """
        items_to_download = self.manifest['items']
        
        if required_only:
            items_to_download = [i for i in items_to_download if i.get('required', False)]
        
        # This will use the cache populated during print_summary()
        existing = self.check_existing_files() if skip_existing else {}
        
        # Filter items that need downloading
        download_list = []
        for item in items_to_download:
            # Skip bundled items
            if item['source'] == 'bundled':
                continue
            
            # Check if we should skip this file
            if skip_existing and item['name'] in existing:
                file_status = existing[item['name']]
                if not file_status['needs_download']:
                    self.log(f"⊘ Skipping {item['name']} ({file_status['reason']})")
                    continue
                elif file_status['reason'] == 'checksum_mismatch':
                    self.log(f"⚠ Re-downloading {item['name']} due to checksum mismatch", "WARNING")
            
            # Check for gated models (simple pre-check, logic handled in download)
            if item.get('gated', False) and not self.hf_token:
                # We log warning here but let it proceed to download so exception can be caught by manifest_integration
                self.log(f"⚠ {item['name']} is gated and no token set - may fail", "WARNING")
            
            download_list.append((item, existing.get(item['name'], {})))
        
        if dry_run:
            self.log("\n" + "=" * 60)
            self.log("DRY RUN MODE - No downloads will be performed")
            self.log("=" * 60)
            for item, status in download_list:
                source_info = self._get_source_info(item)
                self.log(f"Would download: {item['name']}")
                self.log(f"  Source: {source_info}")
                self.log(f"  Destination: {item['path']}")
                if status.get('partial_exists'):
                    self.log(f"  Resume from: {status['partial_size'] / 1024 / 1024:.1f}MB")
            self.log("=" * 60 + "\n")
            return
        
        # Download items
        if parallel and len(download_list) > 1:
            self._download_parallel(download_list, verify_checksums)
        else:
            self._download_sequential(download_list, verify_checksums)
    
    def _download_sequential(self, download_list: List[Tuple[Dict, Dict]], verify_checksums: bool):
        """Download items sequentially."""
        for item, status in download_list:
            try:
                self._download_item(item, verify_checksums)
            except Exception as e:
                # Allow critical authentication errors to bubble up
                if "401" in str(e) or "403" in str(e) or "HF_TOKEN" in str(e):
                    raise
                
                if item.get('required', False):
                    raise Exception(f"Failed to download required item {item['name']}: {e}")
                else:
                    self.log(f"⚠ Failed to download optional item {item['name']}: {e}", "WARNING")
    
    def _download_parallel(self, download_list: List[Tuple[Dict, Dict]], verify_checksums: bool):
        """Download items in parallel using ThreadPoolExecutor."""
        self.log(f"Starting parallel downloads with {self.max_workers} workers...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all download tasks
            future_to_item = {
                executor.submit(self._download_item, item, verify_checksums): item
                for item, status in download_list
            }
            
            # Process completed downloads
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    future.result()
                except Exception as e:
                    # Allow critical authentication errors to bubble up
                    if "401" in str(e) or "403" in str(e) or "HF_TOKEN" in str(e):
                        # Cancel remaining and raise
                        executor.shutdown(wait=False, cancel_futures=True)
                        raise
                        
                    if item.get('required', False):
                        # Cancel remaining downloads and raise
                        executor.shutdown(wait=False, cancel_futures=True)
                        raise Exception(f"Failed to download required item {item['name']}: {e}")
                    else:
                        self.log(f"⚠ Failed to download optional item {item['name']}: {e}", "WARNING")
    
    def _download_item(self, item: Dict, verify_checksum: bool = True):
        """
        Download a single item based on its source type.

        Note: Checksum verification is only performed for items with type='model'.
        """
        # Only verify checksums for model types
        should_verify = verify_checksum and item.get('type') == 'model'

        if item['source'] == 'huggingface':
            self._download_from_huggingface(item, verify_checksum=should_verify)
        elif item['source'] == 'git':
            self._download_from_git(item)
        elif item['source'] == 'url':
            self._download_from_url(item, verify_checksum=should_verify)
        elif item['source'] == 'local':
            self._copy_from_local(item)
        elif item['source'] == 'pip':
            self._install_pip_package(item)
        elif item['source'] == 'install_temp':
            # Route pip_package types to pip installer, others to copy
            if item.get('type') == 'pip_package':
                self._install_pip_package(item)
            else:
                self._copy_from_install_temp(item)
        elif item['source'] == 'winget':
            self._download_from_winget(item)
        else:
            self.log(f"⚠ Unknown source type: {item['source']}", "WARNING")
    
    def _get_source_info(self, item: Dict) -> str:
        """Get human-readable source information."""
        if item['source'] == 'huggingface':
            return f"HuggingFace: {item['repo']}/{item['file']}"
        elif item['source'] == 'git':
            return f"Git: {item['url']} (ref: {item.get('ref', 'main')})"
        elif item['source'] == 'url':
            return f"URL: {item['url']}"
        elif item['source'] == 'local':
            return f"Local: {item.get('source_path', 'unknown')}"
        elif item['source'] == 'pip':
            return f"PyPI: {item.get('package', item['name'])}"
        elif item['source'] == 'install_temp':
            return f"InstallTemp: {item.get('source_path', 'unknown')}"
        elif item['source'] == 'winget':
            return f"Winget: {item.get('package_id', 'unknown')}"
        return item['source']
    
    def _get_partial_path(self, target_path: str) -> Path:
        """Get path for partial download file."""
        safe_name = str(target_path).replace('/', '_').replace('\\', '_')
        return self.partial_download_dir / f"{safe_name}.partial"
    
    def _download_from_huggingface(self, item: Dict, verify_checksum: bool = True):
        """Download from Hugging Face Hub with temp directory cleanup."""
        self.log(f"↓ Downloading {item['name']} from Hugging Face...")

        repo_id = item['repo']
        filename = item['file']
        local_path = self.resolve_item_path(item)
        partial_path = self._get_partial_path(item['path'])
        
        # Parse remote_path to get subfolder if provided
        subfolder = None
        if 'remote_path' in item:
            remote_path = item['remote_path']
            if '/tree/' in remote_path:
                parts = remote_path.split('/tree/')
                if len(parts) > 1:
                    branch_and_path = parts[1].split('/', 1)
                    if len(branch_and_path) > 1:
                        subfolder = branch_and_path[1]
                        self.log(f"  Using subfolder: {subfolder}")
        
        # Build the full filename path in the repo
        repo_filename = f"{subfolder}/{filename}" if subfolder else filename
        
        # Create parent directory for final destination
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # === FIX FOR DIRECTORY CLUTTER ===
        # Create a temp directory inside the parent folder to contain HF cache/structure
        temp_dir_name = f".tmp_hf_{uuid.uuid4().hex[:8]}"
        temp_download_dir = local_path.parent / temp_dir_name
        temp_download_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Check for remote SHA256 (optional metadata check)
            remote_checksum = None
            try:
                api = HfApi(token=self.hf_token)
                file_metadata = api.get_paths_info(repo_id, paths=[repo_filename], repo_type="model")
                if file_metadata and len(file_metadata) > 0:
                    remote_checksum = file_metadata[0].lfs.get('sha256') if hasattr(file_metadata[0], 'lfs') else None
            except Exception:
                pass
            
            manifest_checksum = item.get('sha256') or item.get('sha')
            checksum_to_verify = manifest_checksum or remote_checksum
            
            # Download with progress bar to TEMP dir
            downloaded_path = hf_hub_download(
                repo_id=repo_id,
                filename=repo_filename,
                local_dir=temp_download_dir, # Download into temp dir
                token=self.hf_token,
                force_download=not self.resume_downloads 
            )
            
            # Move the actual file to the correct location
            # This extracts just the file we want from the messy HF structure
            if Path(downloaded_path).exists():
                shutil.move(str(downloaded_path), str(local_path))
            else:
                raise FileNotFoundError(f"Download failed, file not found at {downloaded_path}")
            
        except Exception as e:
            self.log(f"✗ Download failed: {e}", "ERROR")
            raise
        
        finally:
            # CLEANUP: Remove the temporary directory and all HF artifacts
            if temp_download_dir.exists():
                try:
                    shutil.rmtree(temp_download_dir, ignore_errors=True)
                except Exception:
                    pass
        
        # Verify checksum of final file
        if verify_checksum and checksum_to_verify:
            self.log(f"  Verifying checksum...")
            if self._verify_checksum(local_path, checksum_to_verify):
                self.log(f"✓ {item['name']} downloaded and verified")
                
                # Warn if manifest checksum doesn't match remote
                if manifest_checksum and remote_checksum and manifest_checksum != remote_checksum:
                    self.log(f"  ⚠ WARNING: Manifest SHA256 differs from remote!", "WARNING")
                    self.log(f"    Manifest: {manifest_checksum[:16]}...")
                    self.log(f"    Remote:   {remote_checksum[:16]}...")
                
                # Clean up partial file
                if partial_path.exists():
                    partial_path.unlink()
            else:
                raise Exception(f"Checksum mismatch for {item['name']}")
        else:
            self.log(f"✓ {item['name']} downloaded (no checksum verification)")
    
    def _download_from_git(self, item: Dict) -> bool:
        """
        Clone from Git repository or update existing clone.
        """
        url = item['url']
        ref = item.get('ref', 'main')
        local_path = self.resolve_item_path(item)
        
        # Case 1: Directory doesn't exist - fresh clone
        if not local_path.exists():
            self.log(f"↓ Cloning {item['name']} from Git...")
            return self._git_clone_fresh(item, url, ref, local_path)
        
        # Case 2: Directory exists but is not a Git repo - delete and clone
        if not (local_path / '.git').exists():
            self.log(f"↓ Cloning {item['name']} from Git...")
            self.log(f"  Removing non-git directory...")
            self._remove_directory_safely(local_path)
            return self._git_clone_fresh(item, url, ref, local_path)
        
        # Case 3: It's a Git repo - check if already at correct version
        self.log(f"↓ Checking {item['name']}...")
        
        try:
            # Get local commit
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=local_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            local_commit = result.stdout.strip()
            
            # Get remote commit for ref
            result = subprocess.run(
                ['git', 'ls-remote', url, ref],
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            
            if result.stdout:
                remote_commit = result.stdout.split()[0]
                
                # Already at correct version - skip
                if local_commit == remote_commit:
                    self.log(f"⊘ Skipping {item['name']} (already at {ref})")
                    self.skipped_items.append(item)
                    return False
                
                # Different version - update needed
                self.log(f"  Updating {item['name']} from {local_commit[:8]} to {remote_commit[:8]}...")
                return self._git_update_existing(item, url, ref, local_path)
            else:
                # Ref doesn't exist remotely - try to clone fresh
                self.log(f"  Ref {ref} not found on remote, re-cloning...", "WARNING")
                self._remove_directory_safely(local_path)
                return self._git_clone_fresh(item, url, ref, local_path)
                
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, IndexError) as e:
            # Git commands failed - try to update anyway
            self.log(f"  Could not verify version ({e}), attempting update...", "WARNING")
            return self._git_update_existing(item, url, ref, local_path)
    
    def _git_update_existing(self, item: Dict, url: str, ref: str, local_path: Path) -> bool:
        """
        Update existing Git repository using fetch + checkout + reset.
        """
        try:
            # Fetch latest from remote
            self.log(f"  Fetching updates...")
            subprocess.run(
                ['git', 'fetch', 'origin'],
                cwd=local_path,
                check=True,
                capture_output=True,
                timeout=60
            )
            
            # Checkout the ref
            self.log(f"  Checking out {ref}...")
            subprocess.run(
                ['git', 'checkout', ref],
                cwd=local_path,
                check=True,
                capture_output=True,
                timeout=30
            )
            
            # Reset to match remote exactly
            try:
                subprocess.run(
                    ['git', 'reset', '--hard', f'origin/{ref}'],
                    cwd=local_path,
                    check=True,
                    capture_output=True,
                    timeout=30
                )
            except subprocess.CalledProcessError:
                # origin/{ref} might not work for tags/commits, try without origin/
                subprocess.run(
                    ['git', 'reset', '--hard', ref],
                    cwd=local_path,
                    check=True,
                    capture_output=True,
                    timeout=30
                )
            
            self.log(f"✓ {item['name']} updated")
            self.downloaded_items.append(item)
            
            # Install requirements if specified
            self._install_requirements_if_needed(item, local_path)
            
            return True
            
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            # Update failed - fall back to fresh clone
            self.log(f"  Git update failed, re-cloning...", "WARNING")
            self._remove_directory_safely(local_path)
            return self._git_clone_fresh(item, url, ref, local_path)
    
    def _git_clone_fresh(self, item: Dict, url: str, ref: str, local_path: Path) -> bool:
        """
        Perform a fresh git clone.
        """
        # Ensure git is available
        git_cmd = self._ensure_git_available()

        # Ensure parent directory exists
        local_path.parent.mkdir(parents=True, exist_ok=True)

        self.log(f"  Cloning from {url} (ref: {ref})...")
        self.log(f"  Target path: {local_path}")

        try:
            result = subprocess.run([
                git_cmd, 'clone', '--depth', '1',
                '--branch', ref,
                '--progress',
                url, str(local_path)
            ], check=True, capture_output=True, text=True)
        except FileNotFoundError:
            self.log(f"✗ Git executable not found", "ERROR")
            self.log(f"  Please ensure git is installed and in your PATH", "ERROR")
            self.log(f"  Download from: https://git-scm.com/downloads", "ERROR")
            raise
        except subprocess.CalledProcessError as e:
            error_output = e.stderr if e.stderr else e.stdout if e.stdout else str(e)
            self.log(f"✗ Git clone failed: {error_output}", "ERROR")

            # If branch-specific clone fails, try without --branch to use default branch
            if ref == 'main' or ref == 'master':
                self.log(f"  Branch '{ref}' not found, trying default branch...", "WARNING")
                try:
                    result = subprocess.run([
                        git_cmd, 'clone', '--depth', '1',
                        '--progress',
                        url, str(local_path)
                    ], check=True, capture_output=True, text=True)
                    self.log(f"✓ {item['name']} cloned using default branch")
                except FileNotFoundError:
                    self.log(f"✗ Git executable not found", "ERROR")
                    self.log(f"  Please ensure git is installed and in your PATH", "ERROR")
                    raise
                except subprocess.CalledProcessError as e2:
                    error_output2 = e2.stderr if e2.stderr else e2.stdout if e2.stdout else str(e2)
                    self.log(f"✗ Git clone failed: {error_output2}", "ERROR")
                    self.log(f"  Possible reasons:", "ERROR")
                    self.log(f"    - Repository doesn't exist or was renamed", "ERROR")
                    self.log(f"    - Network connectivity issue", "ERROR")
                    self.log(f"    - Repository is private (requires authentication)", "ERROR")
                    self.log(f"    - Path too long (enable Windows long paths)", "ERROR")
                    raise
            else:
                self.log(f"  Possible reasons:", "ERROR")
                self.log(f"    - Branch '{ref}' doesn't exist", "ERROR")
                self.log(f"    - Repository doesn't exist or was renamed", "ERROR")
                self.log(f"    - Network connectivity issue", "ERROR")
                self.log(f"    - Path too long (enable Windows long paths)", "ERROR")
                raise

        self.log(f"✓ {item['name']} cloned")
        self.downloaded_items.append(item)

        # Install requirements if specified
        self._install_requirements_if_needed(item, local_path)

        return True
    
    def _remove_directory_safely(self, path: Path):
        """
        Safely remove a directory, handling Windows file locks and permissions.
        """
        try:
            shutil.rmtree(path)
        except (OSError, PermissionError) as e:
            # On Windows, files might be locked - try harder
            self.log(f"  Retrying removal with error handler...", "WARNING")
            import stat
            
            def handle_remove_readonly(func, path_to_remove, exc):
                """Error handler for Windows readonly files."""
                try:
                    os.chmod(path_to_remove, stat.S_IWRITE)
                    func(path_to_remove)
                except:
                    pass
            
            try:
                shutil.rmtree(path, onerror=handle_remove_readonly)
            except Exception as e2:
                # Last resort: rename to .backup
                self.log(f"  Could not remove, renaming to .backup...", "WARNING")
                backup_path = path.parent / f".backup_{path.name}_{uuid.uuid4().hex[:8]}"
                try:
                    if backup_path.exists():
                        shutil.rmtree(backup_path, ignore_errors=True)
                    os.rename(path, backup_path)
                    self.log(f"  Renamed to {backup_path.name}", "WARNING")
                except Exception as e3:
                    raise Exception(f"Cannot remove existing directory {path}: {e3}")
    
    def _run_pip_install_with_retry(self, pip_args: list, max_retries: int = 3, retry_delay: float = 2.0) -> subprocess.CompletedProcess:
        """
        Run pip install with retry logic for Windows file lock errors.

        Args:
            pip_args: List of pip arguments (e.g., ['install', '-r', 'requirements.txt'])
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds

        Returns:
            CompletedProcess instance

        Raises:
            subprocess.CalledProcessError: If all retries fail
        """
        base_cmd = [str(self.python_executable), '-m', 'pip'] + pip_args

        # Add flags to help with Windows embedded Python issues
        if '--no-warn-script-location' not in pip_args:
            base_cmd.append('--no-warn-script-location')

        last_error = None
        for attempt in range(max_retries):
            try:
                result = subprocess.run(base_cmd, check=True, capture_output=True, text=True)
                return result
            except subprocess.CalledProcessError as e:
                last_error = e
                error_msg = e.stderr if e.stderr else str(e)

                # Check if it's a Windows file lock error (WinError 32)
                if 'WinError 32' in error_msg or 'being used by another process' in error_msg:
                    if attempt < max_retries - 1:
                        self.log(f"  ⚠ File locked by another process, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})...", "WARNING")
                        time.sleep(retry_delay)
                        retry_delay *= 1.5  # Exponential backoff
                        continue
                    else:
                        self.log(f"  ✗ Failed after {max_retries} attempts due to file locks", "ERROR")
                        self.log(f"  Suggestion: Close any Python processes or restart your computer", "WARNING")
                else:
                    # Non-file-lock error, don't retry
                    break

        # All retries exhausted
        raise last_error

    def _install_requirements_if_needed(self, item: Dict, local_path: Path):
        """
        Install requirements.txt if specified in manifest item.
        """
        if item.get('install_requirements', False):
            req_file = local_path / 'requirements.txt'
            if req_file.exists():
                self.log(f"  Installing requirements for {item['name']}...")
                self.log(f"  Using Python: {self.python_executable}")
                try:
                    self._run_pip_install_with_retry(['install', '-r', str(req_file)])
                    self.log(f"  ✓ Requirements installed")
                except subprocess.CalledProcessError as e:
                    error_msg = e.stderr if e.stderr else str(e)
                    self.log(f"  ⚠ Requirements installation failed: {error_msg}", "WARNING")
                    if item.get('required', False):
                        raise
            else:
                self.log(f"  ⊘ No requirements.txt found for {item['name']}")
    
    def _download_from_url(self, item: Dict, verify_checksum: bool = True):
        """Download from direct URL with progress bar and resume capability."""
        self.log(f"↓ Downloading {item['name']} from URL...")

        url = item['url']
        local_path = self.resolve_item_path(item)
        partial_path = self._get_partial_path(item['path'])
        
        # Create parent directory
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check for partial download
        resume_header = {}
        initial_pos = 0
        if self.resume_downloads and partial_path.exists():
            initial_pos = partial_path.stat().st_size
            resume_header = {'Range': f'bytes={initial_pos}-'}
            self.log(f"  Resuming from {initial_pos / 1024 / 1024:.1f}MB")
        
        # Get file size
        try:
            head_response = requests.head(url, allow_redirects=True)
            total_size = int(head_response.headers.get('content-length', 0))
            supports_resume = head_response.headers.get('accept-ranges') == 'bytes'
        except Exception:
            total_size = 0
            supports_resume = False
        
        # Download with progress bar
        try:
            response = requests.get(url, stream=True, headers=resume_header if supports_resume else {})
            response.raise_for_status()
            
            # Open file in appropriate mode
            mode = 'ab' if self.resume_downloads and supports_resume and initial_pos > 0 else 'wb'
            temp_path = partial_path if self.resume_downloads else local_path
            
            chunk_size = 8192
            with open(temp_path, mode) as f:
                if total_size > 0:
                    with tqdm(total=total_size, initial=initial_pos, unit='B', unit_scale=True, 
                             desc=item['name'][:30], ncols=80) as pbar:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
                else:
                    # No size info, download without progress bar
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
            
            # Move partial to final location if using resume
            if self.resume_downloads and temp_path != local_path:
                shutil.move(temp_path, local_path)
        
        except Exception as e:
            self.log(f"✗ Download failed: {e}", "ERROR")
            raise
        
        # Make executable if specified
        if item.get('executable', False):
            local_path.chmod(0o755)
        
        # Verify checksum if provided
        if verify_checksum:
            manifest_checksum = item.get('sha256') or item.get('sha')
            if manifest_checksum:
                self.log(f"  Verifying checksum...")
                if self._verify_checksum(local_path, manifest_checksum):
                    self.log(f"✓ {item['name']} downloaded and verified")
                    # Clean up partial file
                    if partial_path.exists():
                        partial_path.unlink()
                else:
                    raise Exception(f"Checksum mismatch for {item['name']}")
            else:
                self.log(f"✓ {item['name']} downloaded (no checksum verification)")
        else:
            self.log(f"✓ {item['name']} downloaded")
    
    def _copy_from_local(self, item: Dict):
        """Copy from local path."""
        self.log(f"↓ Copying {item['name']} from local...")

        source = Path(item['source_path'])
        dest = self.resolve_item_path(item)

        if not source.exists():
            raise FileNotFoundError(f"Source path not found: {source}")

        dest.parent.mkdir(parents=True, exist_ok=True)

        if source.is_dir():
            # Copy directory with progress
            self.log(f"  Copying directory...")
            shutil.copytree(source, dest, dirs_exist_ok=True)
        else:
            # Copy file with progress
            file_size = source.stat().st_size
            if file_size > 10 * 1024 * 1024:  # Show progress for files > 10MB
                with tqdm(total=file_size, unit='B', unit_scale=True,
                         desc=item['name'][:30], ncols=80) as pbar:
                    with open(source, 'rb') as fsrc:
                        with open(dest, 'wb') as fdst:
                            while True:
                                buf = fsrc.read(8192)
                                if not buf:
                                    break
                                fdst.write(buf)
                                pbar.update(len(buf))
            else:
                shutil.copy2(source, dest)

        self.log(f"✓ {item['name']} copied")

    def _resolve_case_insensitive_path(self, base_path: Path, relative_path: str) -> Optional[Path]:
        """
        Resolve a path case-insensitively by walking the directory tree.

        This is needed because ZIP archives preserve exact case, but manifests
        might use different case (e.g., 'Wheels/' vs 'wheels/').

        Args:
            base_path: The base directory to search from
            relative_path: The relative path to resolve (e.g., "Wheels/file.whl")

        Returns:
            Resolved Path object if found, None otherwise
        """
        if not base_path.exists():
            return None

        # Split the path into components
        parts = Path(relative_path).parts
        current = base_path

        # Walk through each component and try to match case-insensitively
        for part in parts:
            part_lower = part.lower()
            found = False

            try:
                # List directory contents and match case-insensitively
                for item in current.iterdir():
                    if item.name.lower() == part_lower:
                        current = item
                        found = True
                        break
            except (PermissionError, OSError):
                return None

            if not found:
                return None

        return current

    def _copy_from_install_temp(self, item: Dict):
        """Copy from InstallTemp folder (bundled in ZIP package)."""
        if not self.install_temp_path or not self.install_temp_path.exists():
            raise FileNotFoundError(f"InstallTemp folder not available. Make sure the manifest is from a ZIP package with InstallTemp folder.")

        self.log(f"↓ Copying {item['name']} from InstallTemp...")

        # Resolve source path relative to InstallTemp folder
        source_relative = item['source_path']
        source = self.install_temp_path / source_relative
        dest = self.resolve_item_path(item)

        if not source.exists():
            # Try case-insensitive resolution (for ZIP case sensitivity issues)
            resolved_source = self._resolve_case_insensitive_path(self.install_temp_path, source_relative)
            if resolved_source and resolved_source.exists():
                source = resolved_source
                self.log(f"  (Resolved case-insensitive path: {source_relative} -> {source.relative_to(self.install_temp_path)})", "WARNING")
            else:
                raise FileNotFoundError(f"Source path not found in InstallTemp: {source}")

        dest.parent.mkdir(parents=True, exist_ok=True)

        if source.is_dir():
            # Copy directory with progress
            self.log(f"  Copying directory from InstallTemp...")
            shutil.copytree(source, dest, dirs_exist_ok=True)
        else:
            # Copy file with progress
            file_size = source.stat().st_size
            if file_size > 10 * 1024 * 1024:  # Show progress for files > 10MB
                with tqdm(total=file_size, unit='B', unit_scale=True,
                         desc=item['name'][:30], ncols=80) as pbar:
                    with open(source, 'rb') as fsrc:
                        with open(dest, 'wb') as fdst:
                            while True:
                                buf = fsrc.read(8192)
                                if not buf:
                                    break
                                fdst.write(buf)
                                pbar.update(len(buf))
            else:
                shutil.copy2(source, dest)

        self.log(f"✓ {item['name']} copied from InstallTemp")

    def _install_pip_package(self, item: Dict):
        """
        Install a Python package via pip.

        Supports:
        - PyPI packages: source="pip", package="numpy", version="1.24.0"
        - Local wheel files: source="pip", package="path/to/package.whl"
        - URLs: source="pip", package="https://example.com/package.whl"
        - InstallTemp wheels: source="install_temp", source_path="wheels/my_package.whl"
        """
        package_spec = item.get('package', item['name'])
        version = item.get('version')
        source_path = item.get('source_path')

        # Handle install_temp source for bundled wheel files
        if item.get('source') == 'install_temp':
            if not source_path:
                self.log(f"✗ source_path required for install_temp pip packages", "ERROR")
                if item.get('required', False):
                    raise ValueError(f"source_path required for install_temp source: {item['name']}")
                return

            if not self.install_temp_path:
                self.log(f"✗ InstallTemp folder not available", "ERROR")
                if item.get('required', False):
                    raise FileNotFoundError(f"InstallTemp folder not available for: {item['name']}")
                return

            wheel_path = self.install_temp_path / source_path
            if wheel_path.exists():
                package_spec = str(wheel_path.resolve())
                self.log(f"↓ Installing Python package from InstallTemp: {wheel_path.name}...")
            else:
                # Try case-insensitive resolution (for ZIP case sensitivity issues)
                resolved_path = self._resolve_case_insensitive_path(self.install_temp_path, source_path)
                if resolved_path and resolved_path.exists():
                    package_spec = str(resolved_path.resolve())
                    self.log(f"↓ Installing Python package from InstallTemp: {resolved_path.name}...")
                    self.log(f"  (Resolved case-insensitive path: {source_path} -> {resolved_path.relative_to(self.install_temp_path)})", "WARNING")
                else:
                    self.log(f"✗ Wheel file not found in InstallTemp: {source_path}", "ERROR")
                    if item.get('required', False):
                        raise FileNotFoundError(f"Wheel file not found: {source_path}")
                    return
        # Check if package_spec is a local file path
        elif package_spec.endswith('.whl') or package_spec.endswith('.tar.gz') or '/' in package_spec or '\\' in package_spec:
            # Could be a local path or URL
            if not package_spec.startswith(('http://', 'https://', 'git+')):
                # Local path - resolve it
                local_path = Path(package_spec)

                # Try absolute path first
                if local_path.is_absolute() and local_path.exists():
                    package_spec = str(local_path.resolve())
                else:
                    # Try relative to manifest location
                    manifest_dir = self.manifest_path.parent
                    relative_path = manifest_dir / package_spec
                    if relative_path.exists():
                        package_spec = str(relative_path.resolve())
                    elif not local_path.exists():
                        self.log(f"✗ Local package file not found: {package_spec}", "ERROR")
                        if item.get('required', False):
                            raise FileNotFoundError(f"Package file not found: {package_spec}")
                        return
                    else:
                        package_spec = str(local_path.resolve())

                self.log(f"↓ Installing Python package from local file: {Path(package_spec).name}...")
        else:
            # PyPI package - add version if specified
            if version:
                package_spec = f"{package_spec}=={version}"
            self.log(f"↓ Installing Python package from PyPI: {package_spec}...")

        self.log(f"  Using Python: {self.python_executable}")

        try:
            self._run_pip_install_with_retry(['install', package_spec])
            self.log(f"✓ {item['name']} installed via pip")
            self.downloaded_items.append(item)
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            self.log(f"✗ Pip install failed: {error_msg}", "ERROR")
            if item.get('required', False):
                raise
            else:
                self.log(f"⚠ Optional package {item['name']} failed to install", "WARNING")

    def _download_from_winget(self, item: Dict):
        """
        Install a package via Windows Package Manager (winget).

        Manifest fields:
        - package_id (required): The winget package ID (e.g., "Microsoft.VisualStudioCode")
        - silent (optional): Install silently, default True
        - accept_agreements (optional): Accept package/source agreements, default True
        - winget_source (optional): Specify winget source (e.g., "winget", "msstore"), default "winget"

        Example:
          - name: "Visual Studio Code"
            source: winget
            package_id: "Microsoft.VisualStudioCode"
            required: false
        """
        if sys.platform != 'win32':
            self.log(f"⚠ Winget installation skipped: {item['name']} (Windows-only)", "WARNING")
            if item.get('required', False):
                raise OSError(f"Winget source is only supported on Windows: {item['name']}")
            return

        package_id = item.get('package_id')
        if not package_id:
            self.log(f"✗ package_id required for winget source: {item['name']}", "ERROR")
            if item.get('required', False):
                raise ValueError(f"package_id required for winget source: {item['name']}")
            return

        self.log(f"↓ Installing {item['name']} via winget...")
        self.log(f"  Package ID: {package_id}")

        # Build winget command
        cmd = ['winget', 'install', '--id', package_id]

        # Add source if specified
        winget_source = item.get('winget_source', 'winget')
        cmd.extend(['--source', winget_source])

        # Add silent flag if requested (default True)
        if item.get('silent', True):
            cmd.append('--silent')

        # Accept agreements if requested (default True)
        if item.get('accept_agreements', True):
            cmd.extend(['--accept-package-agreements', '--accept-source-agreements'])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            if result.returncode == 0:
                self.log(f"✓ {item['name']} installed via winget")
                self.downloaded_items.append(item)
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                self.log(f"✗ Winget install failed: {error_msg}", "ERROR")
                if item.get('required', False):
                    raise subprocess.CalledProcessError(result.returncode, cmd, error_msg)
                else:
                    self.log(f"⚠ Optional package {item['name']} failed to install", "WARNING")

        except subprocess.TimeoutExpired:
            self.log(f"✗ Winget installation timed out: {item['name']}", "ERROR")
            if item.get('required', False):
                raise
        except FileNotFoundError:
            self.log(f"✗ winget not found. Please install App Installer from Microsoft Store", "ERROR")
            if item.get('required', False):
                raise
        except Exception as e:
            self.log(f"✗ Winget installation failed: {e}", "ERROR")
            if item.get('required', False):
                raise

    def _verify_checksum(self, file_path: Path, expected_sha256: str) -> bool:
        """Verify file SHA256 checksum with progress bar for large files."""
        if not file_path.exists():
            return False
        
        file_size = file_path.stat().st_size
        sha256_hash = hashlib.sha256()
        
        # Show progress for large files (> 100MB)
        if file_size > 100 * 1024 * 1024:
            with open(file_path, "rb") as f:
                with tqdm(total=file_size, unit='B', unit_scale=True, 
                         desc="Verifying", ncols=80) as pbar:
                    while True:
                        data = f.read(4096)
                        if not data:
                            break
                        sha256_hash.update(data)
                        pbar.update(len(data))
        else:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
        
        return sha256_hash.hexdigest() == expected_sha256
    
    def custom_nodes_were_downloaded(self) -> bool:
        """
        Check if any custom nodes were actually downloaded (not skipped).
        Returns True only if custom nodes were installed or updated.
        """
        for item in self.downloaded_items:
            # Check if item is marked as custom_node type
            if item.get('type') == 'custom_node':
                return True
            
            # Check if destination contains 'custom_nodes'
            dest_path = item.get('dest', '') or item.get('path', '')
            if 'custom_nodes' in dest_path.lower():
                return True
        
        return False
    
    def get_download_summary(self) -> Dict:
        """Get summary of downloads needed."""
        existing = self.check_existing_files()
        
        total_items = len(self.manifest['items'])
        bundled = sum(1 for i in self.manifest['items'] if i['source'] == 'bundled')
        to_download = sum(1 for name, status in existing.items() if status['needs_download'])
        already_exist = sum(1 for status in existing.values() if not status['needs_download'])
        partial_downloads = sum(1 for status in existing.values() if status.get('partial_exists', False))
        
        # Calculate total size from metadata or items
        metadata_size = self.manifest.get('metadata', {}).get('total_size_mb')
        if metadata_size:
            total_size = metadata_size
        else:
            total_size = sum(
                item.get('size_mb', 0)
                for item in self.manifest['items']
                if item['source'] != 'bundled' and existing.get(item['name'], {}).get('needs_download', False)
            )
        
        return {
            'total_items': total_items,
            'bundled': bundled,
            'to_download': to_download,
            'already_exist': already_exist,
            'partial_downloads': partial_downloads,
            'total_download_size_mb': total_size,
            'gated_models': [
                i['name'] for i in self.manifest['items']
                if i.get('gated', False) and existing.get(i['name'], {}).get('needs_download', False)
            ]
        }
    
    def print_summary(self):
        """Print download summary."""
        summary = self.get_download_summary()
        package = self.manifest.get('package', {})
        metadata = self.manifest.get('metadata', {})
        
        print("\n" + "=" * 60)
        print("MANIFEST DOWNLOAD SUMMARY")
        print("=" * 60)
        print(f"Package: {package.get('name', 'unknown')} v{package.get('version', '?')}")
        print(f"Description: {package.get('description', 'N/A')}")
        if metadata.get('details'):
            print(f"Details: {metadata['details']}")
        print(f"\nTotal items: {summary['total_items']}")
        print(f"  Bundled in ZIP: {summary['bundled']}")
        print(f"  Already exist: {summary['already_exist']}")
        print(f"  To download: {summary['to_download']}")
        if summary['partial_downloads'] > 0:
            print(f"  Partial downloads: {summary['partial_downloads']} (can be resumed)")
        print(f"Total download size: {summary['total_download_size_mb']:.1f} MB")
        if metadata.get('estimated_time'):
            print(f"Estimated time: {metadata['estimated_time']}")
        
        if summary['gated_models']:
            print(f"\n⚠ Gated models (require license acceptance):")
            for model in summary['gated_models']:
                print(f"  - {model}")
            if not self.hf_token:
                print("\n  Set HF_TOKEN environment variable to download gated models")
        
        if metadata.get('tags'):
            print(f"\nTags: {', '.join(metadata['tags'])}")
        
        print("=" * 60 + "\n")
    
    def cleanup_partial_downloads(self):
        """Clean up all partial download files."""
        if not self.partial_download_dir.exists():
            return
        
        partial_files = list(self.partial_download_dir.glob("*.partial"))
        if partial_files:
            self.log(f"Cleaning up {len(partial_files)} partial download(s)...")
            for partial_file in partial_files:
                partial_file.unlink()
            self.log("✓ Partial downloads cleaned up")
        else:
            self.log("No partial downloads to clean up")


# Example usage
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='ComfyUI Manifest Handler')
    parser.add_argument('manifest', type=Path, help='Path to manifest file (YAML or JSON)')
    parser.add_argument('--comfy-path', type=Path, default=Path('C:/ComfyUI'),
                       help='Path to ComfyUI installation (default: C:/ComfyUI)')
    parser.add_argument('--log-file', type=Path, help='Path to log file')
    parser.add_argument('--required-only', action='store_true',
                       help='Only download required items')
    parser.add_argument('--force', action='store_true',
                       help='Force re-download all files')
    parser.add_argument('--no-verify', action='store_true',
                       help='Skip checksum verification')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview actions without downloading')
    parser.add_argument('--sequential', action='store_true',
                       help='Disable parallel downloads')
    parser.add_argument('--workers', type=int, default=4,
                       help='Number of parallel download workers (default: 4)')
    parser.add_argument('--no-resume', action='store_true',
                       help='Disable resume capability for downloads')
    parser.add_argument('--cleanup', action='store_true',
                       help='Clean up partial download files and exit')
    
    args = parser.parse_args()
    
    # Initialize handler
    handler = ManifestHandler(
        manifest_path=args.manifest,
        comfy_path=args.comfy_path,
        log_file=args.log_file,
        max_workers=args.workers,
        resume_downloads=not args.no_resume
    )
    
    # Cleanup mode
    if args.cleanup:
        handler.cleanup_partial_downloads()
        sys.exit(0)
    
    # Load and validate
    handler.load_manifest()
    handler.validate_manifest()
    handler.print_summary()
    
    # Download items
    handler.download_items(
        skip_existing=not args.force,
        required_only=args.required_only,
        verify_checksums=not args.no_verify,
        dry_run=args.dry_run,
        parallel=not args.sequential
    )
    
    print("\n✓ All downloads completed!")