import json
import unittest
from pathlib import Path


class TestLTXWorkflowPrompts(unittest.TestCase):
    WORKFLOW = Path("example_workflows/LTX2.3_FF_LF_rtx_video.json")

    def test_negative_prompt_excludes_positive_text(self):
        with self.WORKFLOW.open(encoding="utf-8") as f:
            data = json.load(f)

        positive = None
        negative = None
        for node in data["nodes"]:
            if node.get("title") == "Prompt":
                positive = node["widgets_values"][0]
            elif node.get("title") == "Negatives":
                negative = node["widgets_values"][0]

        self.assertIsNotNone(positive, "Prompt node not found")
        self.assertIsNotNone(negative, "Negative prompt node not found")

        for sentence in positive.splitlines():
            sentence = sentence.strip()
            if sentence:
                self.assertNotIn(sentence, negative,
                                 f"Negative prompt contains positive text {sentence!r}")


if __name__ == "__main__":
    unittest.main()
