import json
from pathlib import Path
import shutil
import tempfile
import unittest

from plan_contract import (DOUBTS_ACK, HUMAN_CHANNEL, PREFIX_LENGTH, REVIEW_JSON, REVIEW_MD,
                           ContractError, approve, build_review, find_record, read_registry,
                           require_approval, revoke, write_review)


FIXTURES = Path(__file__).with_name("fixtures")
TEST_CHANNEL = "test_fixture"


def answers(*values):
    queue = list(values)
    return lambda prompt: queue.pop(0)


class PlanContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.registry = self.root / "approvals.jsonl"
        self.plan = self.use_fixture("synthetic-wall.planspec.json")

    def tearDown(self):
        self.temporary.cleanup()

    def use_fixture(self, name: str) -> Path:
        path = self.root / name
        shutil.copyfile(FIXTURES / name, path)
        return path

    def edit_plan(self, change) -> None:
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        change(plan)
        self.plan.write_text(json.dumps(plan), encoding="utf-8")

    def review(self, name="review", previous=None) -> tuple[Path, dict]:
        write_review(self.plan, self.root / name, previous)
        review_dir = self.root / name
        return review_dir, json.loads((review_dir / REVIEW_JSON).read_text(encoding="utf-8"))

    def approve(self, review_dir: Path, *typed, channel=TEST_CHANNEL) -> dict:
        data = json.loads((review_dir / REVIEW_JSON).read_text(encoding="utf-8"))
        return approve(self.plan, review_dir, self.registry, "Luis", "prueba L0",
                       channel=channel,
                       ask=answers(*(typed or (data["plan_sha256"][:PREFIX_LENGTH],))))

    def gate(self, data: dict, channels=frozenset({TEST_CHANNEL})) -> dict:
        return require_approval(self.registry, data["plan_sha256"], data["commands_sha256"],
                                accepted_channels=channels)

    def test_review_is_deterministic_and_states_limits(self):
        first, data = build_review(self.plan)
        second, _ = build_review(self.plan)
        self.assertEqual(first, second)
        self.assertTrue(data["executable"])
        self.assertEqual(data["entity_count"], 4)
        for expected in ("**Muros (1)**", "`wall-south`", "4.000", "0.200", "**Sí**",
                         data["plan_sha256"][:PREFIX_LENGTH], "## 2. Supuestos",
                         "## 3. Dudas", "## 4. Bloqueos", "No se verifica:", "## Aprobación"):
            self.assertIn(expected, first)

    def test_openings_show_swing_and_elevation(self):
        self.plan = self.use_fixture("synthetic-door-swing.planspec.json")
        door, _ = build_review(self.plan)
        self.assertIn("bisagra en el inicio, abre a la izquierda, 90°", door)
        self.plan = self.use_fixture("synthetic-window.planspec.json")
        window, _ = build_review(self.plan)
        self.assertIn("antepecho 0.800 m, dintel 2.100 m", window)

    def test_assumptions_and_doubts_come_from_source_classification(self):
        def change(plan):
            plan["walls"][0]["source"].update({"classification": "inferred", "confidence": 0.6})
            plan["nodes"][1]["source"]["classification"] = "unknown"
        self.edit_plan(change)
        markdown, data = build_review(self.plan)
        self.assertEqual(data["assumptions"], ["wall-south"])
        self.assertEqual(data["doubts"], ["b"])
        self.assertIn("muro `wall-south` · confianza 0.600", markdown)
        self.assertIn("nodo `b`", markdown)
        self.assertIn(DOUBTS_ACK, markdown)

    def test_approval_binds_plan_commands_and_review(self):
        review_dir, data = self.review()
        record = self.approve(review_dir)
        self.assertEqual(record["decision"], "approved")
        self.assertEqual(record["plan_sha256"], data["plan_sha256"])
        self.assertEqual(record["commands_sha256"], data["commands_sha256"])
        self.assertEqual(record["review_md_sha256"], data["review_md_sha256"])
        self.assertEqual(self.gate(data)["record_sha256"], record["record_sha256"])
        self.assertEqual(find_record(self.registry, record["record_sha256"]), record)
        self.assertEqual(len(read_registry(self.registry)), 1)

    def test_wrong_typed_prefix_records_nothing(self):
        review_dir, _ = self.review()
        with self.assertRaisesRegex(ContractError, "prefix differs"):
            self.approve(review_dir, "000000000000")
        self.assertFalse(self.registry.exists())

    def test_doubts_require_explicit_acknowledgement(self):
        self.edit_plan(lambda plan: plan["nodes"][0]["source"].update(
            {"classification": "unknown"}))
        review_dir, data = self.review()
        prefix = data["plan_sha256"][:PREFIX_LENGTH]
        with self.assertRaisesRegex(ContractError, "not acknowledged"):
            self.approve(review_dir, prefix, "si")
        self.assertFalse(self.registry.exists())
        record = self.approve(review_dir, prefix, DOUBTS_ACK)
        self.assertTrue(record["doubts_acknowledged"])
        self.assertEqual(record["doubts"], ["a"])

    def test_gate_rejects_missing_foreign_changed_and_revoked_approvals(self):
        review_dir, data = self.review()
        with self.assertRaisesRegex(ContractError, "absent"):
            self.gate(data)
        self.approve(review_dir)
        with self.assertRaisesRegex(ContractError, "interactive human channel"):
            self.gate(data, channels=frozenset({HUMAN_CHANNEL}))
        with self.assertRaisesRegex(ContractError, "differ from the approved"):
            require_approval(self.registry, data["plan_sha256"], "0" * 64,
                             accepted_channels={TEST_CHANNEL})
        revoke(self.plan, self.registry, "Luis", "cambio de alcance", channel=TEST_CHANNEL,
               ask=answers(data["plan_sha256"][:PREFIX_LENGTH]))
        with self.assertRaisesRegex(ContractError, "revoked"):
            self.gate(data)

    def test_plan_changed_after_review_cannot_be_approved(self):
        review_dir, _ = self.review()
        self.edit_plan(lambda plan: plan["walls"][0].update({"thickness_m": 0.25}))
        with self.assertRaisesRegex(ContractError, "no longer matches"):
            self.approve(review_dir, "anything")
        self.assertFalse(self.registry.exists())

    def test_edited_review_sheet_is_rejected(self):
        review_dir, _ = self.review()
        sheet = review_dir / REVIEW_MD
        sheet.write_bytes(sheet.read_bytes().replace("**Sí**".encode(), b"**Si**"))
        with self.assertRaisesRegex(ContractError, "modified after it was written"):
            self.approve(review_dir, "anything")

    def test_edited_review_summary_cannot_unlock_approval(self):
        self.plan = self.use_fixture("synthetic-door-obstacle-v8.planspec.json")
        review_dir, data = self.review()
        data.update({"executable": True, "quality_blockers": []})
        (review_dir / REVIEW_JSON).write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "no longer matches"):
            self.approve(review_dir)
        self.assertFalse(self.registry.exists())

    def test_non_executable_plan_cannot_be_approved(self):
        self.plan = self.use_fixture("synthetic-door-obstacle-v8.planspec.json")
        review_dir, data = self.review()
        self.assertFalse(data["executable"])
        self.assertIn("**NO**", (review_dir / REVIEW_MD).read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ContractError, "cannot be approved"):
            self.approve(review_dir)

    def test_tampered_registry_is_rejected(self):
        review_dir, data = self.review()
        self.approve(review_dir)
        self.registry.write_bytes(self.registry.read_bytes().replace(b"prueba L0", b"otro"))
        with self.assertRaisesRegex(ContractError, "tampered"):
            read_registry(self.registry)
        with self.assertRaisesRegex(ContractError, "tampered"):
            self.gate(data)

    def test_registry_chain_links_successive_decisions(self):
        review_dir, data = self.review()
        first = self.approve(review_dir)
        second = revoke(self.plan, self.registry, "Luis", "prueba", channel=TEST_CHANNEL,
                        ask=answers(data["plan_sha256"][:PREFIX_LENGTH]))
        self.assertEqual(second["sequence"], 2)
        self.assertEqual(second["previous_record_sha256"], first["record_sha256"])

    def test_review_reports_changes_against_previous_version(self):
        previous = self.root / "previous.planspec.json"
        shutil.copyfile(self.plan, previous)
        self.edit_plan(lambda plan: plan["walls"][0].update({"thickness_m": 0.25}))
        review_dir, data = self.review(previous=previous)
        sheet = (review_dir / REVIEW_MD).read_text(encoding="utf-8")
        self.assertIn("## 6. Cambios respecto de la versión anterior", sheet)
        self.assertIn("Modificado muro `wall-south`: thickness_m", sheet)
        self.assertIsNotNone(data["previous"])
        self.assertEqual(self.approve(review_dir)["decision"], "approved")

    def test_review_directory_is_never_overwritten(self):
        self.review()
        with self.assertRaises(FileExistsError):
            self.review()


if __name__ == "__main__":
    unittest.main()
