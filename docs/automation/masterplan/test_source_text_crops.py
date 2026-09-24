"""Synthetic adversarial crop geometry for source text evidence."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from source_text_crops import create


class SourceTextCropTests(unittest.TestCase):
    def test_padding_rejects_neighboring_claims_before_writing_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run"
            run.mkdir()
            image = root / "synthetic.png"
            Image.new("RGB", (160, 80), "white").save(image)
            source_sha = hashlib.sha256(image.read_bytes()).hexdigest().upper()
            (run / "freeze.json").write_text(json.dumps({
                "source_sha256": source_sha}), encoding="utf-8")
            output = {"source_regions": [[20, 20, 30, 30],
                                         [40, 20, 50, 30]]}
            events = [{"type": "thread.started"}, {"type": "turn.started"},
                      {"type": "item.completed", "item": {
                          "type": "agent_message", "text": json.dumps(output)}},
                      {"type": "turn.completed", "usage": {
                          "input_tokens": 1, "cached_input_tokens": 0,
                          "output_tokens": 1}}]
            (run / "events.jsonl").write_text(
                "\n".join(json.dumps(item) for item in events) + "\n",
                encoding="utf-8")
            target = root / "derived"
            with self.assertRaisesRegex(ValueError, "overlap neighboring"):
                create(run, image, target, padding_px=10)
            self.assertFalse(target.exists())
            result = create(run, image, root / "exact")
            self.assertEqual(len(result["regions"]), 2)


if __name__ == "__main__":
    unittest.main()
