# core/manifest_integration.py
"""
Manifest Handler Integration for ComfyUI Benchmark Framework

This module adds manifest support to the existing package_manager system.
It detects if a ZIP package contains a manifest file and processes it
before the smart extractor handles bundled content.

Integration is transparent and non-breaking with existing functionality.
"""

import os
import sys
import zipfile
import shutil
from pathlib import Path
from typing import Optional, Tuple, Dict

try:
    from .manifest_handler import ManifestHandler
    MANIFEST_HANDLER_AVAILABLE = True
except ImportError:
    # Fallback to absolute import for standalone usage
    try:
        from manifest_handler import ManifestHandler
        MANIFEST_HANDLER_AVAILABLE = True
    except ImportError:
        MANIFEST_HANDLER_AVAILABLE = False
        print("[manifest_integration] Warning: manifest_handler not found, manifest support disabled")


class ManifestIntegration:
    """
    Integrates manifest handler with the benchmark framework's package manager.
    
    Workflow:
    1. Check if ZIP contains manifest.yaml/manifest.json
    2. If yes:
       a. Extract manifest to temp
       b. Run manifest handler to download models
       c. Continue with smart extractor for bundled content
    3. If no:
       a. Use existing smart extractor logic
    """
    
    def __init__(self, 
                 zip_path: Path,
                 comfy_path: Path,
                 temp_dir: Path,
                 log_file: Optional[Path] = None):
        """
        Initialize manifest integration.
        
        Args:
            zip_path: Path to ZIP package
            comfy_path: Path to ComfyUI installation
            temp_dir: Temporary directory for extraction
            log_file: Optional log file
        """
        self.zip_path = Path(zip_path)
        self.comfy_path = Path(comfy_path)
        self.temp_dir = Path(temp_dir)
        self.log_file = log_file
        self.has_manifest = False
        self.manifest_path = None
        self.custom_nodes_installed = False  # NEW: Track custom nodes installation
        
    def _log(self, message: str):
        """Log message to console and file."""
        print(message)
        if self.log_file:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(message + '\n')
    
    def detect_manifest(self) -> bool:
        """
        Check if ZIP package contains a manifest file.
        
        Returns:
            True if manifest found, False otherwise
        """
        if not MANIFEST_HANDLER_AVAILABLE:
            return False
        
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                namelist = zf.namelist()
                
                # Look for manifest at root level
                for manifest_name in ['manifest.yaml', 'manifest.yml', 'manifest.json']:
                    if manifest_name in namelist:
                        self.has_manifest = True
                        self.manifest_path = manifest_name
                        self._log(f"[manifest_integration] Detected manifest: {manifest_name}")
                        return True
                        
        except Exception as e:
            self._log(f"[manifest_integration] Error detecting manifest: {e}")
            return False
        
        return False
    
    def extract_manifest(self) -> Optional[Path]:
        """
        Extract manifest file from ZIP to temp directory.
        
        Returns:
            Path to extracted manifest or None if not found
        """
        if not self.has_manifest or not self.manifest_path:
            return None
        
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                # Extract manifest
                zf.extract(self.manifest_path, self.temp_dir)
                extracted_path = self.temp_dir / self.manifest_path
                
                self._log(f"[manifest_integration] Extracted manifest to: {extracted_path}")
                return extracted_path
                
        except Exception as e:
            self._log(f"[manifest_integration] Error extracting manifest: {e}")
            return None
    
    def _detect_custom_nodes_in_manifest(self, manifest_file: Path) -> bool:
        """
        Check if manifest contains any custom nodes (git URLs).
        
        Args:
            manifest_file: Path to manifest file
            
        Returns:
            True if custom nodes detected, False otherwise
        """
        try:
            import yaml
            import json
            
            with open(manifest_file, 'r', encoding='utf-8') as f:
                if manifest_file.suffix in ['.yaml', '.yml']:
                    manifest = yaml.safe_load(f)
                else:
                    manifest = json.load(f)
            
            items = manifest.get('items', [])
            
            # Check for git URLs which indicate custom nodes
            for item in items:
                source_type = item.get('type', '').lower()
                url = item.get('url', '')
                
                # Git repos are typically custom nodes
                if source_type == 'git' or 'github.com' in url.lower() or '.git' in url.lower():
                    dest = item.get('dest', '')
                    # Confirm it's going to custom_nodes directory
                    if 'custom_nodes' in dest.lower():
                        self._log(f"[manifest_integration] Detected custom node: {item.get('name', url)}")
                        return True
            
            return False
            
        except Exception as e:
            self._log(f"[manifest_integration] Error checking for custom nodes: {e}")
            return False
    
    def process_manifest(self, 
                        skip_existing: bool = True,
                        verify_checksums: bool = True,
                        parallel_downloads: bool = True,
                        max_workers: int = 4) -> Tuple[bool, Optional[Dict]]:
        """
        Process manifest file to download required resources.
        Includes interactive retry logic for gated models/missing tokens.
        """
        if not MANIFEST_HANDLER_AVAILABLE:
            self._log("[manifest_integration] Manifest handler not available")
            return False, None
        
        # Extract manifest
        manifest_file = self.extract_manifest()
        if not manifest_file:
            self._log("[manifest_integration] Failed to extract manifest")
            return False, None
        
        # Check if manifest contains custom nodes
        has_custom_nodes = self._detect_custom_nodes_in_manifest(manifest_file)
        
        self._log("\n" + "="*60)
        self._log("PROCESSING MANIFEST-BASED PACKAGE")
        self._log("="*60)
        
        try:
            # Initialize manifest handler
            handler = ManifestHandler(
                manifest_path=manifest_file,
                comfy_path=self.comfy_path,
                log_file=self.log_file,
                max_workers=max_workers,
                resume_downloads=True
            )
            
            # Load and validate manifest
            handler.load_manifest()
            handler.validate_manifest()
            
            # Show summary
            handler.print_summary()
            
            # Get manifest config if present
            manifest_config = handler.manifest.get('config', {})
            
            # --- RETRY LOOP FOR GATED MODELS ---
            max_retries = 3
            attempt = 0
            download_success = False

            while attempt < max_retries:
                try:
                    self._log(f"\n[manifest_integration] Starting manifest downloads (Attempt {attempt+1}/{max_retries})...")
                    
                    handler.download_items(
                        skip_existing=skip_existing,
                        required_only=False,
                        verify_checksums=verify_checksums,
                        dry_run=False,
                        parallel=parallel_downloads
                    )
                    download_success = True
                    break # Success, exit loop
                
                except Exception as e:
                    err_str = str(e)
                    # Check for Gated Model / Missing Token errors
                    # This catches the specific error raised in manifest_handler.py or generic 401/403s
                    if "HF_TOKEN" in err_str or "gated model" in err_str or "401" in err_str or "403" in err_str:
                        self._log(f"[manifest_integration] ⚠️ Authentication required: {e}")
                        
                        # Dynamically import GUI dialog to avoid circular imports
                        try:
                            from .gui import get_hf_token_dialog
                            new_token = get_hf_token_dialog()
                            
                            if new_token:
                                self._log("[manifest_integration] Token received from user. Retrying...")
                                os.environ["HF_TOKEN"] = new_token
                                handler.hf_token = new_token # Update existing handler instance
                                attempt += 1
                                continue
                            else:
                                self._log("[manifest_integration] Token request cancelled by user.")
                                raise e # User cancelled, re-raise original error
                        except ImportError:
                            self._log("[manifest_integration] GUI unavailable for token input.")
                            raise e
                    else:
                        # Not an auth error, re-raise immediately
                        raise e

            if not download_success:
                return False, None

            # New: Only set flag if custom nodes were ACTUALLY downloaded (not skipped)
            if handler.custom_nodes_were_downloaded():
                self.custom_nodes_installed = True
                self._log("[manifest_integration] ✅ Custom nodes installed via manifest")
            else:
                self.custom_nodes_installed = False
                if has_custom_nodes:
                    self._log("[manifest_integration] ⊘ Custom nodes already up-to-date, no restart needed")
            
            self._log("[manifest_integration] ✅ Manifest processing complete!")
            self._log("="*60 + "\n")
            
            return True, manifest_config
            
        except Exception as e:
            self._log(f"[manifest_integration] ❌ Error processing manifest: {e}")
            # Do not print stack trace for simple token errors to keep log clean
            if "HF_TOKEN" not in str(e):
                import traceback
                traceback.print_exc()
            return False, None
    
    def get_baseconfig_from_manifest(self) -> Optional[Dict]:
        """
        Get NUM_INSTANCES and GENERATIONS from manifest config.
        
        Returns:
            Dictionary with 'NUM_INSTANCES' and 'GENERATIONS' or None
        """
        if not self.has_manifest or not MANIFEST_HANDLER_AVAILABLE:
            return None
        
        try:
            manifest_file = self.temp_dir / self.manifest_path
            if not manifest_file.exists():
                manifest_file = self.extract_manifest()
                if not manifest_file:
                    return None
            
            # Load manifest to get config
            import yaml
            import json
            
            with open(manifest_file, 'r', encoding='utf-8') as f:
                if manifest_file.suffix in ['.yaml', '.yml']:
                    manifest = yaml.safe_load(f)
                else:
                    manifest = json.load(f)
            
            config = manifest.get('config', {})
            
            if 'NUM_INSTANCES' in config or 'GENERATIONS' in config:
                return {
                    'NUM_INSTANCES': config.get('NUM_INSTANCES', 1),
                    'GENERATIONS': config.get('GENERATIONS', 1)
                }
                
        except Exception as e:
            self._log(f"[manifest_integration] Error reading manifest config: {e}")
        
        return None


def integrate_manifest_with_package_manager(
    zip_path: Path,
    comfy_path: Path,
    temp_dir: Path,
    log_file: Optional[Path] = None,
    skip_existing: bool = True,
    verify_checksums: bool = True,
    parallel_downloads: bool = True,
    max_workers: int = 4
) -> Tuple[bool, Optional[Dict], bool]:
    """
    Main integration function to be called by PackageManager.
    
    This function:
    1. Detects if ZIP has manifest
    2. Processes manifest if present (downloads models)
    3. Returns success status, optional manifest config, and custom_nodes_installed flag
    
    Args:
        zip_path: Path to ZIP package
        comfy_path: Path to ComfyUI installation
        temp_dir: Temporary directory for extraction
        log_file: Optional log file
        skip_existing: Skip files that already exist
        verify_checksums: Verify checksums
        parallel_downloads: Use parallel downloads
        max_workers: Number of parallel workers
        
    Returns:
        Tuple of (has_manifest, manifest_config_dict or None, custom_nodes_installed)
        
    Usage in PackageManager.extract_zip():
        has_manifest, manifest_config, custom_nodes_installed = integrate_manifest_with_package_manager(
            zip_path=self.zip_path,
            comfy_path=self.comfy_path,
            temp_dir=self.temp_dir,
            log_file=self.log_file
        )
        
        if has_manifest:
            # Manifest was processed, models downloaded
            if custom_nodes_installed:
                self.custom_nodes_extracted = True  # Set flag for restart check
            # Continue with smart extractor for bundled content
            pass
    """
    integration = ManifestIntegration(
        zip_path=zip_path,
        comfy_path=comfy_path,
        temp_dir=temp_dir,
        log_file=log_file
    )
    
    # Detect manifest
    has_manifest = integration.detect_manifest()
    
    if not has_manifest:
        # No manifest - return early, let smart extractor handle everything
        return False, None, False
    
    # Process manifest
    success, manifest_config = integration.process_manifest(
        skip_existing=skip_existing,
        verify_checksums=verify_checksums,
        parallel_downloads=parallel_downloads,
        max_workers=max_workers
    )
    
    if not success:
        print("[manifest_integration] Warning: Manifest processing failed, continuing with smart extraction")
        return True, None, False  # Has manifest but failed - still continue
    
    # Get baseconfig values from manifest if available
    baseconfig_from_manifest = integration.get_baseconfig_from_manifest()
    if baseconfig_from_manifest:
        manifest_config = manifest_config or {}
        manifest_config.update(baseconfig_from_manifest)
    
    return True, manifest_config, integration.custom_nodes_installed


# Example standalone usage for testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test manifest integration')
    parser.add_argument('zip_path', type=Path, help='Path to ZIP package')
    parser.add_argument('--comfy-path', type=Path, required=True, help='Path to ComfyUI')
    parser.add_argument('--temp-dir', type=Path, help='Temp directory')
    parser.add_argument('--log-file', type=Path, help='Log file')
    
    args = parser.parse_args()
    
    temp_dir = args.temp_dir or (args.comfy_path / "temp" / "manifest_test")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Testing manifest integration with: {args.zip_path}")
    
    has_manifest, config, custom_nodes = integrate_manifest_with_package_manager(
        zip_path=args.zip_path,
        comfy_path=args.comfy_path,
        temp_dir=temp_dir,
        log_file=args.log_file
    )
    
    print(f"\n{'='*60}")
    print(f"Results:")
    print(f"  Has manifest: {has_manifest}")
    print(f"  Config: {config}")
    print(f"  Custom nodes installed: {custom_nodes}")
    print(f"{'='*60}")
    
    # Cleanup
    if temp_dir.exists():
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)