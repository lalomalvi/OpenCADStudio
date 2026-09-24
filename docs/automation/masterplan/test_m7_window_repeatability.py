import json
from pathlib import Path
import tempfile
import unittest

from m7_window_repeatability import ORDER, digest, prepare, summarize, write_new


class WindowRepeatabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.source = base / "source.jpg"
        self.crop = base / "crop.png"
        self.cli = base / "codex.exe"
        for path in (self.source, self.crop, self.cli):
            path.write_bytes(path.name.encode())
        self.root = base / "pilot"
        prepare(self.root, self.source, self.crop, self.cli)
        for index, arm in enumerate(ORDER):
            slot = self.root / f"slot-{index:02d}"
            slot.mkdir()
            write_new(slot / "intent.json", {
                "slot": index, "arm": arm,
                "freeze_sha256": digest(self.root / "freeze.json"),
                "prompt_sha256": digest(self.root / f"{arm}.txt"),
                "crop_sha256": digest(self.root / "crop.png"),
                "cli_sha256": digest(self.cli),
            })
            answer = {"schema_version": "ocs-window-endpoints-1", "status": "observed",
                      "top_px": [264, 232], "bottom_px": [264, 952]}
            events = [
                {"type": "item.completed", "item": {"type": "agent_message",
                                                 "text": json.dumps(answer)}},
                {"type": "turn.completed", "usage": {"input_tokens": 10,
                                                       "cached_input_tokens": 2,
                                                       "output_tokens": 4}},
            ]
            (slot / "events.jsonl").write_text(
                "\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
            (slot / "stderr.txt").write_text("", encoding="utf-8")
            write_new(slot / "result.json", {
                "slot": index, "arm": arm, "exit_code": 0, "elapsed_seconds": 1.0,
                "intent_sha256": digest(slot / "intent.json"),
                "events_sha256": digest(slot / "events.jsonl"),
                "stderr_sha256": digest(slot / "stderr.txt"),
            })

    def test_summarizes_six_complete_slots_with_crop_conversion(self):
        summary = summarize(self.root, self.source, self.cli)
        self.assertEqual(summary["arms"]["baseline"]["passed"], 3)
        self.assertEqual(summary["arms"]["candidate"]["passed"], 3)
        self.assertEqual(summary["records"][0]["observed_original_px"],
                         [[393.0, 564.0], [393.0, 654.0]])
        self.assertFalse(summary["acceptance_m7"])

    def test_changed_event_stream_rejected(self):
        events = self.root / "slot-02" / "events.jsonl"
        events.write_text(events.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "integrity or completion"):
            summarize(self.root, self.source, self.cli)

    def test_changed_crop_rejected(self):
        (self.root / "crop.png").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "Frozen pilot inputs"):
            summarize(self.root, self.source, self.cli)


if __name__ == "__main__":
    unittest.main()
