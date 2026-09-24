import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from artifact_evidence import EvidenceError, artifact_ref, verify_ref
from region_evidence import (build_regions, projected_anchor_regions,
                             projected_door_regions, verify_anchor_regions,
                             verify_regions)


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

    def test_rejects_child_with_valid_hash_but_wrong_parent_pixels(self):
        build_regions(self.report, [{"label": "detail", "rect_px": [2, 1, 8, 7]}])
        crop = self.root / "regions/detail.png"
        Image.new("RGB", (6, 6), (200, 10, 10)).save(crop)
        manifest_path = self.root / "regions/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["regions"][0]["artifact"] = artifact_ref(
            self.root, "regions/detail.png", document_id=5,
            geometry_revision=8, camera_revision=2, region="pixel_crop:detail")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "pixels differ"):
            verify_regions(self.report, manifest_path)

    def test_projected_regions_require_same_capture_identity(self):
        report = json.loads(self.report.read_text(encoding="utf-8"))
        ids = [f"{door}-{part}" for door in ("door-south", "door-east")
               for part in ("hinge", "closed", "arc-mid", "open")]
        report["capture_projection"] = {
            "contract": "viewport-rte-pixels-1", "document_id": 5,
            "geometry_revision": 8, "camera_revision": 2,
            "landmarks_cad": [{"id": name, "point": [0, 0, 0]} for name in ids],
            "landmarks_px": [{"id": name, "pixel": [index + 1, 3], "inside": True}
                             for index, name in enumerate(ids)]}
        self.report.write_text(json.dumps(report), encoding="utf-8")
        regions = projected_door_regions(self.report, margin_px=1)
        self.assertEqual([item["label"] for item in regions],
                         ["door-south", "door-east"])
        self.assertEqual(regions[0]["rect_px"], [0, 2, 6, 5])
        build_regions(self.report, regions)
        verify_regions(self.report, self.root / "regions/manifest.json")
        report["capture_projection"]["camera_revision"] = 3
        self.report.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "does not belong"):
            projected_door_regions(self.report)

    def test_arbitrary_visible_anchor_group_is_fenced_and_cropped(self):
        report = json.loads(self.report.read_text(encoding="utf-8"))
        report["capture_projection"] = {
            "contract": "viewport-rte-pixels-1", "document_id": 5,
            "geometry_revision": 8, "camera_revision": 2,
            "landmarks_cad": [{"id": "edge-a", "point": [0, 0, 0]},
                              {"id": "edge-b", "point": [1, 0, 0]},
                              {"id": "edge-c", "point": [1, 1, 0]}],
            "landmarks_px": [{"id": "edge-a", "pixel": [2.2, 2.4], "inside": True},
                             {"id": "edge-b", "pixel": [8.1, 2.4], "inside": True},
                             {"id": "edge-c", "pixel": [8.1, 7.2], "inside": True}],
            "pixel_probes": [{"id": name, "visible": True}
                             for name in ("edge-a", "edge-b", "edge-c")]}
        self.report.write_text(json.dumps(report), encoding="utf-8")
        groups = [{"label": "synthetic-zone",
                   "landmark_ids": ["edge-a", "edge-b", "edge-c"]}]
        regions = projected_anchor_regions(self.report, groups, margin_px=1)
        self.assertEqual(regions, [{"label": "synthetic-zone",
                                    "rect_px": [1, 1, 11, 10]}])
        build_regions(self.report, regions)
        manifest_path = self.root / "regions/manifest.json"
        verify_anchor_regions(self.report, groups, manifest_path, margin_px=1)
        with self.assertRaisesRegex(EvidenceError, "anchor groups"):
            verify_anchor_regions(
                self.report, [{"label": "synthetic-zone",
                               "landmark_ids": ["edge-a", "edge-b"]}],
                manifest_path, margin_px=1)
        report["capture_projection"]["pixel_probes"][1]["visible"] = False
        self.report.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "hidden"):
            projected_anchor_regions(self.report, groups)

    def test_anchor_group_rejects_unknown_and_duplicate_ids(self):
        report = json.loads(self.report.read_text(encoding="utf-8"))
        report["capture_projection"] = {
            "contract": "viewport-rte-pixels-1", "document_id": 5,
            "geometry_revision": 8, "camera_revision": 2,
            "landmarks_cad": [{"id": "a", "point": [0, 0, 0]},
                              {"id": "b", "point": [1, 0, 0]}],
            "landmarks_px": [{"id": "a", "pixel": [2, 2], "inside": True},
                             {"id": "b", "pixel": [8, 2], "inside": True}],
            "pixel_probes": [{"id": "a", "visible": True},
                             {"id": "b", "visible": True}]}
        self.report.write_text(json.dumps(report), encoding="utf-8")
        for names in (["a", "missing"], ["a", "a"], ["a", []]):
            with self.assertRaises(EvidenceError):
                projected_anchor_regions(
                    self.report, [{"label": "zone", "landmark_ids": names}])
        self.assertFalse((self.root / "regions").exists())


if __name__ == "__main__":
    unittest.main()
