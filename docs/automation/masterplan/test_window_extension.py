import copy
import unittest
from unittest.mock import patch

from window_extension import WindowExtensionError, extend


class WindowExtensionTests(unittest.TestCase):
    def setUp(self):
        self.source = {"classification": "inferred", "confidence": 0.7,
                       "region_px": [0, 0, 10, 10]}
        self.base = {
            "schema_version": "planspec-11",
            "nodes": [{"id": "a", "x": 0, "y": 0},
                      {"id": "b", "x": 0, "y": 4}],
            "lines": [{"id": "host", "start": "a", "end": "b", "layer": "0"}],
            "topology": {"contours": [{"line_ids": ["host"]}]},
            "window_symbols": [],
        }
        self.clear = {"executable": True, "unsupported": [], "quality_blockers": [],
                      "window_symbol_qa": {"status": "clear"},
                      "topology": {"status": "validated"}}

    def test_vertical_host_preserves_base_and_inserts_six_lines(self):
        original = copy.deepcopy(self.base)
        with patch("window_extension.dry_run", return_value=self.clear):
            plan, _ = extend(self.base, host_id="host", window_id="west",
                             first=(0, 1), second=(0, 2), inward=(0.15, 0),
                             source=self.source)
        self.assertEqual(self.base, original)
        self.assertEqual(len(plan["lines"]), 6)
        self.assertEqual(plan["topology"]["contours"][0]["line_ids"],
                         ["west-wall-first", "west-outer", "west-wall-second"])
        nodes = {item["id"]: item for item in plan["nodes"]}
        self.assertEqual((nodes["west-inner-first"]["x"],
                          nodes["west-inner-first"]["y"]), (0.15, 1.0))

    def test_reversed_interval_rejected(self):
        with self.assertRaisesRegex(WindowExtensionError, "directed host"):
            extend(self.base, host_id="host", window_id="west",
                   first=(0, 2), second=(0, 1), inward=(0.15, 0),
                   source=self.source)

    def test_nonperpendicular_frame_rejected(self):
        with self.assertRaisesRegex(WindowExtensionError, "directed host"):
            extend(self.base, host_id="host", window_id="west",
                   first=(0, 1), second=(0, 2), inward=(0.15, 0.1),
                   source=self.source)

    def test_cad_blocker_rejected(self):
        blocked = {**self.clear, "window_symbol_qa": {"status": "blocked"}}
        with patch("window_extension.dry_run", return_value=blocked):
            with self.assertRaisesRegex(WindowExtensionError, "preflight"):
                extend(self.base, host_id="host", window_id="west",
                       first=(0, 1), second=(0, 2), inward=(0.15, 0),
                       source=self.source)


if __name__ == "__main__":
    unittest.main()
