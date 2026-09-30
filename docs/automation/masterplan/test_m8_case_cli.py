import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from m8_case_cli import ReleaseCaseError, allowed_root, prepare, run, validate, verify
from plan_contract import (HUMAN_CHANNEL, PREFIX_LENGTH, _append, approve, digest, revoke,
                           write_review)


class ReleaseCaseCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[3]
        cls.allowed = cls.repo / "target/mcp-release"
        cls.allowed.mkdir(parents=True, exist_ok=True)
        cls.fixture = Path(__file__).with_name("fixtures") / "synthetic-wall.planspec.json"
        cls.binary = Path(sys.executable).resolve(strict=True)

    def approve_fixture(self, workspace: Path, channel=HUMAN_CHANNEL) -> Path:
        """Simulate the human decision the CLI records through an interactive terminal."""
        review = write_review(self.fixture, workspace / "review")
        registry = workspace / "approvals.jsonl"
        approve(self.fixture, workspace / "review", registry, "Luis", "prueba L1",
                channel=channel, ask=lambda prompt: review["plan_sha256"][:PREFIX_LENGTH])
        return registry

    def assert_run_refused(self, workspace: Path, registry: Path, pattern: str) -> None:
        root = workspace / "case"
        prepare(root, self.fixture, self.binary)
        with mock.patch("m8_case_cli.subprocess.Popen") as popen, \
                self.assertRaisesRegex(ReleaseCaseError, pattern):
            run(root, self.fixture, self.binary, registry)
        popen.assert_not_called()
        self.assertFalse((root / "profile").exists())

    def test_revoked_approval_never_opens_the_gui(self):
        with tempfile.TemporaryDirectory(dir=self.allowed) as temporary:
            registry = self.approve_fixture(Path(temporary))
            revoke(self.fixture, registry, "Luis", "prueba", channel=HUMAN_CHANNEL,
                   ask=lambda prompt: digest(self.fixture)[:PREFIX_LENGTH])
            self.assert_run_refused(Path(temporary), registry, "revoked")

    def test_non_human_channel_never_opens_the_gui(self):
        with tempfile.TemporaryDirectory(dir=self.allowed) as temporary:
            registry = self.approve_fixture(Path(temporary), channel="test_fixture")
            self.assert_run_refused(Path(temporary), registry, "interactive human channel")

    def test_approval_of_other_commands_never_opens_the_gui(self):
        with tempfile.TemporaryDirectory(dir=self.allowed) as temporary:
            registry = Path(temporary) / "approvals.jsonl"
            _append(registry, {
                "decision": "approved", "plan_sha256": digest(self.fixture),
                "commands_sha256": "0" * 64, "entity_count": 4, "review_md_sha256": "0" * 64,
                "review_json_sha256": "0" * 64, "planspec_code_sha256": "0" * 64,
                "doubts": [], "doubts_acknowledged": False, "approver": "Luis",
                "scope": "prueba", "channel": HUMAN_CHANNEL,
                "recorded_at_utc": "2026-09-30T00:00:00Z"})
            self.assert_run_refused(Path(temporary), registry, "differ from the approved")

    def test_prepare_and_validate_frozen_contract(self):
        with tempfile.TemporaryDirectory(dir=self.allowed) as temporary:
            root = Path(temporary) / "case"
            prepared = prepare(root, self.fixture, self.binary)
            contract, compiled = validate(root, self.fixture, self.binary)
            self.assertEqual(prepared["commands_sha256"], compiled["commands_sha256"])
            self.assertEqual(contract["entity_count"], 4)
            self.assertFalse(contract["model_call"])
            self.assertIn("contract_gate_code_sha256", contract)

    def test_modified_contract_rejected_before_gui(self):
        with tempfile.TemporaryDirectory(dir=self.allowed) as temporary:
            root = Path(temporary) / "case"
            prepare(root, self.fixture, self.binary)
            contract_path = root / "contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["entity_count"] = 5
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseCaseError, "Frozen contract"):
                run(root, self.fixture, self.binary, Path(temporary) / "approvals.jsonl")
            self.assertFalse((root / "profile").exists())

    def test_started_run_cannot_replay(self):
        with tempfile.TemporaryDirectory(dir=self.allowed) as temporary:
            root = Path(temporary) / "case"
            prepare(root, self.fixture, self.binary)
            (root / "profile").mkdir()
            with self.assertRaisesRegex(ReleaseCaseError, "never replay"):
                run(root, self.fixture, self.binary, Path(temporary) / "approvals.jsonl")

    def test_unapproved_plan_never_opens_the_gui(self):
        with tempfile.TemporaryDirectory(dir=self.allowed) as temporary:
            root = Path(temporary) / "case"
            prepare(root, self.fixture, self.binary)
            with mock.patch("m8_case_cli.subprocess.Popen") as popen, \
                    self.assertRaisesRegex(ReleaseCaseError, "Human approval required"):
                run(root, self.fixture, self.binary, Path(temporary) / "approvals.jsonl")
            popen.assert_not_called()
            self.assertFalse((root / "profile").exists())

    def test_approved_plan_passes_the_gate_to_the_gui(self):
        with tempfile.TemporaryDirectory(dir=self.allowed) as temporary:
            root = Path(temporary) / "case"
            prepare(root, self.fixture, self.binary)
            registry = self.approve_fixture(Path(temporary))

            class GuiLaunched(Exception):
                pass

            with mock.patch("m8_case_cli.subprocess.Popen", side_effect=GuiLaunched) as popen, \
                    self.assertRaises(GuiLaunched):
                run(root, self.fixture, self.binary, registry)
            self.assertEqual(popen.call_args.args[0], [str(self.binary), "--new-instance"])

    def test_verify_requires_the_approval_binding(self):
        with tempfile.TemporaryDirectory(dir=self.allowed) as temporary:
            root = Path(temporary) / "case"
            prepare(root, self.fixture, self.binary)
            (root / "report.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseCaseError, "approval binding"):
                verify(root, self.fixture, self.binary)

    def test_output_path_restricted_to_release_root(self):
        with self.assertRaisesRegex(ReleaseCaseError, "Run root"):
            allowed_root(self.repo / "target/other/case")


if __name__ == "__main__":
    unittest.main()
