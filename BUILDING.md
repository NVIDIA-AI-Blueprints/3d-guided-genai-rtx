# Building Executable Installers

This document explains how to package 3DAI-Guided-BP-Installer as a standalone executable with bundled resources.

## Overview

3DAI-Guided-BP-Installer can be packaged in three ways:

1. **Standalone executable** - User selects manifest file manually
2. **Executable + external package.zip** - Package file alongside the .exe
3. **Fully bundled executable** - Package embedded inside the .exe (single file)

## Prerequisites

Install PyInstaller:
```bash
pip install pyinstaller
```

## Method 1: Standalone Executable

Creates a single .exe file. Users must select their own manifest/package file.

```bash
pyinstaller --onefile --windowed --name="3DAI-Guided-BP-Installer" 3DAI-Guided-BP-Installer.py
```

**Output:** `dist/3DAI-Guided-BP-Installer.exe`

**Usage:** User runs .exe and browses to select manifest file.

---

## Method 2: Executable + External Package

Creates .exe that automatically uses `package.zip` if found in the same directory.

**Step 1:** Build the executable
```bash
pyinstaller --onefile --windowed --name="3DAI-Guided-BP-Installer" 3DAI-Guided-BP-Installer.py
```

**Step 2:** Distribute both files
```
MyInstaller/
├── 3DAI-Guided-BP-Installer.exe
└── package.zip
```

**Usage:** User downloads both files, runs .exe. The installer automatically detects and uses `package.zip`.

---

## Method 3: Fully Bundled (Recommended)

Creates a single .exe with package.zip embedded inside. **This is the recommended distribution method.**

**Step 1:** Create your package.zip with this structure:
```
package.zip
├── manifest.yaml
├── ComfyUI/
│   └── custom_nodes/
│       └── my_custom_node/
└── InstallTemp/
    └── models/
        └── my_model.safetensors
```

**Step 2:** Build with bundled package
```bash
# Windows
pyinstaller --onefile --windowed --add-data "package.zip;." --name="MyInstaller" 3DAI-Guided-BP-Installer.py

# Linux/Mac
pyinstaller --onefile --windowed --add-data "package.zip:." --name="MyInstaller" 3DAI-Guided-BP-Installer.py
```

**Output:** `dist/MyInstaller.exe` (single file, fully self-contained)

**Usage:** User downloads single .exe file and runs it. Everything is embedded!

---

## Advanced PyInstaller Options

### Add an Icon
```bash
pyinstaller --onefile --windowed --icon=installer.ico --add-data "package.zip;." 3DAI-Guided-BP-Installer.py
```

### Hide Console Window (Windows only)
```bash
pyinstaller --onefile --noconsole --add-data "package.zip;." 3DAI-Guided-BP-Installer.py
```

### Optimize Size
```bash
pyinstaller --onefile --windowed --add-data "package.zip;." --strip --exclude-module tkinter 3DAI-Guided-BP-Installer.py
```

### Add Multiple Data Files
```bash
pyinstaller --onefile --windowed \
  --add-data "package.zip;." \
  --add-data "logo.png;." \
  --add-data "README.txt;." \
  3DAI-Guided-BP-Installer.py
```

---

## Package.zip Structure

Your `package.zip` can contain:

### Required
- **manifest.yaml** or **manifest.json** - Installation instructions

### Optional
- **ComfyUI/** - Files to merge with ComfyUI installation
  - `ComfyUI/custom_nodes/` - Custom nodes (auto-merged)
  - `ComfyUI/models/` - Models (auto-merged)
  - `ComfyUI/input/` - Input files (auto-merged)

- **InstallTemp/** - Files to install according to manifest
  - Reference with `source: install_temp` in manifest
  - Allows pre-bundling large models for offline install

### Example manifest.yaml
```yaml
name: My Complete Package
version: 1.0

resources:
  # Pre-bundled model (no download needed)
  - name: FLUX Model
    type: model
    source: install_temp
    source_path: models/flux1-dev.safetensors
    path: models/checkpoints/flux1-dev.safetensors
    path_base: comfyui
    required: true

  # Download from HuggingFace
  - name: T5 Encoder
    type: model
    source: huggingface
    repo: comfyanonymous/flux_text_encoders
    file: t5xxl_fp8_e4m3fn.safetensors
    path: models/text_encoders/t5xxl_fp8_e4m3fn.safetensors
    path_base: comfyui
    required: true
```

---

## Detection Behavior

When the executable runs, it checks for `package.zip` in this order:

1. **Inside the executable** (`sys._MEIPASS/package.zip`)
   - Created with `--add-data` flag
   - Single file distribution

2. **Alongside the executable** (`3DAI-Guided-BP-Installer.exe` directory)
   - External package.zip file
   - Two file distribution

3. **Manual selection**
   - No package.zip found
   - User browses to select manifest

---

## Testing Your Build

1. **Build the executable:**
   ```bash
   pyinstaller --onefile --windowed --add-data "package.zip;." 3DAI-Guided-BP-Installer.py
   ```

2. **Test it:**
   ```bash
   dist/3DAI-Guided-BP-Installer.exe
   ```

3. **Verify:**
   - GUI should launch automatically
   - Manifest field should show package.zip path
   - Browse button should be disabled
   - Installation should proceed using bundled package

---

## Distribution Checklist

- [ ] Create complete package.zip with manifest + resources
- [ ] Build executable with `--add-data` flag
- [ ] Test on clean machine (no Python installed)
- [ ] Verify package.zip is detected automatically
- [ ] Test installation completes successfully
- [ ] Check file sizes are reasonable
- [ ] Include README with usage instructions

---

## Troubleshooting

### "package.zip not found" error
- Ensure package.zip exists in project directory when building
- Check `--add-data` syntax matches your OS (`;` for Windows, `:` for Linux/Mac)

### Executable is too large
- Remove unnecessary dependencies: `--exclude-module tkinter`
- Use UPX compression: `--upx-dir=/path/to/upx`
- Consider Method 2 (external package.zip)

### "Qt platform plugin" error
- Try: `--hidden-import PySide6` or `--hidden-import PyQt5`
- Or bundle Qt plugins: `--add-binary "path/to/qt/plugins;qt_plugins"`

### Antivirus false positives
- Sign your executable with a code signing certificate
- Upload to VirusTotal and request whitelisting
- Use `--debug all` to help AV heuristics

---

## Example Build Script

Create `build.bat` (Windows) or `build.sh` (Linux/Mac):

```bash
#!/bin/bash
# Build 3DAI-Guided-BP-Installer with bundled package

echo "Building 3DAI-Guided-BP-Installer..."

# Clean previous builds
rm -rf build dist

# Build executable
pyinstaller \
  --onefile \
  --windowed \
  --name="3DAI-Guided-BP-Installer" \
  --add-data "package.zip;." \
  --icon=installer.ico \
  --strip \
  3DAI-Guided-BP-Installer.py

echo "Build complete: dist/3DAI-Guided-BP-Installer.exe"
echo "File size: $(du -h dist/3DAI-Guided-BP-Installer.exe)"
```

Make executable: `chmod +x build.sh`

Run: `./build.sh`
