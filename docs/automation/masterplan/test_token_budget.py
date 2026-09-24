"""Synthetic usage only; no model call or private rollout."""

from pathlib import Path
import tempfile
import unittest

from token_budget import TokenBudget, TokenBudgetError


USAGE = {"input_tokens": 6, "cached_input_tokens": 2,
         "cache_write_input_tokens": 0, "output_tokens": 4,
         "reasoning_output_tokens": 1, "total_tokens": 10}


class TokenBudgetTests(unittest.TestCase):
    def budget(self, directory, *, tokens=20, responses=2):
        return TokenBudget(Path(directory) / "tokens.jsonl", "synthetic-run",
                           max_total_tokens=tokens, max_responses=responses)

    def test_reserve_complete_restart_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            budget = self.budget(directory)
            self.assertEqual(budget.reserve("req-1")["status"], "reserved")
            self.assertEqual(budget.complete("req-1", "resp-1", USAGE)["total_tokens"], 10)
            resumed = self.budget(directory)
            self.assertEqual(resumed.reserve("req-1")["status"], "already_completed")
            self.assertEqual(resumed.complete("req-1", "resp-1", USAGE)["status"],
                             "already_completed")
            resumed.reserve("req-2")
            with self.assertRaisesRegex(TokenBudgetError, "already counted"):
                resumed.complete("req-2", "resp-1", USAGE)
            self.assertEqual(resumed.complete("req-2", "resp-2", USAGE)["total_tokens"], 20)
            snapshot = resumed.snapshot()
            self.assertEqual((snapshot["responses_completed"], snapshot["total_tokens"]),
                             (2, 20))
            self.assertTrue(snapshot["exhausted"])
            self.assertFalse(snapshot["pending_uncertain"])
            with self.assertRaisesRegex(TokenBudgetError, "budget is exhausted"):
                resumed.reserve("req-3")
            journal = (Path(directory) / "tokens.jsonl").read_text()
            self.assertNotIn("resp-1", journal)
            self.assertNotIn("req-1", journal)

    def test_uncertain_response_blocks_new_request_until_reconciled(self):
        with tempfile.TemporaryDirectory() as directory:
            self.budget(directory).reserve("req-1")
            resumed = self.budget(directory)
            with self.assertRaisesRegex(TokenBudgetError, "uncertain"):
                resumed.reserve("req-1")
            with self.assertRaisesRegex(TokenBudgetError, "uncertain"):
                resumed.reserve("req-2")
            self.assertEqual(resumed.complete("req-1", "resp-1", USAGE)["total_tokens"], 10)
            self.assertEqual(resumed.reserve("req-2")["status"], "reserved")

    def test_overrun_is_recorded_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            budget = self.budget(directory, tokens=9)
            budget.reserve("req-1")
            with self.assertRaisesRegex(TokenBudgetError, "exceeded"):
                budget.complete("req-1", "resp-1", USAGE)
            with self.assertRaisesRegex(TokenBudgetError, "exceeded"):
                self.budget(directory, tokens=9).complete("req-1", "resp-1", USAGE)
            with self.assertRaisesRegex(TokenBudgetError, "budget is exhausted"):
                budget.reserve("req-2")

    def test_journal_tamper_and_limit_change_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            budget = self.budget(directory)
            budget.reserve("req-1")
            with self.assertRaisesRegex(TokenBudgetError, "limits differ"):
                self.budget(directory, tokens=21).reserve("req-2")
            checkpoint = Path(directory) / "tokens.jsonl"
            checkpoint.write_text(checkpoint.read_text().replace('"max_total_tokens":20',
                                                                  '"max_total_tokens":21'))
            with self.assertRaisesRegex(TokenBudgetError, "chain is invalid"):
                budget.reserve("req-2")


if __name__ == "__main__":
    unittest.main()
