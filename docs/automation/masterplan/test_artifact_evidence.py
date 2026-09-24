import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("artifact_evidence", Path(__file__).with_name("artifact_evidence.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ArtifactEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "synthetic.png"
        self.path.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 2, 3) + b"fixture")

    def test_reference_fails_on_tamper_and_stale_render(self):
        ref = module.artifact_ref(self.root, "synthetic.png", document_id=1,
                                  geometry_revision=2, camera_revision=3)
        module.verify_ref(self.root, ref, document_id=1, geometry_revision=2, camera_revision=3)
        with self.assertRaises(module.EvidenceError):
            module.verify_ref(self.root, ref, document_id=1, geometry_revision=3, camera_revision=3)
        self.path.write_bytes(self.path.read_bytes() + b"changed")
        with self.assertRaises(module.EvidenceError):
            module.verify_ref(self.root, ref, document_id=1, geometry_revision=2, camera_revision=3)

    def test_escape_and_invalid_png_fail(self):
        with self.assertRaises(module.EvidenceError):
            module.artifact_ref(self.root, "../outside.png", document_id=1,
                                geometry_revision=1, camera_revision=1)
        self.path.write_bytes(b"not a png")
        with self.assertRaises(module.EvidenceError):
            module.artifact_ref(self.root, "synthetic.png", document_id=1,
                                geometry_revision=1, camera_revision=1)

    def test_seal_detects_edit_and_has_no_binary_or_credentials(self):
        ref = module.artifact_ref(self.root, "synthetic.png", document_id=1,
                                  geometry_revision=2, camera_revision=3)
        usage = {"schema_version": "m3-usage-summary-1", "source_kind": "token_usage_record",
                 "coverage": {"records": 1, "unique_responses": 1, "duplicate_records": 0,
                              "turns_with_identity": 1},
                 "usage": {"input_tokens": 8, "cached_input_tokens": 3,
                           "cache_write_input_tokens": 0, "output_tokens": 2,
                           "reasoning_output_tokens": 1, "total_tokens": 10},
                 "noncached_input_tokens": 5,
                 "identity": {"effective_model": "unknown", "supervisor_usage": "unknown"},
                 "billed_cost": None}
        value = module.seal("synthetic-run", usage, [ref], verdict="partial")
        module.verify_seal(value)
        self.assertNotIn("fixture", json.dumps(value))
        usage["token"] = "private"
        with self.assertRaises(module.EvidenceError):
            module.seal("synthetic-run", usage, [ref], verdict="partial")
        value["payload"]["verdict"] = "passed"
        with self.assertRaises(module.EvidenceError):
            module.verify_seal(value)


if __name__ == "__main__":
    unittest.main()
