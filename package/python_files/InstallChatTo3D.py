from pathlib import Path
import git
from git.exc import GitCommandError
import shutil
import subprocess
import os
import platform
import logging
import re
import requests
import time
import psutil
import zipfile
import tempfile


# Set up logging for get_conda_python_path and general use
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# GitHub repository URL
gHubURL = 'https://github.com/anmaurya001/chat-to-3d.git'

# Get the directory two levels up from the current script (C:\Users\NV\VisualGenAI_BP\3d-guided-genai-rtx\package)
output_path = Path(__file__).resolve().parent.parent.parent.parent
target_dir = output_path / 'chat-to-3d'

def get_conda_exe() -> str | None:
    """Return the path to the Conda executable, prioritizing CONDA_EXE environment variable."""
    conda_exe = os.environ.get("CONDA_EXE")
    if conda_exe and os.path.isfile(conda_exe):
        logger.debug("Using CONDA_EXE: %s", conda_exe)
        return conda_exe

    default_paths = [
        Path(os.path.expanduser("~/Miniconda3/Scripts/conda.exe")),
        Path(os.path.expanduser("~/Anaconda3/Scripts/conda.exe")),
        Path("C:/ProgramData/Miniconda3/Scripts/conda.exe"),
        Path("C:/ProgramData/Anaconda3/Scripts/conda.exe")
    ]
    for path in default_paths:
        if path.exists():
            logger.info("Found Conda executable at: %s", path)
            os.environ["PATH"] = f"{path.parent};{os.environ.get('PATH', '')}"
            return str(path)
    
    logger.warning("No Conda executable found in CONDA_EXE or default paths")
    return None

def clone_repository(url: str, target_dir: Path) -> bool:
    """Clone a Git repository with --recursive to the target directory."""
    try:
        git.Repo.clone_from(
            url=url,
            to_path=target_dir,
            multi_options=['--recursive']
        )
        print(f"Successfully cloned repository to {target_dir}")
        return True
    except GitCommandError as e:
        if e.status == 128:
            print(f"Repository not cloned: Target directory '{target_dir}' already exists.")
        else:
            print(f"Error cloning repository: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error cloning repository: {e}")
        return False

def replace_file(target_file: Path, patch_file: Path) -> bool:
    """Replace target_file with patch_file if both exist."""
    if target_file.exists():
        print(f"Target file '{target_file}' exists.")
        if patch_file.exists():
            try:
                shutil.copy2(patch_file, target_file)
                print(f"Successfully replaced '{target_file}' with '{patch_file}'.")
                return True
            except Exception as e:
                print(f"Error replacing file: {e}")
                return False
        else:
            print(f"Patch file '{patch_file}' does not exist. No replacement performed.")
            return False
    else:
        print(f"Target file '{target_file}' does not exist. No replacement performed.")
        return False

def get_conda_base_path() -> str | None:
    """Attempt to find the Conda base directory."""
    conda_exe = get_conda_exe()
    if not conda_exe:
        return None

    try:
        result = subprocess.run(
            [conda_exe, "info", "--base"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout:
            conda_base = result.stdout.strip()
            logger.info("Found Conda base using 'conda info --base': %s", conda_base)
            return conda_base
        else:
            logger.warning("Could not locate Conda base using 'conda info --base': %s", result.stderr)
    except subprocess.SubprocessError as e:
        logger.warning("Failed to locate Conda base using 'conda info --base': %s", str(e))

    # Fallback to default
    conda_base = os.path.expanduser("~/Miniconda3")
    logger.debug("Falling back to default Conda base: %s", conda_base)
    if os.path.exists(conda_base):
        return conda_base
    logger.warning("Conda base directory not found: %s", conda_base)
    return None

def get_conda_python_path() -> str | None:
    """Attempt to find the Conda 'trellis' environment's Python executable."""
    conda_base = get_conda_base_path()
    if not conda_base:
        return None

    if platform.system() == "Windows":
        python_path = os.path.join(conda_base, "envs", "trellis", "python.exe")
    else:
        python_path = os.path.join(conda_base, "envs", "trellis", "bin", "python")
    
    if os.path.isfile(python_path):
        try:
            result = subprocess.run(
                [python_path, "-c", "import sys; print(sys.version)"],
                capture_output=True,
                text=True,
                timeout=5
            )
            logger.debug("Conda Python version: %s", result.stdout.strip())
            return python_path
        except subprocess.SubprocessError as e:
            logger.error("Failed to verify Conda Python: %s", str(e))
            return None
    logger.warning("Conda Python not found at %s", python_path)
    return None

def check_conda_installed() -> bool:
    """Check if Conda is installed by running 'conda --version'."""
    conda_exe = get_conda_exe()
    if not conda_exe:
        print("Conda is not installed or not found in CONDA_EXE or default locations.")
        logger.error("Conda check failed: Unable to locate conda executable")
        return False

    try:
        result = subprocess.run(
            [conda_exe, '--version'],
            capture_output=True,
            text=True,
            check=True
        )
        version = result.stdout.strip()
        print(f"Conda is installed: {version} (found at {conda_exe})")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Conda check failed: {e.stderr}")
        logger.error("Conda check failed: %s", e.stderr)
        return False

def check_trellis_environment() -> bool:
    """Check if a Conda environment named 'trellis' exists."""
    python_path = get_conda_python_path()
    if python_path:
        print(f"Conda environment 'trellis' exists. Python executable: {python_path}")
        return True
    else:
        print("Conda environment 'trellis' does not exist.")
        return False

def install_trellis_conda_packages() -> bool:
    """Install nvidia::cuda-runtime and nvidia::cuda-nvcc in the trellis environment."""
    conda_exe = get_conda_exe()
    if not conda_exe:
        print("Cannot install Conda packages: Conda executable not found.")
        logger.error("Conda executable not found for package installation")
        return False

    print("Installing Conda packages in 'trellis' environment...")
    try:
        result = subprocess.run(
            [
                conda_exe, 'install', '-n', 'trellis', '-c', 'nvidia',
                'cuda-runtime', 'cuda-nvcc', '-y'
            ],
            capture_output=True,
            text=True,
            check=True
        )
        print("Successfully installed nvidia::cuda-runtime and nvidia::cuda-nvcc.")
        logger.info("Conda install output: %s", result.stdout.strip())
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error installing Conda packages: {e.stderr}")
        logger.error("Failed to install Conda packages: %s", e.stderr)
        return False

def install_trellis_pip_requirements(target_dir: Path) -> bool:
    """Install pip requirements from files in target_dir using trellis environment."""
    conda_exe = get_conda_exe()
    if not conda_exe:
        print("Cannot install pip requirements: Conda executable not found.")
        logger.error("Conda executable not found")
        return False

    requirements_files = [
        target_dir / 'requirements-torch.txt',
        target_dir / 'requirements-other.txt',
        target_dir / 'requirements.txt'
    ]

    all_success = True
    for req_file in requirements_files:
        if not req_file.exists():
            print(f"Requirements file '{req_file}' does not exist. Skipping.")
            logger.warning("Requirements file not found: %s", req_file)
            all_success = False
            continue

        print(f"Installing pip requirements from '{req_file}'...")
        try:
            # Use conda run to ensure the trellis environment is activated
            cmd = [
                conda_exe, 'run', '-n', 'trellis',
                'python', '-m', 'pip', 'install', '-r', str(req_file)
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            print(f"Successfully installed requirements from '{req_file}'.")
            logger.info("Pip install output for %s: %s", req_file, result.stdout.strip())
        except subprocess.CalledProcessError as e:
            print(f"Error installing requirements from '{req_file}': {e.stderr}")
            logger.error("Failed to install requirements from %s: %s", req_file, e.stderr)
            all_success = False
        except FileNotFoundError:
            print(f"Cannot install requirements: Conda executable '{conda_exe}' not found.")
            logger.error("Conda executable not found: %s", conda_exe)
            all_success = False

    return all_success

def install_trellis_local_modules(target_dir: Path) -> bool:
    """Install local modules vox2seq and flash_attn wheel file using trellis environment's Python."""
    python_path = get_conda_python_path()
    if not python_path:
        print("Cannot install local modules: 'trellis' environment Python not found.")
        logger.error("Trellis environment Python executable not found")
        return False

    module_paths = [
        target_dir / 'trellis' / 'extensions' / 'vox2seq'
    ]

    all_success = True
    for module_path in module_paths:
        if not module_path.exists():
            print(f"Local module '{module_path}' does not exist. Skipping.")
            logger.warning("Local module not found: %s", module_path)
            all_success = False
            continue

        print(f"Installing local module '{module_path}'...")
        try:
            result = subprocess.run(
                [python_path, '-m', 'pip', 'install', str(module_path)],
                capture_output=True,
                text=True,
                check=True
            )
            print(f"Successfully installed local module '{module_path}'.")
            logger.info("Pip install output for %s: %s", module_path, result.stdout.strip())
        except subprocess.CalledProcessError as e:
            print(f"Error installing local module '{module_path}': {e.stderr}")
            logger.error("Failed to install local module %s: %s", module_path, e.stderr)
            all_success = False
        except FileNotFoundError:
            print(f"Cannot install local module: Python executable '{python_path}' not found.")
            logger.error("Python executable not found: %s", python_path)
            all_success = False

    return all_success

def set_persistent_env_var(name: str, value: str, system_level: bool = False) -> bool:
    """Set a persistent environment variable."""
    try:
        if platform.system() == "Windows":
            scope = "System" if system_level else "User"
            cmd = ['setx', name, value]
            if system_level:
                cmd = [
                    'powershell', '-Command',
                    f'[Environment]::SetEnvironmentVariable("{name}", "{value}", "{scope}")'
                ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            print(f"Successfully set persistent environment variable '{name}' = '{value}' ({scope} level)")
            logger.info("Setx/PowerShell output: %s", result.stdout.strip())
        
        else:  # Linux/macOS
            shell = os.environ.get('SHELL', '')
            if 'bash' in shell:
                config_file = Path.home() / '.bashrc'
            elif 'zsh' in shell:
                config_file = Path.home() / '.zshrc'
            else:
                config_file = Path.home() / '.profile'
            
            if system_level:
                config_file = Path('/etc/environment')
                if not os.access(config_file, os.W_OK):
                    print(f"Cannot write to {config_file}: Requires root privileges")
                    logger.error("Insufficient permissions for system-level variable")
                    return False
            
            with config_file.open('a') as f:
                f.write(f'\nexport {name}="{value}"\n')
            print(f"Successfully set persistent environment variable '{name}' = '{value}' in {config_file}")
            logger.info("Appended to %s: export %s=%s", config_file, name, value)
            os.environ[name] = value
        
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"Error setting environment variable '{name}': {e.stderr}")
        logger.error("Failed to set environment variable: %s", e.stderr)
        return False
    except PermissionError:
        print(f"Permission denied: Cannot set {name} at {'system' if system_level else 'user'} level")
        logger.error("Permission denied for environment variable %s", name)
        return False
    except Exception as e:
        print(f"Unexpected error setting environment variable '{name}': {str(e)}")
        logger.error("Unexpected error: %s", str(e))
        return False

def copy_blender_addons(target_dir: Path) -> bool:
    """Copy NV_Trellis_Addon.py and asset_importer.py to Blender addons directories for versions >= 4.2."""
    if platform.system() == "Windows":
        blender_dir = Path(os.getenv('APPDATA', Path.home() / 'AppData' / 'Roaming')) / 'Blender Foundation' / 'Blender'
    elif platform.system() == "Linux":
        blender_dir = Path.home() / '.config' / 'blender'
    else:  # macOS
        blender_dir = Path.home() / 'Library' / 'Application Support' / 'Blender'

    if not blender_dir.exists():
        print(f"Blender configuration directory not found: {blender_dir}")
        logger.warning("Blender directory not found: %s", blender_dir)
        return False

    source_files = [
        target_dir / 'blender' / 'NV_Trellis_Addon.py',
        target_dir / 'blender' / 'asset_importer.py'
    ]

    for source_file in source_files:
        if not source_file.exists():
            print(f"Source file '{source_file}' does not exist. Cannot copy addons.")
            logger.error("Source file not found: %s", source_file)
            return False

    all_success = True
    version_pattern = re.compile(r'^\d+\.\d+$')
    for version_dir in blender_dir.iterdir():
        if not version_dir.is_dir():
            continue
        version_str = version_dir.name
        if not version_pattern.match(version_str):
            continue

        try:
            version_num = float(version_str)
            if version_num >= 4.2:
                addons_dir = version_dir / 'scripts' / 'addons'
                addons_dir.mkdir(parents=True, exist_ok=True)

                for source_file in source_files:
                    try:
                        shutil.copy2(source_file, addons_dir / source_file.name)
                        print(f"Copied '{source_file.name}' to '{addons_dir}' for Blender {version_str}")
                        logger.info("Copied %s to %s", source_file.name, addons_dir)
                    except Exception as e:
                        print(f"Error copying '{source_file.name}' to '{addons_dir}': {str(e)}")
                        logger.error("Failed to copy %s to %s: %s", source_file.name, addons_dir, str(e))
                        all_success = False
        except ValueError:
            logger.debug("Skipping non-numeric directory: %s", version_str)
            continue

    if all_success:
        print("Successfully copied all Blender addons for versions >= 4.2")
    else:
        print("Some Blender addon copies failed")
    return all_success

def run_and_monitor_gradio_service(target_dir: Path) -> bool:
    """Run the Gradio service and monitor http://127.0.0.1:7860/ for up to 3 minutes, then terminate."""
    conda_exe = get_conda_exe()
    if not conda_exe:
        print("Cannot run Gradio service: Conda executable not found.")
        logger.error("Conda executable not found")
        return False

    run_script = target_dir / 'chat-to-3d-core' / 'run.py'
    if not run_script.exists():
        print(f"Gradio run script '{run_script}' does not exist.")
        logger.error("Gradio run script not found: %s", run_script)
        return False

    print("Starting Gradio service...")
    cmd = [
        conda_exe, 'run', '-n', 'trellis',
        'python', str(run_script)
    ]
    try:
        # Start the process without capturing output to allow it to run in the background
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.info("Started Gradio service with PID: %s", process.pid)
    except subprocess.SubprocessError as e:
        print(f"Error starting Gradio service: {str(e)}")
        logger.error("Failed to start Gradio service: %s", str(e))
        return False

    # Monitor the webpage
    url = "http://127.0.0.1:7860/"
    timeout = 180  # 3 minutes in seconds
    start_time = time.time()
    check_interval = 5  # Check every 5 seconds

    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"Gradio service is active at {url}")
                logger.info("Gradio webpage is active")
                break
        except requests.RequestException as e:
            logger.debug("Gradio webpage not yet active: %s", str(e))
        time.sleep(check_interval)
    else:
        print("Gradio service did not become active within 3 minutes.")
        logger.warning("Gradio service timeout after %s seconds", timeout)

    # Terminate the process
    try:
        parent = psutil.Process(process.pid)
        # Terminate all child processes
        for child in parent.children(recursive=True):
            child.terminate()
        parent.terminate()
        # Wait briefly to ensure termination
        parent.wait(timeout=5)
        print("Gradio service terminated.")
        logger.info("Gradio service terminated, PID: %s", process.pid)
    except psutil.NoSuchProcess:
        logger.warning("Gradio process already terminated")
    except psutil.TimeoutExpired:
        logger.warning("Gradio process did not terminate within timeout, forcing kill")
        parent.kill()
    except Exception as e:
        print(f"Error terminating Gradio service: {str(e)}")
        logger.error("Failed to terminate Gradio service: %s", str(e))
        return False

    return True

def install_ninja_to_trellis() -> bool:
    """Check for trellis environment in environments.txt, download ninja-win.zip, and install ninja.exe."""
    logger.info("Attempting to install Ninja to Trellis environment")
    # Check for environments.txt
    env_file = Path(os.path.expanduser("~/.conda/environments.txt"))
    if not env_file.exists():
        print(f"Conda environments file not found at {env_file}")
        logger.error("Conda environments file not found: %s", env_file)
        return False

    # Read environments.txt and find trellis
    trellis_path = None
    try:
        with env_file.open('r') as f:
            for line in f:
                line = line.strip()
                if line and 'trellis' in line:
                    trellis_path = Path(line)
                    print(f"Found trellis environment at: {trellis_path}")
                    logger.info("Trellis environment found in environments.txt: %s", trellis_path)
                    break
        if not trellis_path:
            print("Trellis environment not found in environments.txt")
            logger.warning("No trellis environment in %s", env_file)
            return False
    except Exception as e:
        print(f"Error reading environments.txt: {str(e)}")
        logger.error("Failed to read %s: %s", env_file, str(e))
        return False

    # Download ninja-win.zip
    ninja_url = "https://github.com/ninja-build/ninja/releases/download/v1.13.0/ninja-win.zip"
    temp_dir = Path(tempfile.gettempdir()) / "ninja_download"
    temp_dir.mkdir(exist_ok=True)
    zip_path = temp_dir / "ninja-win.zip"

    print(f"Downloading ninja from {ninja_url}...")
    try:
        response = requests.get(ninja_url, timeout=10)
        if response.status_code != 200:
            print(f"Failed to download ninja: HTTP {response.status_code}")
            logger.error("Download failed: HTTP %s", response.status_code)
            return False
        with zip_path.open('wb') as f:
            f.write(response.content)
        logger.info("Downloaded ninja to %s", zip_path)
    except requests.RequestException as e:
        print(f"Error downloading ninja: {str(e)}")
        logger.error("Download failed: %s", str(e))
        return False

    # Extract ninja-win.zip
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        logger.info("Extracted ninja to %s", temp_dir)
    except zipfile.BadZipFile as e:
        print(f"Error extracting ninja zip: {str(e)}")
        logger.error("Failed to extract %s: %s", zip_path, str(e))
        return False

    # Locate ninja.exe
    ninja_exe = temp_dir / "ninja.exe"
    if not ninja_exe.exists():
        print(f"ninja.exe not found in extracted files at {temp_dir}")
        logger.error("ninja.exe not found in %s", temp_dir)
        return False

    # Determine destination directory
    if platform.system() == "Windows":
        dest_dir = trellis_path
    else:
        dest_dir = trellis_path / "bin"
    dest_dir.mkdir(exist_ok=True)
    dest_path = dest_dir / "ninja.exe"

    # Move ninja.exe to trellis environment
    try:
        shutil.move(str(ninja_exe), str(dest_path))
        print(f"Successfully moved ninja.exe to {dest_path}")
        logger.info("Moved ninja.exe to %s", dest_path)
    except Exception as e:
        print(f"Error moving ninja.exe to {dest_path}: {str(e)}")
        logger.error("Failed to move ninja.exe to %s: %s", dest_path, str(e))
        return False

    # Clean up temporary directory
    try:
        shutil.rmtree(temp_dir)
        logger.info("Cleaned up temporary directory %s", temp_dir)
    except Exception as e:
        logger.warning("Failed to clean up %s: %s", temp_dir, str(e))

    return True


def main():
    """Main function to execute Git clone, file replacement, Conda checks, package installation, and Blender addon copying."""
    # Step 1: Clone the repository
    print("Cloning repository...")
    clone_success = clone_repository(gHubURL, target_dir)

    # Step 2: Replace the file if applicable
    print("\nChecking and replacing file...")
    target_file = target_dir / 'trellis' / 'trellis' / 'representations' / 'mesh' / 'flexicubes' / 'flexicubes.py'
    patch_file = target_dir / 'patchfiles' / 'flexicubes.py'
    replace_file(target_file, patch_file)

    # Step 3: Check Conda and trellis environment
    print("\nChecking for Conda installation...")
    conda_installed = check_conda_installed()
    if conda_installed:
        print("\nChecking for 'trellis' environment...")
        trellis_exists = check_trellis_environment()

        # Step 4: If conda trellis environment does not exist, create it
        if not trellis_exists:
            print("\nCreating 'trellis' environment...")
            conda_exe = get_conda_exe()
            if not conda_exe:
                print("Cannot create 'trellis' environment: Conda executable not found.")
                logger.error("Conda executable not found for environment creation")
                return
            try:
                subprocess.run([conda_exe, 'create', '-n', 'trellis', 'python=3.11.9', '-y'], check=True)
                print("Successfully created 'trellis' environment.")
            except subprocess.CalledProcessError as e:
                print(f"Error creating 'trellis' environment: {e.stderr}")
                logger.error("Failed to create trellis environment: %s", e.stderr)
                return

        # Step 5: Install Conda packages in trellis environment
        #print("\nInstalling Conda packages in trellis environment...")
        #install_trellis_conda_packages()

        # Step 6: Install pip requirements in trellis environment
        print("\nInstalling pip requirements in trellis environment...")
        install_trellis_pip_requirements(target_dir)

        # Step 7: Install local modules in trellis environment
        print("\nInstalling local modules in trellis environment...")
        install_trellis_local_modules(target_dir)

        # Step 8: Install ninja to trellis environment
        print("\nInstalling ninja to trellis environment...")
        install_ninja_to_trellis()

        # Step 9: Set persistent environment variable
        print("\nSetting persistent environment variable...")
        env_var_name = "CHAT_TO_3D_PATH"
        env_var_value = str(target_dir)
        set_persistent_env_var(env_var_name, env_var_value, system_level=False)

        # Step 10: Run and monitor Gradio service
        print("\nRunning and monitoring Gradio service...")
        run_and_monitor_gradio_service(target_dir)

        # Step 11: Copy Blender addons for versions >= 4.2
        print("\nCopying Blender addons for versions >= 4.2...")
        copy_blender_addons(target_dir)

if __name__ == "__main__":
    main()