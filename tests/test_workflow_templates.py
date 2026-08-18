"""Regression tests for ComfyUI workflow template files."""

import json
import unittest
from pathlib import Path

EXAMPLE_DIR = Path(__file__).parent.parent / "example_workflows"
WORKFLOW_FILES = sorted(EXAMPLE_DIR.glob("*.json"))


def _accepts(slot_type, link_type):
    if slot_type is None or link_type is None:
        return slot_type == link_type
    allowed = {t.strip() for t in slot_type.split(",")}
    if "*" in allowed:
        return True
    return link_type in allowed


class TestWorkflowTemplate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = []
        for path in WORKFLOW_FILES:
            with open(path, encoding="utf-8") as f:
                cls.workflows.append((path.name, json.load(f)))

    def _iter_workflows(self):
        if not self.workflows:
            self.fail(f"no workflow JSON files found in {EXAMPLE_DIR}")
        return self.workflows

    def test_required_top_level_keys(self):
        for name, data in self._iter_workflows():
            with self.subTest(workflow=name):
                for key in ("last_node_id", "last_link_id", "nodes", "links", "version"):
                    self.assertIn(key, data)

    def test_all_links_reference_existing_top_level_nodes(self):
        for name, data in self._iter_workflows():
            with self.subTest(workflow=name):
                node_ids = {node["id"] for node in data["nodes"]}
                for link in data["links"]:
                    self.assertIn(link[1], node_ids, f"link {link[0]} origin node missing")
                    self.assertIn(link[3], node_ids, f"link {link[0]} target node missing")

    def test_link_types_match_node_slots(self):
        for name, data in self._iter_workflows():
            with self.subTest(workflow=name):
                outputs = {}
                inputs = {}
                for node in data["nodes"]:
                    for slot, output in enumerate(node.get("outputs", [])):
                        outputs[(node["id"], slot)] = output.get("type")
                    for slot, inp in enumerate(node.get("inputs", [])):
                        inputs[(node["id"], slot)] = inp.get("type")
                for link in data["links"]:
                    lid, origin, oslot, target, tslot, ltype = link
                    self.assertTrue(
                        _accepts(outputs.get((origin, oslot)), ltype),
                        f"link {lid} origin ({origin},{oslot}) does not accept {ltype}",
                    )
                    self.assertTrue(
                        _accepts(inputs.get((target, tslot)), ltype),
                        f"link {lid} target ({target},{tslot}) does not accept {ltype}",
                    )

    def test_unique_link_ids(self):
        for name, data in self._iter_workflows():
            with self.subTest(workflow=name):
                link_ids = [link[0] for link in data["links"]]
                self.assertEqual(len(link_ids), len(set(link_ids)))

    def test_last_ids_cover_used_ids(self):
        for name, data in self._iter_workflows():
            with self.subTest(workflow=name):
                max_node_id = max(node["id"] for node in data["nodes"])
                max_link_id = max(link[0] for link in data["links"])
                self.assertGreaterEqual(data["last_node_id"], max_node_id)
                self.assertGreaterEqual(data["last_link_id"], max_link_id)

    def test_subgraph_node_interface_matches_definition(self):
        for name, data in self._iter_workflows():
            with self.subTest(workflow=name):
                subgraphs = {sg["id"]: sg for sg in data.get("definitions", {}).get("subgraphs", [])}
                for node in data["nodes"]:
                    if node["type"] not in subgraphs:
                        continue
                    sg = subgraphs[node["type"]]
                    sg_inputs = sg.get("inputs", [])
                    sg_outputs = sg.get("outputs", [])
                    self.assertEqual(len(node.get("inputs", [])), len(sg_inputs))
                    self.assertEqual(len(node.get("outputs", [])), len(sg_outputs))
                    for i, inp in enumerate(node["inputs"]):
                        self.assertEqual(inp.get("type"), sg_inputs[i]["type"])
                    for i, out in enumerate(node["outputs"]):
                        self.assertEqual(out.get("type"), sg_outputs[i]["type"])


