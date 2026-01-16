# core/workflow_manager.py
import json
import random
import re
import requests
from pathlib import Path


class WorkflowManager:
    def __init__(self, workflow_path, log_file=None):
        """
        Initialize WorkflowManager with a workflow JSON path.

        Args:
            workflow_path (Path): Path to the workflow JSON file.
            log_file (Path, optional): Path to log file for logging operations.
        """
        self.workflow_path = Path(workflow_path).resolve()
        self.log_file = log_file if log_file else None
        self.workflow = None
        self.applied_overrides = []

    def log(self, message):
        """Log a message to the console and optionally to a log file."""
        print(message)
        if self.log_file:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(message + '\n')


    def load_workflow(self):
        """Load ONLY API/flat format workflows. Reject full UI workflows with clear message."""
        if not self.workflow_path.exists():
            raise FileNotFoundError(f"Workflow file not found: {self.workflow_path}")

        if self.workflow_path.suffix.lower() != ".json":
            raise ValueError(f"Workflow must be a .json file: {self.workflow_path}")

        self.log(f"Loading workflow: {self.workflow_path}")

        try:
            with open(self.workflow_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # ------------------------------------------------------------------
            # STRICT FORMAT CHECK: Must be API/flat format
            # ------------------------------------------------------------------
            if not isinstance(data, dict):
                raise ValueError("Workflow root must be a JSON object {}")

            # If it has "nodes" list → it's the full UI format → REJECT
            if "nodes" in data and isinstance(data["nodes"], list):
                raise ValueError(
                    "ERROR: This is a FULL UI workflow (not API format)\n\n"
                    "You saved the workflow using the regular 'Save' button.\n"
                    "Please re-save it using:\n"
                    "   → 'Save (API Format)' button in ComfyUI\n"
                    "   (You may need to enable Dev Mode in settings)\n\n"
                    "This benchmark tool ONLY accepts API-format workflows.\n"
                    "Reason: They are smaller, faster, and 100% compatible with the /prompt API."
                )

            # If it has keys like "last_node_id", "version", etc. but no nodes → still reject
            if any(key in data for key in ["last_node_id", "last_link_id", "version", "comfy_fork_version"]):
                if not any(str(k).isdigit() for k in data.keys()):
                    raise ValueError(
                        "This appears to be a UI workflow metadata shell without nodes.\n"
                        "Please use 'Save (API Format)' to export a valid prompt."
                    )

            # At this point: it should be flat dict with node IDs as keys
            valid_node_ids = [k for k in data.keys() if str(k).isdigit() or (isinstance(k, str) and k.isdigit())]
            if not valid_node_ids:
                raise ValueError("No valid node entries found. This is not a valid API-format workflow.")

            # Success – store as-is
            self.workflow = data
            self.log(f"Successfully loaded API-format workflow with {len(valid_node_ids)} nodes")

            # Optional: lightweight validation
            self._validate_workflow()

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in workflow file: {e}")
        except Exception as e:
            # Re-raise with clear message
            if "UI workflow" in str(e) or "Save (API Format)" in str(e):
                raise  # already clear
            else:
                raise ValueError(f"Failed to load workflow: {e}")

    def _validate_workflow(self):
        """
        Validate the workflow JSON, focusing on KSampler and KSamplerAdvanced nodes.
        This is now non-fatal – logs warnings instead of raising errors.
        """
        sampler_nodes = [
            (nid, node) for nid, node in self.workflow.items()
            if node.get("class_type") in ["KSampler", "KSamplerAdvanced"]
        ]

        if not sampler_nodes:
            self.log("Validation skipped – no KSampler or KSamplerAdvanced nodes found. This is not an error.")
            return

        self.log(f"Validating {len(sampler_nodes)} sampler node(s)...")
        all_valid = True

        for node_id, node in sampler_nodes:
            class_type = node.get("class_type")
            inputs = node.get("inputs", {})

            try:
                if class_type == "KSampler":
                    steps = inputs.get("steps")
                    start_step = inputs.get("start_step", 0)
                    last_step = inputs.get("last_step", steps)
                    cfg = inputs.get("cfg")
                    denoise = inputs.get("denoise")
                    sampler_name = inputs.get("sampler_name")
                    scheduler = inputs.get("scheduler")

                    if not isinstance(steps, int) or steps <= 0:
                        self.log(f"WARNING: Node {node_id} (KSampler) - invalid 'steps': {steps} (must be positive int)")
                        all_valid = False
                    if not isinstance(start_step, int) or start_step < 0:
                        self.log(f"WARNING: Node {node_id} (KSampler) - invalid 'start_step': {start_step}")
                        all_valid = False
                    if last_step is not None and (not isinstance(last_step, int) or last_step <= start_step or last_step > steps):
                        self.log(f"WARNING: Node {node_id} (KSampler) - invalid 'last_step': {last_step}")
                        all_valid = False
                    if not isinstance(cfg, (int, float)) or cfg <= 0:
                        self.log(f"WARNING: Node {node_id} (KSampler) - invalid 'cfg': {cfg}")
                        all_valid = False
                    if not isinstance(denoise, (int, float)) or not (0 <= denoise <= 1):
                        self.log(f"WARNING: Node {node_id} (KSampler) - invalid 'denoise': {denoise}")
                        all_valid = False
                    if not sampler_name:
                        self.log(f"WARNING: Node {node_id} (KSampler) - missing 'sampler_name'")
                        all_valid = False
                    if not scheduler:
                        self.log(f"WARNING: Node {node_id} (KSampler) - missing 'scheduler'")
                        all_valid = False

                elif class_type == "KSamplerAdvanced":
                    steps = inputs.get("steps")
                    cfg = inputs.get("cfg")
                    sampler_name = inputs.get("sampler_name")
                    scheduler = inputs.get("scheduler")
                    start_at_step = inputs.get("start_at_step")
                    end_at_step = inputs.get("end_at_step")

                    if not isinstance(steps, int) or steps <= 0:
                        self.log(f"WARNING: Node {node_id} (KSamplerAdvanced) - invalid 'steps': {steps}")
                        all_valid = False
                    if not isinstance(cfg, (int, float)) or cfg <= 0:
                        self.log(f"WARNING: Node {node_id} (KSamplerAdvanced) - invalid 'cfg': {cfg}")
                        all_valid = False
                    if not sampler_name:
                        self.log(f"WARNING: Node {node_id} (KSamplerAdvanced) - missing 'sampler_name'")
                        all_valid = False
                    if not scheduler:
                        self.log(f"WARNING: Node {node_id} (KSamplerAdvanced) - missing 'scheduler'")
                        all_valid = False
                    if not isinstance(start_at_step, int) or start_at_step < 0:
                        self.log(f"WARNING: Node {node_id} (KSamplerAdvanced) - invalid 'start_at_step': {start_at_step}")
                        all_valid = False
                    if not isinstance(end_at_step, int) or end_at_step <= start_at_step:
                        self.log(f"WARNING: Node {node_id} (KSamplerAdvanced) - invalid 'end_at_step': {end_at_step}")
                        all_valid = False

            except Exception as e:
                self.log(f"WARNING: Node {node_id} ({class_type}) - validation error: {e}")
                all_valid = False

        if all_valid:
            self.log("All sampler nodes passed validation.")
        else:
            self.log("Validation completed with warnings. Continuing execution...")

    def apply_overrides(self, override_path):
        """Apply overrides from a JSON file to the workflow."""
        if not override_path or not Path(override_path).exists():
            self.log("No override file provided or file does not exist.")
            return

        try:
            with open(override_path, 'r', encoding='utf-8') as f:
                overrides = json.load(f).get("overrides", {})
            self.log(f"Override file specified: {override_path}")
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            error_msg = f"Error: Failed to parse override file {override_path}: {e}"
            self.log(error_msg)
            raise

        modified_workflow = json.loads(json.dumps(self.workflow))  # Deep copy
        self.applied_overrides = []

        for override_key, override in overrides.items():
            override_item = override.get("override_item")
            override_value = override.get("override_value")
            restrict = override.get("restrict", {})
            if not override_item or override_value is None:
                self.log(f"Warning: Skipping invalid override {override_key}: missing override_item or override_value")
                continue
            matched_nodes = []
            for node_id, node in modified_workflow.items():
                matches = True
                if restrict:
                    for restrict_key, restrict_value in restrict.items():
                        if restrict_key == "id":
                            if node_id != str(restrict_value):
                                matches = False
                                break
                        elif restrict_key in node.get("_meta", {}):
                            if node["_meta"].get(restrict_key) != restrict_value:
                                matches = False
                                break
                        elif restrict_key in node:
                            if node.get(restrict_key) != restrict_value:
                                matches = False
                                break
                        else:
                            matches = False
                            break
                if matches:
                    node_title = node.get("_meta", {}).get("title", "Untitled")
                    if override_item == "bypass":
                        if override_value is True:
                            modified_workflow[node_id]["bypass"] = True
                            self.log(f"Applying override {override_key}: setting bypass to true in node {node_id} ({node_title})")
                            matched_nodes.append(f"{node_id} ({node_title})")
                        elif override_value is False and node.get("bypass", False) is True:
                            modified_workflow[node_id]["bypass"] = False
                            self.log(f"Applying override {override_key}: setting bypass to false in node {node_id} ({node_title})")
                            matched_nodes.append(f"{node_id} ({node_title})")
                    elif override_item in node.get("inputs", {}):
                        modified_workflow[node_id]["inputs"][override_item] = override_value
                        self.log(f"Applying override {override_key}: setting {override_item} to {override_value} in node {node_id} ({node_title})")
                        matched_nodes.append(f"{node_id} ({node_title})")
            if matched_nodes:
                self.applied_overrides.append({
                    "key": override_key,
                    "item": override_item,
                    "value": override_value,
                    "nodes": matched_nodes
                })
            else:
                self.log(f"Warning: Override {override_key} matched no nodes")
        self.workflow = modified_workflow

    def get_workflow(self, randomize_seeds=True):
        """
        Get a copy of the workflow, optionally randomizing seeds for KSampler/PrimitiveInt nodes.

        Args:
            randomize_seeds (bool): If True, randomize seeds for KSampler and PrimitiveInt nodes.

        Returns:
            dict: A deep copy of the workflow JSON.
        """
        if self.workflow is None:
            error_msg = "Error: Workflow not loaded. Call load_workflow() first."
            self.log(error_msg)
            raise ValueError(error_msg)

        workflow = json.loads(json.dumps(self.workflow))  # Deep copy
        if randomize_seeds:
            for node_id, node in workflow.items():
                class_type = node.get("class_type")
                inputs = node.get("inputs", {})
                if class_type == "KSampler" and "seed" in inputs:
                    workflow[node_id]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
                elif class_type == "KSamplerAdvanced" and "noise_seed" in inputs:
                    workflow[node_id]["inputs"]["noise_seed"] = random.randint(0, 2**32 - 1)
                elif class_type == "RandomNoise" and "noise_seed" in inputs:
                    workflow[node_id]["inputs"]["noise_seed"] = random.randint(0, 2**32 - 1)
                elif class_type == "PrimitiveInt" and "value" in inputs:
                    meta = node.get("_meta", {})
                    title = meta.get("title", "")
                    if re.search(r"Random", title, re.IGNORECASE):
                        workflow[node_id]["inputs"]["value"] = random.randint(0, 2**32 - 1)
        return workflow

    def update_filename_prefixes_in_copy(self, workflow_copy, prefix_type, instance_num, gen_num, timestamp):
        """
        Update filename_prefix in SaveImage nodes:
          - Add timestamp folder: {base_path}/{timestamp}/
          - Append suffix to filename: _{timestamp}_{prefix_type}_{instance}-{gen}

        Example:
            Original: "flux_krea/flux_krea"
            → Folder: flux_krea/020911/
            → File:  flux_krea_020911_RUN_2-4_00001_.png

        Args:
            workflow_copy (dict): Copy of the workflow to modify.
            prefix_type (str): 'WARMUP' or 'RUN'.
            instance_num (int): 1-based instance number.
            gen_num (int): 1-based generation number.
            timestamp (str): HHMMSS timestamp.

        Returns:
            dict: Modified workflow copy.
        """
        timestamp_folder = timestamp  # e.g., "020911"
        suffix = f"{timestamp}_{prefix_type}_{instance_num}-{gen_num}"  # e.g., "020911_RUN_2-4"
        modified = False

        for node_id, node in workflow_copy.items():
            if node.get("class_type") in ("SaveImage", "SaveVideo", "SaveGLB"):
                inputs = node.get("inputs", {})
                if "filename_prefix" in inputs:
                    current_prefix = inputs["filename_prefix"]

                    # CRITICAL: Skip if this is a node connection (list with node ID reference)
                    # In ComfyUI API format, ["80", 0] means "connect to node 80, output 0"
                    if isinstance(current_prefix, list):
                        # Check if first element looks like a node ID (numeric string or int)
                        if len(current_prefix) >= 2 and (isinstance(current_prefix[0], int) or 
                            (isinstance(current_prefix[0], str) and current_prefix[0].isdigit())):
                            self.log(f"Skipping filename_prefix in node {node_id}: it's a node connection {current_prefix}")
                            continue
                        # Otherwise it might be a list-wrapped string (uncommon)
                        if len(current_prefix) > 0 and isinstance(current_prefix[0], str):
                            orig = current_prefix[0]
                            parts = orig.strip("/").split("/", 1)
                            base_path = parts[0] if len(parts) > 1 else ""
                            filename_part = parts[-1] if len(parts) > 1 else parts[0]
                            new_path = f"{base_path}/{timestamp_folder}/{filename_part}_{suffix}" if base_path else f"{timestamp_folder}/{filename_part}_{suffix}"
                            current_prefix[0] = new_path
                            self.log(f"Updated filename_prefix (list) in node {node_id}: '{orig}' → '{new_path}'")
                            modified = True

                    elif isinstance(current_prefix, str):
                        # Split into base path and filename part
                        parts = current_prefix.strip("/").split("/", 1)
                        base_path = parts[0] if len(parts) > 1 else ""
                        filename_part = parts[-1] if len(parts) > 1 else parts[0]

                        # Build new path: base_path/timestamp/filename_part_suffix
                        new_path = f"{base_path}/{timestamp_folder}/{filename_part}_{suffix}" if base_path else f"{timestamp_folder}/{filename_part}_{suffix}"

                        inputs["filename_prefix"] = new_path
                        self.log(f"Updated filename_prefix in node {node_id}: '{current_prefix}' → '{new_path}'")
                        modified = True

        if not modified:
            self.log("No SaveImage nodes with filename_prefix found.")

        return workflow_copy

    def queue_prompt(self, client_id, server_address):
        """
        Queue a workflow prompt to a ComfyUI server.

        Args:
            client_id (str): Unique client ID for the prompt.
            server_address (str): Address of the ComfyUI server (e.g., "127.0.0.1:8188").

        Returns:
            str: The prompt ID returned by the server.
        """
        workflow = self.get_workflow()
        data = {"prompt": workflow, "client_id": client_id}
        response = requests.post(f"http://{server_address}/prompt", json=data)
        if response.status_code != 200:
            error_msg = f"Failed to queue prompt: {response.text}"
            self.log(error_msg)
            raise Exception(error_msg)
        return response.json()["prompt_id"]

    def get_applied_overrides(self):
        """Return the list of applied overrides."""
        return self.applied_overrides

    def set_benchmarknode_value(self, benchmark_node_manager, field_name, field_value):
        """
        Set a value on the Benchmark Workflow node if the comfyui-benchmark custom node exists.
        If the node doesn't exist in the workflow JSON, create it.

        Args:
            benchmark_node_manager (BenchmarkNodeManager): Instance to check for comfyui-benchmark existence.
            field_name (str): The field to set. Can be 'capture_benchmark', 'outfile_postfix1', or 'outfile_postfix2'.
            field_value: The value to set. Boolean for 'capture_benchmark', string for 'outfile_postfix1' and 'outfile_postfix2'.
        """
        if not benchmark_node_manager.exists:
            self.log("comfyui-benchmark custom node not found. Skipping Benchmark Workflow node modification.")
            return

        if self.workflow is None:
            error_msg = "Error: Workflow not loaded. Call load_workflow() first."
            self.log(error_msg)
            raise ValueError(error_msg)

        if field_name not in ['capture_benchmark', 'outfile_postfix1', 'outfile_postfix2']:
            error_msg = f"Invalid field_name: {field_name}. Must be one of 'capture_benchmark', 'outfile_postfix1', 'outfile_postfix2'."
            self.log(error_msg)
            raise ValueError(error_msg)

        if field_name == 'capture_benchmark' and not isinstance(field_value, bool):
            error_msg = f"Invalid field_value for {field_name}: must be boolean."
            self.log(error_msg)
            raise ValueError(error_msg)

        if field_name in ['outfile_postfix1', 'outfile_postfix2'] and not isinstance(field_value, str):
            error_msg = f"Invalid field_value for {field_name}: must be string."
            self.log(error_msg)
            raise ValueError(error_msg)

        benchmark_node_id = None
        for node_id, node in self.workflow.items():
            meta = node.get("_meta", {})
            title = meta.get("title", "")
            if title == "Benchmark Workflow":
                benchmark_node_id = node_id
                break

        modified_workflow = json.loads(json.dumps(self.workflow))  # Deep copy

        if benchmark_node_id is None:
            # Create a new Benchmark Workflow node
            benchmark_node_id = str(len(modified_workflow) + 1)  # Simple ID generation
            modified_workflow[benchmark_node_id] = {
                "class_type": "BenchmarkWorkflow",
                "_meta": {"title": "Benchmark Workflow"},
                "inputs": {
                    "capture_benchmark": True,
                    "file_prefix": "",
                    "file_postfix": ""
                }
            }
            self.log(f"Created new Benchmark Workflow node with ID: {benchmark_node_id}")

        node = modified_workflow[benchmark_node_id]
        if field_name not in node.get("inputs", {}):
            error_msg = f"Field '{field_name}' not found in inputs of Benchmark Workflow node (ID: {benchmark_node_id})."
            self.log(error_msg)
            raise ValueError(error_msg)

        node["inputs"][field_name] = field_value
        self.log(f"Set {field_name} to {field_value} in Benchmark Workflow node (ID: {benchmark_node_id})")
        self.workflow = modified_workflow