import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("seal_cad_run", Path(__file__).with_name("seal_cad_run.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class CadSealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        self.binary = self.run / "synthetic.exe"
        self.binary.write_bytes(b"synthetic binary")
        self.drawing = self.run / "synthetic-verified.dwg"
        self.drawing.write_bytes(b"synthetic drawing")
        fixture = Path(module.__file__).with_name("fixtures") / "synthetic-room.planspec.json"
        compiled = module.dry_run(json.loads(fixture.read_text(encoding="utf-8")))
        manifest = {"total": 3, "by_type": {"Line": 2, "Circle": 1}, "by_layer": {"0": 3}}
        self.report = {"status": "passed", "gui_exited": True, "shutdown": "exited",
                       "binary_sha256": module.digest(self.binary),
                       "planspec": {"fixture_sha256": module.digest(fixture).lower(),
                                    "commands_sha256": compiled["commands_sha256"],
                                    "handles_by_id": {"line-1": "64", "line-2": "65", "circle-1": "66"}},
                       "audit_summary": {"status": "passed", "summary": {"errors": 0, "warnings": 0},
                                         "target": {"lossless": True}, "manifest": manifest,
                                         "bounds": None, "unknown_entities": 0},
                       "verified_output": {"path": str(self.drawing), "sha256": module.digest(self.drawing),
                                           "bytes": self.drawing.stat().st_size,
                                           "reopened_manifest": manifest},
                       "private_token": "must-not-export"}
        self.save_report()

    def save_report(self):
        (self.run / "report.json").write_text(json.dumps(self.report), encoding="utf-8")

    def test_seal_is_sanitized_immutable_and_detects_tamper(self):
        module.seal_run(self.run, self.binary)
        module.verify_seal(self.run, self.binary)
        self.assertNotIn("must-not-export", (self.run / "SEAL.json").read_text(encoding="utf-8"))
        with self.assertRaises(module.SealError):
            module.seal_run(self.run, self.binary)
        self.drawing.write_bytes(b"changed drawing")
        with self.assertRaises(module.SealError):
            module.verify_seal(self.run, self.binary)

    def test_changed_hash_or_unknown_identity_fails_before_writing(self):
        self.report["verified_output"]["sha256"] = "0" * 64
        self.save_report()
        with self.assertRaises(module.SealError):
            module.seal_run(self.run, self.binary)
        self.assertFalse((self.run / "SEAL.json").exists())


if __name__ == "__main__":
    unittest.main()
