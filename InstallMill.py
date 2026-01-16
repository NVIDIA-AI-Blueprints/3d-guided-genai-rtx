import io, os, csv, requests, zipfile, subprocess, sys, time, platform
python_executable = sys.executable
if not python_executable:
    python_executable = "unknown"
print(f"Current Python executable: {python_executable}")

import shutil, argparse, urllib, validators, re, winreg, ctypes, typing
import traceback
import msvcrt
import logging
from sys import version_info
from git import Repo
from pathlib import Path
from huggingface_hub import hf_hub_download
from huggingface_hub import snapshot_download
from huggingface_hub.utils import are_progress_bars_disabled, disable_progress_bars, enable_progress_bars
from huggingface_hub import list_repo_files
from huggingface_hub import whoami

# Set up logging for get_conda_python_path and general use
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

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
        
def is_admin():
    try:
        # Check if the current user has administrator privileges
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False  
        

class ManifestItem:
    def __init__(self, url, location, overwrite, basefolder):
        self.url = url
        self.location = location
        self.overwrite = overwrite
        self.basefolder = basefolder
        self.valid_url = validators.url(url)
        
        #Get the overwrite value and convert it to an actual boolean
        if self.overwrite.lower() == 'true':
            self.overwrite = True
        else:
            self.overwrite = False
            
        # If the supplied URL is a valid URL
        if self.valid_url:
            self.url_parts = urllib.parse.urlsplit(url)
        else:
            self.url_parts = None

        self.item_type = self.interrogate_url()
        print(f'The manifest item type is: {self.item_type}')

    def interrogate_url(self):

        if not self.valid_url:
            #IF the file has an absolute path provided check if it exists
            if os.path.isabs(self.url):
                if os.path.isfile(self.url):
                    return 'LOCAL_FILE'
            else:  #IF the file path is relative, check if it exists in the install location or in the original base location.
                if os.path.isfile(self.url):
                    return 'LOCAL_FILE'
                elif os.path.isfile(os.path.normpath(os.path.join(self.basefolder,self.url))):
                    self.url=os.path.join(self.basefolder,self.url)
                    return 'LOCAL_FILE'

            if self.location.lower() == 'comfy_manager_install':
                return 'CM_MANAGER_INSTALL'
            elif self.location.lower() == 'winget_install':
                print("Found winget_install...")
                return 'WINGET_INSTALL'
            return 'INVALID_URL'

        if self.url_parts.netloc == "huggingface.co":
            path = self.url_parts.path
            path_parts = path.split('/')
            self.repo_id = path_parts[1] + '/' + path_parts[2] if len(path_parts) > 2 else None
            element_f = path.split(self.repo_id)[1].split('/')[-1] if self.repo_id else None
            local_path, local_filename = split_tup = os.path.split(self.location)
            self.local_path = local_path
            self.local_filename = local_filename

            if element_f and len(element_f) > 0:
                self.is_file = True
                self.is_repo = False
                self.filename = element_f
                return 'HF_FILE'
            else:
                self.is_file = False
                self.is_repo = True
                self.filename = None
                return 'HF_REPO'

        elif "github.com" in self.url_parts.netloc:
            path = self.url_parts.path
            # This will return a tuple of root and extension
            split_tup = os.path.splitext(path)
            # Extract the file name and extension
            element_f = split_tup[0]
            element_x = split_tup[1]

            if element_x == '.git':
                self.is_file = False
                self.is_repo = True
                self.filename = None
                self.repo_id = os.path.basename(element_f)
                return 'GH_REPO'
            else:
                self.is_file = True
                self.is_repo = False
                self.filename = os.path.basename(element_f)
                self.repo_id = os.path.basename(element_f)
                return 'GH_FILE'
        else:
            self.is_file = True
            self.is_repo = False
            self.filename = None
            return 'UNDEFINED'



def is_package_installed(package_name):
    """Check if the Python package is installed."""
    try:
        subprocess.check_call([f'pip show {package_name}'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def clone_or_update_repo(repo_url, local_path):
    """Clone the repo if it doesn't exist, or update it if it does."""
    if not os.path.exists(local_path):
        # Clone the repository
        print(f"Cloning repository from {repo_url} to {local_path}")
        repo = Repo.clone_from(repo_url, local_path)
    else:
        # Update the repository
        print(f"Repository already exists at {local_path}. Pulling latest changes.")
        repo = Repo(local_path)
        origin = repo.remotes.origin
        origin.pull()

def install_package_from_local_path(local_path):
    """Install the package from the local repository."""
    print(f"Installing package from {local_path}")
    subprocess.check_call([f'pip install {local_path}'], shell=True)

def manage_package(package_name, repo_url, local_path):
    """Check if the package is installed, clone/update the repo, and install the package."""
    if is_package_installed(package_name):
        print(f"{package_name} is already installed. Updating the package.")
        clone_or_update_repo(repo_url, local_path)
        
    else:
        print(f"{package_name} is not installed. Cloning the repository and installing the package.")
        clone_or_update_repo(repo_url, local_path)
       
        
# Function to Clone github Repos
def clone_repo(repo_url, dest_folder):
    try:
        print(f"Cloning repository from {repo_url} into {dest_folder}")
        Repo.clone_from(repo_url, dest_folder)
        print("Repository cloned successfully.")
    except Exception as e:
        print(f"An error occurred while cloning the repository: {e}")


# Function to stream the download of larger files
def stream_dl(url,file_name):
    # Open the stream to the URL
    r = requests.get(url, stream=True)

    print('Saving to: ', file_name)

    # Create the directory/file 
    os.makedirs(os.path.dirname(file_name), exist_ok=True)
    with open(file_name, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024*1024):
            if chunk:
                print('#',end="",flush=True)
                f.write(chunk)
    print('\nSave Complete.\n')

def check_hf_token_validity(token):
    """
    Check if a Hugging Face token is valid using the whoami endpoint.

    Args:
        token (str): The Hugging Face API token to validate.

    Returns:
        tuple: A tuple containing:
            - bool: True if the token is valid, False otherwise.
            - dict or str: User information (dict) if valid, or an error message (str) if invalid.
    """
    # Check if the token is provided
    if not token:
        return False, "Token is empty or not provided"

    # Define the API endpoint and headers
    endpoint = "https://huggingface.co/api/whoami-v2"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # Make the GET request to the whoami endpoint
        response = requests.get(endpoint, headers=headers)

        # Check the response status code
        if response.status_code == 200:
            # Parse and return user information if the token is valid
            user_info = response.json()
            return True, user_info
        elif response.status_code == 401:
            # Token is invalid
            return False, "Invalid token"
        else:
            # Other API errors
            return False, f"API error: {response.status_code} {response.reason}"

    except requests.exceptions.RequestException as e:
        # Handle network or request-related errors
        return False, f"Request failed: {str(e)}"
    except ValueError:
        # Handle cases where the response is not valid JSON
        return False, "Invalid response format: not JSON"

def check_model_access(model):
    """
    Check if the user has access to a specified Hugging Face model using the HF_TOKEN environment variable.

    Args:
        model_name (str): The name of the model repository (e.g., "meta-llama/Llama-2-7b").

    Returns:
        tuple: (bool, str) where the first element indicates success (True if access is granted, False otherwise),
               and the second element is a message explaining the result.
    """

    try:
        # Attempt to list files in the model repository with the provided token
        g = hf_hub_download(repo_id=model["model_name"], filename=model["filename"], token=model["token"])
        return True, "User has access to the model"

    except requests.exceptions.HTTPError as e:
        # Handle HTTP errors, specifically 401 (Unauthorized) or 403 (Forbidden)
        if e.response.status_code == 404:
            return False, "The model repository does not exist"
        elif e.response.status_code in [401, 403]:
            return False, "User does not have access to the gated model"
        else:
            return False, f"An HTTP error occurred: {e}"

    except Exception as e:
        # Catch any other unexpected errors
        return False, f"An unexpected error occurred: {e}"

# Function to Download and extract files
def get_and_extract(url, location, overwrite, basefolder=os.getcwd()):
    print('URL: ', url)
    element = ManifestItem(url,location,overwrite, basefolder)
    # this will return a tuple of root and extension
    split_tup = os.path.splitext(element.url)

    # extract the file name and extension
    url_base = split_tup[0]
    file_extension = split_tup[1]

    if os.path.exists(location):
        print("File exists...")
        print(location)
        if not element.overwrite:
            print("Overwrite flag set to FALSE")
            print("Existing file(s) will not be updated.")
            return
        else:
            print("Overwrite flag set to TRUE")
            print("Existing file(s) will be updated/overwritten")
    match element.item_type:
        case 'HF_FILE':
            if element.overwrite:
                print("Deleting existing file: " + element.location)
                if os.path.isfile(element.location):
                    try:
                        os.remove(element.location)
                    except OSError as e:
                        print("Error: %s - %s." % (e.filename, e.strerror))
                        
            repo_id = element.repo_id
            f_name = element.url_parts.path.split('/blob/main/')[1]
            l_dir = element.local_path + '/' + f_name

            enable_progress_bars()
            #hf_hub_download(repo_id=element.repo_id, filename=f_name) #download to the local cache first
            hf_hub_download(repo_id=element.repo_id,filename=f_name,local_dir=l_dir) #download to local directory, will used cached files
            #huggingface downloads download the directory, we'll need to fix this
            dir_root = element.local_path + '/' + f_name.split('/')[0]
            if os.path.exists(dir_root):
                if not os.path.isfile(dir_root):    
                    #os.rename(dir_root, element.local_path+"/delete")
                    shutil.move(element.local_path +'/'+ f_name +'/'+ f_name, element.local_path + '/file.tmp')
                    shutil.rmtree(element.local_path+'/'+f_name.split('/')[0])
                    shutil.move(element.local_path + '/file.tmp', element.location)
        case 'CM_MANAGER_INSTALL':
            subprocess.call([sys.executable, './ComfyUI/custom_nodes/ComfyUI-Manager/cm-cli.py','install',element.url])

        case 'WINGET_INSTALL':
            print(f"Installing winget install using: 'winget install {element.url}'")
            try:
                # Construct the winget install command
                command = f'winget install --id {element.url}'

                # Notify the user
                print(f"Installing {element.url} using winget. Please respond to any prompts in the terminal.")

                # Run the command, keeping the terminal interactive
                result = subprocess.run(
                    command,
                    shell=True,  # Required for winget to run in the shell
                    check=False,  # Don't raise an exception on non-zero exit codes
                    text=True,    # Ensure output is treated as text
                    stdout=sys.stdout,  # Direct output to terminal
                    stderr=sys.stderr,  # Direct errors to terminal
                    stdin=sys.stdin     # Allow user input for prompts
                )

                # Check the result
                if result.returncode == 0:
                    print(f"Successfully installed {element.url}.")
                    return True
                else:
                    print(f"Failed to install {element.url}. Exit code: {result.returncode}")
                    return False

            except subprocess.SubprocessError as e:
                print(f"An error occurred while running winget: {e}")
                return False


        case 'HF_REPO':
            include_list = ['*.*']
            exclude_list = ['*.md']
            enable_progress_bars()
            #check url querystring for inclusion/exclusions
            if len(element.url_parts.query): #If the query portion is not empty
                query_args=element.url_parts.query.split('&')
                for arg in query_args:
                    filter_key, filter_mask = arg.split('=')
                    filter_key = filter_key.lower().replace(' ','') #convert to lower and remove any whitespace
                    filter_mask = filter_mask.replace(' ','') #remove any whitespace
                    
                    
                    match filter_key:
                        case 'exclude':
                            exclude_list = exclude_list+filter_mask.split(',')

                        case 'include':
                            include_list = filter_mask.split(',')

            snapshot_download(repo_id=element.repo_id, local_dir=element.location, allow_patterns=include_list, ignore_patterns=exclude_list)

        case 'GH_FILE':
            stream_dl(element.url, element.location)

        case 'GH_REPO':
            manage_package(element.repo_id,element.url,element.location)

        case 'UNDEFINED' | 'LOCAL_FILE':
            match file_extension:
                case '.zip':
                    if element.item_type == 'LOCAL_FILE':
                        z = zipfile.ZipFile(element.url, mode='r')
                    else:
                        # Get the URL
                        r = requests.get(url)
    
                        print('Extracting to: ', location)
    
                        # Stream the URL into the Zip Decompressor
                        z= zipfile.ZipFile(io.BytesIO(r.content))
                        
                    z.extractall(location)
                    print('Extraction complete.\n')

                # case '.7z':
                    # # 7z needs to save the file first
                    # if element.item_type == 'LOCAL_FILE':
                        # archive = py7zr.SevenZipFile(element.url, mode='r')
                    # else:
                        # temp_store = './'+url.rsplit('/',1)[1]
                        # stream_dl(url, temp_store)
                        # archive = py7zr.SevenZipFile(temp_store, mode='r')
                    # archive.extractall(path=location)
                    # archive.close()
                case '.py':
                    if element.item_type == 'LOCAL_FILE':
                        print(f"Executing local Python script: {element.url}")
                        try:
                            # Run the script as a subprocess with Popen for real-time output
                            process = subprocess.Popen(
                                [sys.executable, element.url],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,  # Combine stderr with stdout
                                text=True,
                                bufsize=1,
                                universal_newlines=True
                            )
                            # Stream output in real-time
                            while True:
                                line = process.stdout.readline().strip()
                                if not line and process.poll() is not None:
                                    break
                                if line:
                                    print(line)  # Print output to console
                            # Wait for the process to complete and get the return code
                            return_code = process.wait()
                            print(f"Script {element.url} exited with code {return_code}")
                            if return_code != 0:
                                print(f"Warning: Script {element.url} failed with exit code {return_code}")
                            # Continue processing CSV regardless of exit code
                        except subprocess.SubprocessError as e:
                            print(f"Error executing {element.url}: {e}")
                    else:
                        stream_dl(url, location)

                # Not an archive
                case _:
                    if element.item_type == 'LOCAL_FILE':
                        shutil.copyfile(element.url,element.location)
                    else:
                        stream_dl(url,location)


#If the custom CSV file is a relative filepath, convert it to absolute.
#This file pathpath must be set BEFORE changing the working directory.
manifestFile = './install_files.csv'
if not os.path.isabs(manifestFile):
    manifestFile=os.path.abspath(manifestFile)

#Change the working directory to the install folder directory
installFolder = os.path.normpath(os.path.join(os.getcwd(),'ComfyUI_windows_portable'))
print('Change the working folder to: '+installFolder)
set_persistent_env_var('COMFYUI_BASE',installFolder)
os.chdir(installFolder)

    
baseFolder = os.path.normpath(os.path.dirname(os.path.abspath(__file__)))

# Now get the ComfyManager from it's git repo
# repository_url = "https://github.com/ltdrdata/ComfyUI-Manager.git"
# Where ComfyManager will go
# destination_folder = "./ComfyUI/custom_nodes/ComfyUI-Manager"
# Create the target directory
# os.makedirs(os.path.dirname(destination_folder), exist_ok=True)
# Cloning the repository
# manage_package('ComfyUI-Manager',repository_url, destination_folder)
# subprocess.call([sys.executable, '-m', 'pip', 'install','-r','./ComfyUI/custom_nodes/ComfyUI-Manager/requirements.txt'])

# Load the CSV file and iterate over each line
print(manifestFile)

user_profile = os.environ.get('USERPROFILE')

# Retrieve the token from the HF_TOKEN environment variable
token = os.environ.get('HF_TOKEN')
if not token:
    print("HF_TOKEN is not set...set the HF_TOKEN environment variable with a valid token and restart Setup")
    sys.exit("!!! SETUP FAILED:  Please set the HF_TOKEN environment variable and restart Setup")

else:
    is_valid, result = check_hf_token_validity(token)
    if is_valid:
        print(f"Token is valid! User info: {result}")
    else:
        print(f"Token is invalid or an error occurred: {result}")
        print("HF_TOKEN value is not valid, please check the HF_TOKEN environment variable is a valid huggingface token and restart Setup")
        sys.exit("!!! SETUP FAILED:  Please verify the HF_TOKEN environment variable is valid and restart Setup")

#List of potentially gated models to verify if the user currently has access
model_list = [{"model_name":"black-forest-labs/FLUX.1-dev","filename":".gitattributes","token":token},
              {"model_name":"black-forest-labs/FLUX.1-Canny-dev","filename":".gitattributes","token":token},
              {"model_name":"black-forest-labs/FLUX.1-Depth-dev","filename":".gitattributes","token":token},
              {"model_name":"black-forest-labs/FLUX.1-dev-onnx","filename":".gitattributes","token":token},
              {"model_name":"black-forest-labs/FLUX.1-Canny-dev-onnx","filename":".gitattributes","token":token},
              {"model_name":"black-forest-labs/FLUX.1-Depth-dev-onnx","filename":".gitattributes","token":token},
              ]
non_accessible_models = []

for model in model_list:
    print(f"Checking model: {model['model_name']}")
    result = check_model_access(model)
    if result[0]:
        print(f"Model access: {model['model_name']} is accessible")
    else:
        print(f"Model access: {model['model_name']} is not accessible")
        print(result[1])
        non_accessible_models.append(model["model_name"])

if len(non_accessible_models) > 0:
    print("The following models are not accessible:")
    for model in non_accessible_models:
        print(f"\t{model}: https://huggingface.co/{model}")
    print("Please accept the use license for the listed models and restart Setup")
    sys.exit("!!! SETUP FAILED:  Please accept the use license for ALL listed models and restart Setup")


with open(manifestFile, mode ='r')as file:
    csvFile = csv.reader(file)
    for lines in csvFile:
        get_and_extract(lines[0], lines[1], lines[2], baseFolder)


#Install Complete
comfyui_path = Path('./ComfyUI')
#print(f'ComfyUI_PATH = {comfyui_path}')
comfyui_python_path = Path('./python_embeded')
#print(f'ComfyUI_PYTHON = {comfyui_python_path}')
print('Installation is complete....')
print('***********************************************************************')
print('The path information below can be used to setup the ComfyUI BlenderAI node Addon in Blender 3D')
print('')
print(f'ComfyUI Path =  {comfyui_path.resolve()}\\')
print(f'Python Path =  {comfyui_python_path.resolve()}\\')
print('***********************************************************************')
print('Press any key to finish...')
msvcrt.getch() # wait for a key press