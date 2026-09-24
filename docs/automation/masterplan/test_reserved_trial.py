"""Synthetic M7 matrix/journal tests; no model or CAD process runs."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from reserved_oracle import freeze
from reserved_trial import TrialError, TrialJournal
import test_reserved_oracle


class ReservedTrialTests(unittest.TestCase):
    def make_journal(self, directory):
        root, cohort, images, oracle_root, oracles = test_reserved_oracle.ReservedOracleTests().make_inputs(directory)
        manifest = (Path(directory) / "oracle-freeze.json").resolve()
        freeze(cohort, images, input_root=root, oracle_paths=oracles,
               oracle_root=oracle_root, output=manifest)
        run = (Path(directory) / "run").resolve()
        run.mkdir()
        protocol = (Path(directory) / "protocol.json").resolve()
        protocol.write_text('{"version":"synthetic-v1"}\n', encoding="utf-8")
        binary = (Path(directory) / "synthetic-cad.bin").resolve()
        binary.write_bytes(b"synthetic cad binary")
        args = dict(cohort_path=cohort, image_paths=images, input_root=root,
                    oracle_manifest_path=manifest, oracle_paths=oracles,
                    oracle_root=oracle_root,
                    arm_protocols={"baseline": protocol, "candidate": protocol},
                    arm_binaries={"baseline": binary, "candidate": binary},
                    requested_model="gpt-6-luna", effort="medium",
                    hardware_label="synthetic-host")
        journal = TrialJournal(run / "attempts.jsonl", "synthetic-m7", **args)
        return journal, args, run, oracles, binary

    def test_36_slot_matrix_is_durable_and_reconciles_one_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, args, run, _, _ = self.make_journal(directory)
            self.assertEqual(journal.snapshot()["slots_total"], 36)
            first = journal.reserve("baseline", "case-0", 1, "private-request-1")
            self.assertEqual(first["status"], "reserved")
            self.assertTrue(journal.snapshot()["pending_uncertain"])
            with self.assertRaisesRegex(TrialError, "uncertain"):
                journal.reserve("candidate", "case-0", 1, "private-request-2")
            resumed = TrialJournal(run / "attempts.jsonl", "synthetic-m7", **args)
            evidence = run / "case-0-r1.json"
            evidence.write_text('{"synthetic":"observed"}\n', encoding="utf-8")
            result = resumed.record_result("baseline", "case-0", 1, "private-request-1",
                                           disposition="completed", effective_model="gpt-6-luna",
                                           evidence_path=evidence)
            self.assertEqual(result["status"], "recorded")
            self.assertEqual(resumed.record_result(
                "baseline", "case-0", 1, "private-request-1", disposition="completed",
                effective_model="gpt-6-luna", evidence_path=evidence)["status"],
                "already_recorded")
            with self.assertRaisesRegex(TrialError, "already consumed"):
                resumed.reserve("baseline", "case-0", 1, "different-request")
            resumed.reserve("candidate", "case-0", 1, "private-request-2")
            resumed.record_result("candidate", "case-0", 1, "private-request-2",
                                  disposition="failed", effective_model="unknown",
                                  evidence_path=evidence)
            snapshot = resumed.snapshot()
            self.assertEqual((snapshot["slots_reserved"], snapshot["slots_remaining"]), (2, 34))
            self.assertEqual(snapshot["dispositions"],
                             {"completed": 1, "failed": 1, "partial": 0, "uncertain": 0})
            raw = (run / "attempts.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("private-request", raw)
            self.assertNotIn(str(run), raw)
            self.assertNotIn("synthetic-host", raw)

    def test_uncertain_consumes_slot_and_wrong_model_cannot_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, run, _, _ = self.make_journal(directory)
            journal.reserve("baseline", "case-0", 1, "request-1")
            evidence = run / "result.json"
            evidence.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(TrialError, "effective model"):
                journal.record_result("baseline", "case-0", 1, "request-1",
                                      disposition="completed", effective_model="unknown",
                                      evidence_path=evidence)
            journal.record_result("baseline", "case-0", 1, "request-1",
                                  disposition="uncertain", effective_model="unknown")
            with self.assertRaisesRegex(TrialError, "already consumed"):
                journal.reserve("baseline", "case-0", 1, "request-2")
            self.assertEqual(journal.snapshot()["dispositions"]["uncertain"], 1)
            self.assertEqual(journal.reserve("candidate", "case-0", 1, "request-3")["status"],
                             "reserved")

    def test_source_binary_and_journal_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, run, oracles, binary = self.make_journal(directory)
            journal.reserve("baseline", "case-0", 1, "request-1")
            path = run / "attempts.jsonl"
            original = path.read_bytes()
            path.write_bytes(original.replace(b'"baseline"', b'"candidate"', 1))
            with self.assertRaisesRegex(TrialError, "hash chain"):
                journal.snapshot()
            path.write_bytes(original)
            binary.write_bytes(b"changed")
            with self.assertRaisesRegex(TrialError, "frozen identities changed"):
                journal.snapshot()
            binary.write_bytes(b"synthetic cad binary")
            oracle = json.loads(oracles["case-0"].read_text(encoding="utf-8"))
            oracle["checks"]["metric"][0]["criterion"] = "changed"
            oracles["case-0"].write_text(json.dumps(oracle), encoding="utf-8")
            with self.assertRaisesRegex(TrialError, "not ready"):
                journal.snapshot()

    def test_two_writers_cannot_reserve_the_same_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, args, run, _, _ = self.make_journal(directory)
            journal.snapshot()
            other = TrialJournal(run / "attempts.jsonl", "synthetic-m7", **args)
            def attempt(item):
                try:
                    item[0].reserve("baseline", "case-0", 1, item[1])
                    return "reserved"
                except TrialError:
                    return "rejected"
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(attempt, ((journal, "request-a"),
                                                   (other, "request-b"))))
            self.assertEqual(sorted(outcomes), ["rejected", "reserved"])
            self.assertEqual(journal.snapshot()["slots_reserved"], 1)

    def test_arm_specific_binary_is_frozen_without_changing_shared_model(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, args, run, _, _ = self.make_journal(directory)
            candidate = (Path(directory) / "candidate-cad.bin").resolve()
            candidate.write_bytes(b"candidate build")
            args["arm_binaries"] = {"baseline": args["arm_binaries"]["baseline"],
                                    "candidate": candidate}
            journal = TrialJournal(run / "attempts.jsonl", "synthetic-m7", **args)
            journal.snapshot()
            candidate.write_bytes(b"changed candidate build")
            with self.assertRaisesRegex(TrialError, "frozen identities changed"):
                journal.snapshot()

    def test_recorded_result_file_is_rechecked_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, args, run, _, _ = self.make_journal(directory)
            journal.reserve("baseline", "case-0", 1, "request-1")
            evidence = run / "result.json"
            evidence.write_text('{"status":"observed"}\n', encoding="utf-8")
            journal.record_result("baseline", "case-0", 1, "request-1",
                                  disposition="completed", effective_model="gpt-6-luna",
                                  evidence_path=evidence)
            resumed = TrialJournal(run / "attempts.jsonl", "synthetic-m7", **args)
            self.assertEqual(resumed.snapshot()["dispositions"]["completed"], 1)
            evidence.write_text('{"status":"changed"}\n', encoding="utf-8")
            with self.assertRaisesRegex(TrialError, "evidence changed"):
                resumed.snapshot()

    def test_complete_matrix_keeps_all_36_attempts_in_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            journal, _, run, _, _ = self.make_journal(directory)
            evidence = run / "partial.json"
            evidence.write_text('{"synthetic":"partial"}\n', encoding="utf-8")
            for arm in ("baseline", "candidate"):
                for case in range(6):
                    for repetition in (1, 2, 3):
                        request = f"{arm}-case-{case}-r{repetition}"
                        journal.reserve(arm, f"case-{case}", repetition, request)
                        journal.record_result(arm, f"case-{case}", repetition, request,
                                              disposition="partial", effective_model="unknown",
                                              evidence_path=evidence)
            snapshot = journal.snapshot()
            self.assertEqual((snapshot["slots_reserved"], snapshot["slots_remaining"]), (36, 0))
            self.assertEqual(snapshot["dispositions"]["partial"], 36)


if __name__ == "__main__":
    unittest.main()
