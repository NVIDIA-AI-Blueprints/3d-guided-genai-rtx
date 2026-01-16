import argparse
import json
import os
import sys
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.manifest_handler import ManifestHandler
from core.package_manager import PackageManager
from core.comfyui_installer import ComfyUIInstaller


def extract_manifest_from_zip(zip_path: Path, temp_dir: Path, comfy_path: Optional[Path] = None) -> tuple[Path, Optional[Path]]:
    """
    Extract manifest.json from ZIP package.
    Also extracts InstallTemp folder if present and merges ComfyUI folder if present.

    Args:
        zip_path: Path to the ZIP package
        temp_dir: Temporary directory for extraction
        comfy_path: ComfyUI installation path (for merging ComfyUI folder from package)

    Returns:
        tuple: (manifest_path, install_temp_path)
            - manifest_path: Path to extracted manifest file
            - install_temp_path: Path to extracted InstallTemp folder, or None if not present
    """
    print(f"[1/3] Extracting manifest from package...")

    # Create temporary extraction directory
    temp_dir.mkdir(parents=True, exist_ok=True)

    install_temp_path = None

    with zipfile.ZipFile(zip_path, 'r') as zf:
        # Look for manifest.json at root or in common locations
        manifest_locations = ['manifest.json', 'manifest.yaml', 'manifest.yml']
        manifest_file = None

        for loc in manifest_locations:
            if loc in zf.namelist():
                manifest_file = loc
                break

        if not manifest_file:
            raise FileNotFoundError("No manifest.json/yaml found in ZIP package")

        # Extract manifest
        zf.extract(manifest_file, temp_dir)
        manifest_path = temp_dir / manifest_file

        print(f"✓ Manifest extracted to: {manifest_path}")

        # Check for InstallTemp folder and extract it
        install_temp_files = [f for f in zf.namelist() if f.startswith('InstallTemp/')]
        if install_temp_files:
            print(f"Found InstallTemp folder in package - extracting {len(install_temp_files)} files...")
            install_temp_path = temp_dir / "InstallTemp"

            # Extract all InstallTemp files
            for file in install_temp_files:
                zf.extract(file, temp_dir)

            print(f"✓ InstallTemp extracted to: {install_temp_path}")

        # Check for ComfyUI folder and merge it into installation
        comfyui_files = [f for f in zf.namelist() if f.startswith('ComfyUI/') and not f.startswith('ComfyUI/.')]
        if comfyui_files and comfy_path:
            print(f"Found ComfyUI folder in package - merging {len(comfyui_files)} files...")

            for file in comfyui_files:
                # Extract to temp first
                zf.extract(file, temp_dir)

                # Determine source and destination
                source_file = temp_dir / file
                # Remove 'ComfyUI/' prefix to get relative path
                relative_path = Path(file).relative_to('ComfyUI')
                dest_file = comfy_path / relative_path

                # Skip directories (they're created automatically)
                if source_file.is_file():
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    import shutil
                    shutil.copy2(source_file, dest_file)

            print(f"✓ ComfyUI folder merged into {comfy_path}")

        return manifest_path, install_temp_path


def main():
    """Main installer entry point."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(
        description="ComfyUI Modular Installer - Install models, custom nodes, and assets from manifest files."
    )
    parser.add_argument("-c", "--comfy_path", type=str,
                        help="Path to ComfyUI installation folder (default: auto-install to ~/ComfyUI_BP/ComfyUI)")
    parser.add_argument("-m", "--manifest", type=str,
                        help="Path to manifest.json/yaml file or ZIP package containing manifest")
    parser.add_argument("--no-auto-install", action="store_true",
                        help="Disable automatic ComfyUI installation if not found")
    parser.add_argument("--install-path", type=str,
                        help="Custom installation path for ComfyUI portable (default: ~/ComfyUI_BP)")
    parser.add_argument("--skip-blender", action="store_true",
                        help="Skip Blender 4.5 LTS installation (Windows only)")
    parser.add_argument("--gui", action="store_true",
                        help="Launch graphical installer interface")
    parser.add_argument("-l", "--log", nargs='?', const=True, default=False,
                        help="Enable logging to file")
    parser.add_argument("-t", "--temp_path", type=str,
                        help="Alternate temporary directory for extraction")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Force re-download/installation of all items")
    parser.add_argument("--required-only", action="store_true",
                        help="Only install items marked as required")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip checksum verification for downloads")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview actions without executing downloads")
    parser.add_argument("--sequential", action="store_true",
                        help="Disable parallel downloads (use sequential mode)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of parallel download workers (default: 4)")
    parser.add_argument("--no-resume", action="store_true",
                        help="Disable resume capability for interrupted downloads")
    parser.add_argument("--list-contents", action="store_true",
                        help="List manifest contents without installing")
    parser.add_argument("--cleanup", action="store_true",
                        help="Clean up partial download files and exit")
    parser.add_argument("--keep-extracted", action="store_true",
                        help="Keep extracted temporary files for debugging (don't auto-cleanup)")

    args = parser.parse_args()

    # === FROZEN EXECUTABLE DETECTION ===
    # If running as a frozen executable (PyInstaller, cx_Freeze, etc.), force GUI mode
    if getattr(sys, 'frozen', False):
        # Check for bundled package.zip in two locations:
        # 1. Inside the executable (PyInstaller --add-data)
        # 2. External file alongside the executable
        bundled_package = None

        if hasattr(sys, '_MEIPASS'):
            # PyInstaller extracts bundled data to _MEIPASS temp directory
            internal_package = Path(sys._MEIPASS) / "package.zip"
            if internal_package.exists():
                bundled_package = internal_package

        if not bundled_package:
            # Check for external package.zip alongside the executable
            exe_dir = Path(sys.executable).parent
            external_package = exe_dir / "package.zip"
            if external_package.exists():
                bundled_package = external_package

        if not args.gui:
            if bundled_package:
                print(f"Detected frozen executable with bundled package.zip - launching GUI mode...")
            else:
                print("Detected frozen executable - launching GUI mode...")
            args.gui = True

    # === GUI MODE ===
    if args.gui:
        try:
            from core.installer_gui import run_installer_gui
            result = run_installer_gui()
            return 0 if result and result.get('success') else 1
        except ImportError:
            print("❌ ERROR: Qt bindings not found. Please install PySide6:")
            print("   pip install PySide6")
            return 1
        except Exception as e:
            print(f"❌ ERROR: GUI failed to launch: {e}")
            return 1

    if not args.manifest and not args.cleanup:
        parser.error("--manifest (-m) is required unless using --cleanup")

    # === COMFYUI INSTALLATION/DETECTION ===
    install_path = Path(args.install_path) if args.install_path else ComfyUIInstaller.DEFAULT_INSTALL_PATH
    comfyui_installer = ComfyUIInstaller(install_path=install_path)

    # Determine ComfyUI path
    if args.comfy_path:
        # User specified path - check for embedded Python
        comfy_path = Path(args.comfy_path).resolve()

        # Try to find embedded Python at the specified path
        # Need to go up to the install root to check for python_embeded
        install_root = comfy_path.parent if comfy_path.name == "ComfyUI" else comfy_path

        possible_python_paths = [
            install_root / "python_embeded" / "python.exe",
            install_root / "python_embedded" / "python.exe",
            comfy_path / ".." / "python_embeded" / "python.exe",
            comfy_path / ".." / "python_embedded" / "python.exe",
        ]

        python_executable = None
        for py_path in possible_python_paths:
            resolved_path = py_path.resolve()
            if resolved_path.exists():
                python_executable = resolved_path
                print(f"✓ Found embedded Python: {python_executable}")
                break

        if not python_executable:
            print(f"⚠ No embedded Python found at {comfy_path}")
            print(f"  Will use system Python for pip installations: {sys.executable}")
            print(f"  Note: Packages may not be visible to ComfyUI")
            python_executable = None  # Will fall back to sys.executable in ManifestHandler
    else:
        # Auto-detect or install ComfyUI
        print("\n" + "=" * 60)
        print("COMFYUI INSTALLATION CHECK")
        print("=" * 60)

        if comfyui_installer.check_existing_installation():
            # Existing installation found
            print(f"✓ ComfyUI found at: {install_path}")

            # Get installation info
            info = comfyui_installer.get_installation_info()
            comfy_path = info['comfyui_path']
            python_executable = info['python_executable']

            if python_executable:
                print(f"✓ Embedded Python found: {python_executable}")

            # Prompt user for action
            if not args.cleanup:
                user_choice = ComfyUIInstaller.prompt_user_action()
                if user_choice == 2:
                    print("\nInstallation cancelled by user.")
                    return 0
                # Choice 1: Continue with existing installation

        else:
            # No installation found
            print(f"⊘ ComfyUI not found at: {install_path}")

            if args.no_auto_install:
                print("❌ ERROR: ComfyUI not found and auto-install is disabled")
                print(f"   Please install ComfyUI manually or remove --no-auto-install flag")
                return 1

            # Prompt to install
            print("\nWould you like to download and install ComfyUI portable? (y/n): ", end="")
            try:
                response = input().strip().lower()
                if response != 'y':
                    print("\nInstallation cancelled by user.")
                    return 0
            except (KeyboardInterrupt, EOFError):
                print("\n\nInstallation cancelled by user.")
                return 0

            # Install ComfyUI
            print("\n" + "=" * 60)
            print("INSTALLING COMFYUI")
            print("=" * 60)
            success, message = comfyui_installer.install_comfyui()
            if not success:
                print(f"❌ ERROR: {message}")
                return 1

            print(f"✓ {message}")

            # Get installation info after install
            info = comfyui_installer.get_installation_info()
            comfy_path = info['comfyui_path']
            python_executable = info['python_executable']

            if python_executable:
                print(f"✓ Embedded Python: {python_executable}")

        print("=" * 60 + "\n")

    # Validate ComfyUI path
    if not comfy_path or not comfy_path.exists():
        print(f"❌ ERROR: ComfyUI path does not exist: {comfy_path}")
        return 1

    # === BLENDER INSTALLATION (Windows only) ===
    if not args.skip_blender and sys.platform == "win32":
        print("\n" + "=" * 60)
        print("BLENDER INSTALLATION CHECK")
        print("=" * 60)

        if comfyui_installer.check_blender_installed():
            print("✓ Blender 4.5 LTS is already installed")
        else:
            print("⊘ Blender 4.5 LTS not found")
            print("\nBlender is used for 3D object generation in ComfyUI.")
            print("Would you like to install Blender 4.5 LTS? (y/n): ", end="")
            try:
                response = input().strip().lower()
                if response == 'y':
                    print("\n" + "=" * 60)
                    print("INSTALLING BLENDER")
                    print("=" * 60)
                    success, message = comfyui_installer.install_blender()
                    if success:
                        print(f"✓ {message}")
                    else:
                        print(f"⚠ {message}")
                        print("  You can continue without Blender or install it manually later.")
                else:
                    print("\nSkipping Blender installation.")
            except (KeyboardInterrupt, EOFError):
                print("\n\nSkipping Blender installation.")

        print("=" * 60 + "\n")
    else:
        # Blender installation skipped
        if args.skip_blender:
            print("⊘ Skipping Blender installation (--skip-blender flag used)")
        elif sys.platform != "win32":
            print("⊘ Skipping Blender installation (not supported on this platform)")

    # === CLEANUP MODE ===
    if args.cleanup:
        print("Cleaning up partial downloads...")
        handler = ManifestHandler(
            manifest_path=comfy_path / "manifest.json",  # Dummy path
            comfy_path=comfy_path,
            resume_downloads=True
        )
        handler.cleanup_partial_downloads()
        return 0

    # === LOG FILE ===
    log_file = None
    if args.log is not False:
        manifest_basename = Path(args.manifest).stem
        timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
        log_file = Path(args.log).resolve() if args.log is not True else Path(f"{manifest_basename}_install_{timestamp}.txt").resolve()
        if log_file.is_dir():
            log_file = log_file / f"{manifest_basename}_install_{timestamp}.txt"
        print(f"Logging to: {log_file}")
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"Installation started: {datetime.now()}\n")

    manifest_path = Path(args.manifest).resolve()
    temp_dir = None
    package_manager = None

    try:
        print("\n" + "=" * 60)
        print("ComfyUI Modular Installer")
        print("=" * 60)
        print(f"ComfyUI Path: {comfy_path}")
        print(f"Manifest: {manifest_path}")
        print("=" * 60 + "\n")

        # === HANDLE MANIFEST SOURCE ===
        install_temp_path = None  # Will be set if InstallTemp folder exists in ZIP
        if manifest_path.suffix.lower() == '.zip':
            # Extract manifest from ZIP package
            temp_dir = Path(args.temp_path) / f"manifest_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}" if args.temp_path else comfy_path / f"temp_manifest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            manifest_path, install_temp_path = extract_manifest_from_zip(manifest_path, temp_dir, comfy_path)

            # Also use PackageManager to extract bundled files if present
            print("\n[2/3] Extracting bundled files from package...")
            package_manager = PackageManager(
                zip_path=Path(args.manifest).resolve(),
                comfy_path=comfy_path,
                temp_path=args.temp_path,
                extract_minimal=False,
                force_extract=args.force,
                log_file=log_file
            )
            # PackageManager will handle extraction of bundled files
            try:
                package_manager.extract_zip()
                print("✓ Bundled files extracted")
            except Exception as e:
                print(f"⚠ No bundled files in package or extraction failed: {e}")

        elif manifest_path.suffix.lower() in ['.json', '.yaml', '.yml']:
            print(f"Using manifest: {manifest_path}")
        else:
            raise ValueError("Manifest must be .json, .yaml, .yml, or .zip file")

        # === INITIALIZE MANIFEST HANDLER ===
        print("\n[2/3] Loading manifest...")
        handler = ManifestHandler(
            manifest_path=manifest_path,
            comfy_path=comfy_path,
            log_file=log_file,
            max_workers=args.workers,
            resume_downloads=not args.no_resume,
            python_executable=python_executable,
            install_temp_path=install_temp_path
        )

        # Load and validate manifest
        handler.load_manifest()
        handler.validate_manifest()

        # Ensure prerequisites (git, git-lfs) are available
        handler.ensure_prerequisites()

        # Check for gated models and prompt for HF token if needed
        if handler.has_gated_models() and not handler.hf_token:
            print("\n" + "=" * 60)
            print("⚠ HUGGINGFACE TOKEN REQUIRED")
            print("=" * 60)
            print("This package includes gated models that require a HuggingFace token.")
            print("\nTo get a token:")
            print("  1. Visit https://huggingface.co/settings/tokens")
            print("  2. Create a new token with 'Read' permission")
            print("  3. Accept the license for gated models on HuggingFace")
            print("  4. Paste the token below")
            print("\nAlternatively, set the HF_TOKEN environment variable.")
            print("=" * 60)

            try:
                token = input("\nEnter your HuggingFace token (or press Enter to skip): ").strip()
                if token:
                    handler.set_hf_token(token)
                    print("✓ HuggingFace token set")
                else:
                    print("⚠ No token provided - gated models may fail to download")
            except (KeyboardInterrupt, EOFError):
                print("\n⚠ No token provided - gated models may fail to download")

        # Print summary
        handler.print_summary()

        # === LIST CONTENTS MODE ===
        if args.list_contents:
            print("\n" + "=" * 60)
            print("MANIFEST ITEMS")
            print("=" * 60)
            for item in handler.manifest['items']:
                print(f"\n{item['name']}")
                print(f"  Type: {item['type']}")
                print(f"  Source: {item['source']}")
                if 'path' in item:
                    print(f"  Destination: {item['path']}")
                if item.get('required'):
                    print(f"  Required: Yes")
                if item.get('size_mb'):
                    print(f"  Size: {item['size_mb']:.1f} MB")
            print("=" * 60 + "\n")
            return 0

        # === DOWNLOAD/INSTALL ITEMS ===
        print("\n[3/3] Installing items...")
        handler.download_items(
            skip_existing=not args.force,
            required_only=args.required_only,
            verify_checksums=not args.no_verify,
            dry_run=args.dry_run,
            parallel=not args.sequential
        )

        if args.dry_run:
            print("\n✓ Dry run completed (no changes made)")
            return 0

        # === INSTALLATION SUMMARY ===
        print("\n" + "=" * 60)
        print("INSTALLATION COMPLETE")
        print("=" * 60)

        package_info = handler.manifest.get('package', {})
        package_name = package_info.get('name', 'unknown')

        print(f"Package: {package_name}")
        if package_info.get('version'):
            print(f"Version: {package_info['version']}")
        print(f"ComfyUI Path: {comfy_path}")

        # Print what was downloaded/installed
        if handler.downloaded_items:
            print(f"\n✓ Items installed: {len(handler.downloaded_items)}")
            for item in handler.downloaded_items[:5]:  # Show first 5
                print(f"  - {item['name']}")
            if len(handler.downloaded_items) > 5:
                print(f"  ... and {len(handler.downloaded_items) - 5} more")

        if handler.skipped_items:
            print(f"\n⊘ Items skipped (already up-to-date): {len(handler.skipped_items)}")

        # Check if restart is needed
        if handler.custom_nodes_were_downloaded():
            print(f"\n⚠️  IMPORTANT: Restart ComfyUI to load new custom nodes")

        print("=" * 60 + "\n")

        if log_file:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\nInstallation completed: {datetime.now()}\n")
                f.write(f"Package: {package_name}\n")

    except KeyboardInterrupt:
        print("\n\nInstallation interrupted by user.")
        if log_file:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Installation interrupted: {datetime.now()}\n")
        return 1
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
        if log_file:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Cleanup temporary files (unless --keep-extracted flag is set)
        if temp_dir and temp_dir.exists():
            if args.keep_extracted:
                print(f"\n⚠ Keeping extracted files for debugging: {temp_dir}")
                print("  Use --cleanup to remove them later")
            else:
                print("\nCleaning up temporary files...")
                import shutil
                try:
                    shutil.rmtree(temp_dir)
                    print("✓ Cleanup complete")
                except Exception as e:
                    print(f"⚠ Cleanup warning: {e}")

        if log_file:
            print(f"\nLog file: {log_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
