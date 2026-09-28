"""Regression for Actions visibility lag immediately after pushing an open PR."""
import unittest
from unittest.mock import patch
import fork_sync_ci as ci


class DispatchRaceTests(unittest.TestCase):
    def test_open_pr_at_exact_head_does_not_dispatch(self):
        pull = {"state": "open", "number": 2, "html_url": "https://example.invalid/pr/2",
                "head": {"sha": "a" * 40, "repo": {"full_name": ci.REPO}}}
        with patch.object(ci, "gh", return_value=[pull]), patch.object(ci, "claim_dispatch") as dispatch:
            state = ci.start_when_absent(".", "a" * 40, "codex/desktop-distribution", "base", "auto")
        dispatch.assert_not_called()
        self.assertEqual(state["state"], "awaiting_pull_request_run")
        self.assertEqual(state["pull_request"], 2)

    def test_unrelated_or_absent_pr_allows_claimed_dispatch(self):
        unrelated = {"state": "open", "head": {"sha": "b" * 40, "repo": {"full_name": ci.REPO}}}
        for pulls in ([], [unrelated]):
            with self.subTest(pulls=pulls), patch.object(ci, "gh", return_value=pulls), patch.object(ci, "claim_dispatch", return_value={"state": "dispatched"}) as dispatch:
                state = ci.start_when_absent(".", "a" * 40, "codex/desktop-distribution", "base", "auto")
                dispatch.assert_called_once_with(".", "a" * 40, "codex/desktop-distribution", "base", "auto")
                self.assertEqual(state["state"], "dispatched")

    def test_failed_pr_observation_cannot_dispatch(self):
        with patch.object(ci, "gh", side_effect=RuntimeError("API unavailable")), patch.object(ci, "claim_dispatch") as dispatch:
            with self.assertRaises(RuntimeError):
                ci.start_when_absent(".", "a" * 40, "codex/desktop-distribution", "base", "auto")
        dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
