from git import Repo
import os, shutil
from pathlib import Path

def copy_file(src, dst):
    try:
        if not os.path.exists(src):
            print(f"Error: Source file not found at '{src}'"); return
        if not os.path.isfile(src):
            print(f"Error: Source path '{src}' is not a file."); return
        shutil.copy2(src, dst)
        print(f"Successfully copied '{src}' to '{dst}'")
    except FileNotFoundError: print(f"Error: One of the paths specified was not found.")
    except PermissionError: print(f"Error: Permission denied. Check file permissions for '{src}' or '{dst}'.")
    except OSError as e: print(f"An operating system error occurred: {e}")
    except Exception as e: print(f"An unexpected error occurred: {e}")

# Get Blender config directory
user_profile = os.environ.get('USERPROFILE')
blender_path = Path(user_profile, 'AppData/Roaming/Blender Foundation/Blender')

blender_versions = []

# Get the current working directory
current_directory = os.getcwd()

# Print the current working directory
print("Current working directory:", current_directory)

if user_profile:
    blender42_path = Path(user_profile, 'AppData/Roaming/Blender Foundation/Blender/4.2/extensions/user_default')

    if not blender_path.exists():
        try:
            blender42_path.mkdir(parents=True, exist_ok=True)  # Create the directory and its parents
            print(f"Directory created: {blender42_path}")
        except OSError as e:
            print(f"Error creating directory: {e}")
    else:
        print(f"Directory already exists: {blender42_path}")
else:
    print("USERPROFILE environment variable not found.")
    
# Ensure the directory exists
if blender_path.exists():
    subdirs = [d.name for d in blender_path.iterdir() if d.is_dir()]
    
    for dir in subdirs:
        try:
            float(dir)  # Check if the folder name is a valid number (Blender version)
            blender_versions.append(dir)
        except ValueError:
            pass  # Ignore folders that aren't numeric

    for ver in blender_versions:
        addon_path = Path(blender_path, ver, 'extensions/user_default/ComfyUI-BlenderAI-node')

        repo_url = 'https://github.com/AIGODLIKE/ComfyUI-BlenderAI-node.git'
        branch_name = 'MIT-1.5.7'

        if not addon_path.exists():
            Repo.clone_from(repo_url, addon_path, branch=branch_name)
            print(f'ComfyUI-Blender-AI addon installed to: {addon_path}')
            #pref_new = os.path.normpath(os.path.join(current_directory,'../package/patch_files/preference.py'))
            #pref_dest = os.path.normpath(os.path.join(addon_path,'preference.py'))

            #print(f"\n--- Attempting to copy {pref_new} to destination_folder {pref_dest} / ---")
            #copy_file(pref_new, pref_dest)
	
        else: 
            print(f'Found an existing addon installation at: {addon_path}.')
            print('Add-on will not be installed.')
else:
    print(f'Blender directory not found: {blender_path}')



