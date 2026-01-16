import shutil
import os
documents_path = os.path.join(os.environ["USERPROFILE"], "Documents")

src = "../package/Blender"
dst = os.path.join(documents_path,"Blender")

os.makedirs(dst, exist_ok=True)  # Ensure the destination exists

for item in os.listdir(src):
    s = os.path.join(src, item)
    d = os.path.join(dst, item)
    if os.path.isdir(s):
        shutil.copytree(s, d, dirs_exist_ok=True)
    else:
        shutil.copy2(s, d)  # Preserve metadata