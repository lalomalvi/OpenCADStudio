import json
from pathlib import Path
import sys
import tempfile
import unittest

from m8_case_cli import ReleaseCaseError, allowed_root, prepare, run, validate


class ReleaseCaseCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[3]
        cls.allowed = cls.repo / "target/mcp-release"
        cls.allowed.mkdir(parents=True, exist_ok=True)
        cls.fixture = Path(__file__).with_name("fixtures") / "synthetic-wall.planspec.json"
        cls.binary = Path(sys.executable).resolve(strict=True)

    def test_prepare_and_validate_frozen_contract(self):
        with tempfile.TemporaryDirectory(dir=self.allowed) as temporary:
            root = Path(temporary) / "case"
            prepared = prepare(root, self.fixture, self.binary)
            contract, compiled = validate(root, self.fixture, self.binary)
            self.assertEqual(prepared["commands_sha256"], compiled["commands_sha256"])
            self.assertEqual(contract["entity_count"], 4)
            self.assertFalse(contract["model_call"])

    def test_modified_contract_rejected_before_gui(self):
        with tempfile.TemporaryDirectory(dir=self.allowed) as temporary:
            root = Path(temporary) / "case"
            prepare(root, self.fixture, self.binary)
            contract_path = root / "contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["entity_count"] = 5
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseCaseError, "Frozen contract"):
                run(root, self.fixture, self.binary)
            self.assertFalse((root / "profile").exists())

    def test_started_run_cannot_replay(self):
        with tempfile.TemporaryDirectory(dir=self.allowed) as temporary:
            root = Path(temporary) / "case"
            prepare(root, self.fixture, self.binary)
            (root / "profile").mkdir()
            with self.assertRaisesRegex(ReleaseCaseError, "never replay"):
                run(root, self.fixture, self.binary)

    def test_output_path_restricted_to_release_root(self):
        with self.assertRaisesRegex(ReleaseCaseError, "Run root"):
            allowed_root(self.repo / "target/other/case")


if __name__ == "__main__":
    unittest.main()
