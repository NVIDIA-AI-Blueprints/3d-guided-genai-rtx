import sys
import subprocess


subprocess.call([sys.executable, '-m', 'pip',  'install',  '-r', './ComfyUI/custom_nodes/NIMnodes/requirements.txt'])



