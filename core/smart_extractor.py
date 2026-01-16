# core/smart_extractor.py
import os
import shutil
import zipfile
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

try:
    import tomllib
    tomli = tomllib
except ImportError:
    import tomli


def _load_pyproject_toml(path: Path) -> Optional[Dict]:
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            return tomli.load(f)
    except Exception as e:
        print(f"[smart_extractor] Failed to parse {path}: {e}")
        return None


def _get_node_identity(toml_path: Path) -> Tuple[Optional[str], Optional[str]]:
    data = _load_pyproject_toml(toml_path)
    if not data:
        return None, None
    project = data.get("project") or data.get("tool", {}).get("poetry", {})
    name = project.get("name")
    version = project.get("version")
    return (name.strip().lower() if name else None,
            version.strip() if version else None)


def _files_match(local_path: Path, zip_info: zipfile.ZipInfo) -> bool:
    """Compare file size only — mtime in ZIP is unreliable."""
    if not local_path.exists():
        return False
    try:
        return local_path.stat().st_size == zip_info.file_size
    except OSError:
        return False


class SmartExtractor:
    def __init__(self,
                 zip_path: Path,
                 comfy_path: Path,
                 temp_dir: Path,
                 log_file: Optional[Path] = None,
                 minimal: bool = False,
                 force_extraction: bool = False):
        self.zip_path = zip_path
        self.comfy_path = comfy_path
        self.temp_dir = temp_dir
        self.log_file = log_file
        self.minimal = minimal
        self.force_extraction = force_extraction and not minimal
        self.extracted_files: List[Path] = []
        self.skipped_files: List[Path] = []
        self.custom_nodes_extracted: bool = False

    def _log(self, msg: str):
        print(msg)
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(msg + "\n")

    def extract(self) -> Path:
        os.makedirs(self.temp_dir, exist_ok=True)
        mode = 'MINIMAL' if self.minimal else 'FORCE' if self.force_extraction else 'SMART'
        self._log(f"[smart_extractor] Mode: {mode}")

        with zipfile.ZipFile(self.zip_path, "r") as zf:
            # 1. Extract root files (including pre.py/post.py)
            self._extract_root_files(zf)

            if not self.minimal:
                # 2. Extract generic content
                self._extract_generic_comfyui_contents(zf)
                # 3. Extract custom nodes
                self._extract_custom_nodes(zf)

            # 4. Run scripts with output monitoring
            self._run_script_if_exists(self.temp_dir / "pre.py")
            self._run_script_if_exists(self.temp_dir / "post.py")

        workflow_path = self.temp_dir / "workflow.json"
        if not workflow_path.exists():
            raise FileNotFoundError("workflow.json not found after extraction")
        return workflow_path

    def _extract_root_files(self, zf: zipfile.ZipFile):
        """Extract JSON, YAML, and Python scripts from the root of the ZIP."""
        root_items = [i for i in zf.namelist()
                      if i.lower().endswith(('.json', '.yaml', '.yml', '.py'))
                      and os.path.basename(i) == i]
        
        for item in root_items:
            target = self.temp_dir / os.path.basename(item)
            zf.extract(item, self.temp_dir)
            self.extracted_files.append(target)
            self._log(f"[smart_extractor] Extracted root: {target.name}")

    def _extract_generic_comfyui_contents(self, zf: zipfile.ZipFile):
        """
        Extract everything under ComfyUI/ EXCEPT custom_nodes/
        """
        comfy_prefix = "ComfyUI/"
        items = [i for i in zf.infolist()
                 if i.filename.startswith(comfy_prefix)
                 and not i.is_dir()
                 and "/custom_nodes/" not in i.filename]

        if not items:
            return

        if self.force_extraction:
            self._log("[smart_extractor] FORCE: extracting all generic ComfyUI content")
        else:
            self._log("[smart_extractor] SMART: extracting generic ComfyUI content (models, input, etc.)")

        for info in items:
            rel_path = Path(info.filename[len(comfy_prefix):])
            local_path = self.comfy_path / rel_path
            os.makedirs(local_path.parent, exist_ok=True)

            need_extract = self.force_extraction or not _files_match(local_path, info)

            if need_extract:
                tmp_extracted = self.temp_dir / info.filename
                zf.extract(info, self.temp_dir)
                shutil.copy2(tmp_extracted, local_path)
                self.extracted_files.append(local_path)
                self._log(f"[smart_extractor] EXTRACT generic: {rel_path}")
            else:
                self.skipped_files.append(local_path)
                self._log(f"[-detection] SKIP generic (identical): {rel_path}")

    def _extract_custom_nodes(self, zf: zipfile.ZipFile):
        if self.force_extraction:
            self._log("[smart_extractor] FORCE: extracting all custom nodes")
        else:
            self._log("[smart_extractor] SMART: checking custom nodes")

        node_prefix = "ComfyUI/custom_nodes/"
        node_dirs = {
            i.filename[len(node_prefix):].split("/", 1)[0]
            for i in zf.infolist()
            if i.filename.startswith(node_prefix) and i.filename.count("/") >= 2
        }

        for node_name in node_dirs:
            if not node_name or node_name.strip() == "":
                continue

            zip_node_root = f"{node_prefix}{node_name}"
            local_node_root = self.comfy_path / "custom_nodes" / node_name

            zf.extractall(self.temp_dir, members=[
                m for m in zf.namelist() if m.startswith(zip_node_root)
            ])

            zip_toml = self.temp_dir / zip_node_root / "pyproject.toml"
            local_toml = local_node_root / "pyproject.toml"

            zip_name, zip_ver = _get_node_identity(zip_toml)
            local_name, local_ver = _get_node_identity(local_toml)

            should_extract = self.force_extraction

            if not should_extract and zip_name and local_name and zip_name == local_name:
                if local_ver and zip_ver and zip_ver <= local_ver:
                    self._log(f"[smart_extractor] SKIP node {node_name} (local {local_ver} >= zip {zip_ver})")
                    should_extract = False
                else:
                    should_extract = True
            else:
                should_extract = True

            if not should_extract:
                shutil.rmtree(self.temp_dir / zip_node_root, ignore_errors=True)
                continue

            if local_node_root.exists():
                shutil.rmtree(local_node_root, ignore_errors=True)

            shutil.copytree(
                self.temp_dir / zip_node_root,
                local_node_root,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".git", ".github", "__pycache__")
            )
            self.extracted_files.append(local_node_root)
            self.custom_nodes_extracted = True
            self._log(f"[smart_extractor] EXTRACT node: {node_name} (v{zip_ver or 'unknown'})")

            req_path = local_node_root / "requirements.txt"
            if req_path.exists():
                self._log(f"[smart_extractor] Installing requirements for {node_name}...")
                try:
                    subprocess.check_call([
                        sys.executable, "-m", "pip", "install", "-r", str(req_path)
                    ], cwd=local_node_root)
                except subprocess.CalledProcessError as e:
                    self._log(f"[smart_extractor] FAILED requirements for {node_name}: {e}")

            shutil.rmtree(self.temp_dir / zip_node_root, ignore_errors=True)

    def _run_script_if_exists(self, script_path: Path):
        """
        Run a python script if it exists. 
        Monitors stdout for 'BENCHMARK_RESTART_REQUIRED' to set restart flag.
        """
        if script_path.exists():
            self._log(f"[smart_extractor] Running {script_path.name}...")
            try:
                # Use Popen to stream output and check for restart signal
                process = subprocess.Popen(
                    [sys.executable, str(script_path)],
                    cwd=self.temp_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                restart_signal = "BENCHMARK_RESTART_REQUIRED"
                
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    if line:
                        stripped_line = line.strip()
                        print(stripped_line) # Echo to console for user visibility
                        
                        # Log to file if configured
                        if self.log_file:
                             with open(self.log_file, "a", encoding="utf-8") as f:
                                f.write(stripped_line + "\n")
                                
                        if restart_signal in line:
                            self.custom_nodes_extracted = True
                            self._log(f"[smart_extractor] ⚠️ {script_path.name} requested ComfyUI restart")

                if process.returncode != 0:
                     raise subprocess.CalledProcessError(process.returncode, process.args)
                     
            except subprocess.CalledProcessError as e:
                self._log(f"[smart_extractor] ERROR in {script_path.name}: {e}")
                raise

    def cleanup(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self._log(f"[smart_extractor] Cleaned temp dir: {self.temp_dir}")