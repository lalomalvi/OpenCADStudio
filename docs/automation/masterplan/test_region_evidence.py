import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from artifact_evidence import EvidenceError, artifact_ref, verify_ref
from region_evidence import build_regions, verify_regions


class RegionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Image.new("RGB", (20, 10), (20, 30, 40)).save(self.root / "capture.png")
        self.parent = artifact_ref(self.root, "capture.png", document_id=5,
                                   geometry_revision=8, camera_revision=2,
                                   region="viewport")
        self.report = self.root / "report.json"
        self.report.write_text(json.dumps({"status": "passed",
                                           "capture_overlay_policy": "drawing_only",
                                           "capture_artifact": self.parent}), encoding="utf-8")

    def test_crops_inherit_fence_and_reject_replay_or_tamper(self):
        value = build_regions(self.report, [{"label": "detail", "rect_px": [2, 1, 8, 7]}])
        self.assertEqual(value["human_review_status"], "pending")
        child = value["regions"][0]["artifact"]
        self.assertEqual((child["width"], child["height"]), (6, 6))
        verify_ref(self.root, child, document_id=5, geometry_revision=8, camera_revision=2)
        verify_regions(self.report, self.root / "regions/manifest.json")
        crop = self.root / "regions/detail.png"
        original = crop.read_bytes()
        crop.write_bytes(original + b"tampered")
        with self.assertRaises(EvidenceError):
            verify_regions(self.report, self.root / "regions/manifest.json")
        crop.write_bytes(original)
        with self.assertRaises(EvidenceError):
            build_regions(self.report, [{"label": "detail", "rect_px": [2, 1, 8, 7]}])
        (self.root / "capture.png").write_bytes(b"changed")
        with self.assertRaises(EvidenceError):
            build_regions(self.report, [{"label": "new", "rect_px": [0, 0, 2, 2]}], "later")
        with self.assertRaises(EvidenceError):
            verify_regions(self.report, self.root / "regions/manifest.json")

    def test_rejects_bad_rect_and_unfenced_capture_without_writing(self):
        with self.assertRaises(EvidenceError):
            build_regions(self.report, [{"label": "bad", "rect_px": [0, 0, 21, 2]}])
        self.assertFalse((self.root / "regions").exists())
        report = json.loads(self.report.read_text(encoding="utf-8"))
        report["capture_overlay_policy"] = "with_controls"
        self.report.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaises(EvidenceError):
            build_regions(self.report, [{"label": "detail", "rect_px": [0, 0, 2, 2]}])


if __name__ == "__main__":
    unittest.main()
