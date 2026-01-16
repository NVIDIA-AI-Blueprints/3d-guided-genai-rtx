import subprocess
import os
from pathlib import Path
import logging
import sys
import re
import traceback
import time

# Setup logging with explicit console and file handlers
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console_handler.setFormatter(formatter)
file_handler = logging.FileHandler("run_ngc_podman_flux.log")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.handlers = [console_handler, file_handler]

try:
    import pynvml
    import requests
except ImportError as e:
    logger.error(f"Missing dependency: {e}")
    print(f"Error: Missing dependency: {e}")
    print("Please install required packages: pip install pynvml requests")
    sys.exit(1)

# Functions from ngc.py
def get_device_info_nvml():
    logger.debug("Attempting to get device info via NVML")
    try:
        pynvml.nvmlInit()
        deviceCount = pynvml.nvmlDeviceGetCount()
        deviceInfo = []
        for i in range(deviceCount):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            uuid = pynvml.nvmlDeviceGetUUID(handle)
            name = pynvml.nvmlDeviceGetName(handle)
            brand = pynvml.nvmlDeviceGetBrand(handle)
            architecture = pynvml.nvmlDeviceGetArchitecture(handle)
            pciDeviceId = pynvml.nvmlDeviceGetPciInfo(handle).pciDeviceId
            pciDeviceId_64bit = format(pciDeviceId, 'X')
            fakePdi = int(hash(uuid) % 2**64)
            pdi_64bit = format(fakePdi, 'X')
            deviceInfo.append({
                'uuid': uuid,
                'pdi': f"0x{pdi_64bit}",
                'name': name,
                'brand': brand,
                'architecture': architecture,
                'pci_device_id': f"0x{pciDeviceId_64bit}",
            })
        pynvml.nvmlShutdown()
        logger.debug(f"NVML device info: {deviceInfo}")
        return deviceInfo
    except pynvml.NVMLError as e:
        logger.warning(f"NVML Error: {e}")
        pynvml.nvmlShutdown()
        return []
    except Exception as e:
        logger.error(f"Unexpected error in get_device_info_nvml: {e}")
        return []

def get_device_info_smi():
    logger.debug("Attempting to get device info via nvidia-smi")
    try:
        output = subprocess.check_output(['nvidia-smi', '-q'], text=True)
        deviceInfo = []
        uuid_pattern = re.compile(r"GPU UUID\s*:\s*(.+)")
        pdi_pattern = re.compile(r"PDI\s*:\s*(.+)")
        name_pattern = re.compile(r"Product Name\s*:\s*(.+)")
        brand_pattern = re.compile(r"Product Brand\s*:\s*(.+)")
        arch_pattern = re.compile(r"Product Architecture\s*:\s*(.+)")
        pci_pattern = re.compile(r"Device Id\s*:\s*(.+)")

        matches = {
            "uuid": uuid_pattern.search(output),
            "pdi": pdi_pattern.search(output),
            "name": name_pattern.search(output),
            "brand": brand_pattern.search(output),
            "architecture": arch_pattern.search(output),
            "pci_device_id": pci_pattern.search(output),
        }

        if not matches["pdi"] and matches["uuid"]:
            fakePdi = int(hash(matches["uuid"].group(1).strip()) % 2**64)
            pdi_64bit = format(fakePdi, 'X')
            matches["pdi"] = re.match(r"(.+)", f"0x{pdi_64bit}")

        deviceInfo.append({k: (m.group(1).strip() if m else "Unknown") for k, m in matches.items()})
        logger.debug(f"SMI device info: {deviceInfo}")
        return deviceInfo
    except subprocess.CalledProcessError as e:
        logger.warning(f"nvidia-smi error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in get_device_info_smi: {e}")
        return []

def get_ngc_key_from_device_info(deviceInfo):
    logger.debug("Attempting to fetch NGC API key")
    ngcKeyServiceUrl = 'https://nts.ngc.nvidia.com/v1/token'
    payload = {
        "client_id": "examplepy",
        "pdi": deviceInfo[0].get('pdi', 'Unknown') if deviceInfo else 'Unknown',
        "access_policy_name": "nim-dev",
        "device": deviceInfo[0] if deviceInfo else {}
    }
    try:
        response = requests.post(ngcKeyServiceUrl, headers={'Accept': 'application/json'}, json=payload)
        response.raise_for_status()
        keyData = response.json()
        logger.debug("Successfully fetched NGC API key")
        return keyData.get('access_token')
    except requests.RequestException as e:
        logger.error(f"Error fetching API key: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_ngc_key_from_device_info: {e}")
        return None

def get_ngc_key():
    logger.debug("Starting get_ngc_key")
    deviceInfoNvml = get_device_info_nvml()
    deviceInfoSmi = get_device_info_smi()
    if not deviceInfoNvml and not deviceInfoSmi:
        logger.error("No device info available from NVML or nvidia-smi")
        raise Exception("No GPU device info available")
    key = get_ngc_key_from_device_info(deviceInfoNvml)
    if key:
        return key
    logger.error("Failed to get NGC API key")
    raise Exception("Error getting NGC API key. Please follow the instructions in the README to set up your NGC API key.")

def stop_container():
    """Attempt to stop the FLUX_DEPTH container and verify it's stopped."""
    logger.debug("Attempting to stop FLUX_DEPTH container")
    try:
        # Stop the container
        stop_process = subprocess.run(
            ["wsl", "-d", "NVIDIA-Workbench", "podman", "stop", "FLUX_DEPTH"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if stop_process.returncode == 0:
            logger.info("Successfully stopped FLUX_DEPTH container.")
            print("Successfully stopped FLUX_DEPTH container.")
        else:
            logger.warning(f"Stop command returned non-zero exit code: {stop_process.stderr}")
            print(f"Warning: Stop command returned non-zero exit code: {stop_process.stderr}")

        # Verify the container is stopped
        check_process = subprocess.run(
            ["wsl", "-d", "NVIDIA-Workbench", "podman", "ps", "-a", "--filter", "name=FLUX_DEPTH"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if "FLUX_DEPTH" not in check_process.stdout:
            logger.debug("Verified: FLUX_DEPTH container is not running.")
        else:
            logger.warning("FLUX_DEPTH container may still be running.")
            print("Warning: FLUX_DEPTH container may still be running.")
    except subprocess.TimeoutExpired:
        logger.error("Timeout while stopping FLUX_DEPTH container.")
        print("Error: Timeout while stopping FLUX_DEPTH container.")
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"Error stopping FLUX_DEPTH container: {e.stderr}")
        print(f"Error stopping FLUX_DEPTH container: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error stopping FLUX_DEPTH container: {e}")
        print(f"Error: Unexpected error stopping FLUX_DEPTH container: {e}")
        raise

def main():
    logger.debug("Starting run_ngc_podman_flux.py")
    # Use current directory as target_dir
    target_dir = Path(__file__).resolve().parent
    logger.debug(f"Using target_dir (CWD): {target_dir}")

    try:
        # Get NGC API key
        logger.debug("Retrieving NGC API key")
        try:
            ngc_api_key = get_ngc_key()
            logger.info("Successfully retrieved NGC API Key.")
        except Exception as e:
            logger.error(f"Failed to retrieve NGC API key: {e}")
            print(f"Error: Failed to retrieve NGC API key: {e}")
            sys.exit(1)

        # Get HF_TOKEN
        hftoken = os.environ.get('HF_TOKEN')
        if not hftoken:
            logger.error("HF_TOKEN environment variable is not set.")
            print("Error: HF_TOKEN environment variable is not set.")
            sys.exit(1)
        logger.debug(f"Retrieved HF_TOKEN: {hftoken}")

        # Resolve shell script path
        script_dir = target_dir.parent /  "shell_scripts"
        script_name = "start_flux_container.sh"
        windows_script_path = script_dir / script_name
        logger.debug(f"Checking for shell script: {windows_script_path}")
        if not windows_script_path.exists():
            logger.error(f"Shell script not found: {windows_script_path}")
            print(f"Error: Shell script '{windows_script_path}' does not exist.")
            sys.exit(1)

        # Convert Windows path to WSL path
        drive_letter = windows_script_path.drive[0].lower()
        wsl_script_path = f"/mnt/{drive_letter}{windows_script_path.as_posix()[2:]}"
        logger.info(f"Resolved WSL script path: {wsl_script_path}")

        # Prepare environment and command with hftoken as positional argument
        bash_command = f"export NGC_API_KEY='{ngc_api_key}' && '{wsl_script_path}' '{hftoken}'"
        logger.debug(f"Prepared bash command: {bash_command}")

        # Open log file for writing
        log_file_path = script_dir / "logs" / "flux_container.log"
        logger.debug(f"Opening log file: {log_file_path}")
        try:
            # Ensure nim_llm directory exists
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file_path, "w") as log_file:
                logger.info(f"Logging Podman output to {log_file_path}")
                print(f"Running Podman command via WSL (logging to {log_file_path})...")

                # Launch process with Popen to stream output
                logger.debug("Starting WSL subprocess")
                process = subprocess.Popen(
                    ["wsl", "-d", "NVIDIA-Workbench", "/bin/bash", "-c", bash_command],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )

                # Stream output and monitor for "Application startup complete" with timeout
                startup_complete = False
                start_time = time.time()
                timeout_seconds = 3600  # 60 minutes timeout
                while True:
                    try:
                        line = process.stdout.readline().strip()
                        if not line and process.poll() is not None:
                            logger.debug("Process ended unexpectedly.")
                            break
                        if line:
                            logger.debug(f"Podman output: {line}")
                            print(line)
                            log_file.write(line + "\n")
                            log_file.flush()

                            # Check for startup complete
                            if "Serving endpoints:" in line:
                                logger.info("Detected 'Application startup complete'. Stopping container...")
                                print("Detected 'Application startup complete'. Stopping container...")
                                startup_complete = True
                                stop_container()
                                break

                        # Check for timeout
                        if time.time() - start_time > timeout_seconds:
                            logger.error(f"Timeout: 'Application startup complete' not detected within {timeout_seconds//60} minutes.")
                            print(f"Error: Timeout: 'Application startup complete' not detected within {timeout_seconds//60} minutes.")
                            stop_container()
                            sys.exit(1)

                    except KeyboardInterrupt:
                        logger.warning("Received KeyboardInterrupt. Stopping container...")
                        print("Received KeyboardInterrupt. Stopping container...")
                        stop_container()
                        sys.exit(1)

                # Wait for the process to complete
                process.wait()
                logger.debug(f"Subprocess completed with return code: {process.returncode}")

                if not startup_complete:
                    logger.error("Podman command did not output 'Application startup complete'.")
                    print("Error: Podman command did not output 'Application startup complete'.")
                    stop_container()
                    sys.exit(1)

                if process.returncode != 0:
                    logger.warning(f"Podman command returned non-zero exit code {process.returncode}, but startup completed successfully.")
                    print(f"Warning: Podman command returned non-zero exit code {process.returncode}, but startup completed successfully.")
                    # Exit with 0 to allow host script to proceed
                    sys.exit(0)

                logger.info("Podman command executed and container stopped successfully.")
                print("Podman command executed and container stopped successfully.")

        except FileNotFoundError as e:
            logger.error(f"Failed to create log file {log_file_path}: {e}")
            print(f"Error: Failed to create log file {log_file_path}: {e}")
            stop_container()
            sys.exit(1)

    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.cmd}, Exit code: {e.returncode}, Output: {e.output}")
        print(f"Error: Command failed: {e.cmd}\nExit code: {e.returncode}\nOutput: {e.output}")
        stop_container()
        sys.exit(e.returncode)
    except Exception as e:
        logger.error(f"Unexpected error: {e}\n{traceback.format_exc()}")
        print(f"Error: Unexpected error: {e}\n{traceback.format_exc()}")
        stop_container()
        sys.exit(1)

if __name__ == "__main__":
    main()