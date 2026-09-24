"""Portable contract tests for the scoped CLI development gate."""

import json
from pathlib import Path
import tempfile
import unittest

from cli_development_trial import (CliAbstained, CliTrialError,
                                   check_ct1, check_explicit_line_graph,
                                   check_rectangle, parse_cli_events)


def rectangle(width=0.2, height=0.4):
    source = {"region_px": [1, 1, 10, 10], "confidence": 0.9,
              "classification": "measured"}
    return {"schema_version": "planspec-1", "units": "m",
            "origin": {"x": 0, "y": 0},
            "nodes": [{"id": name, "x": x, "y": y, "source": source}
                      for name, x, y in (("a", 0, 0), ("b", width, 0),
                                         ("c", width, height), ("d", 0, height))],
            "lines": [{"id": f"l{i}", "start": a, "end": b,
                       "layer": "0", "source": source}
                      for i, (a, b) in enumerate((("a", "b"), ("b", "c"),
                                                    ("c", "d"), ("d", "a")), 1)],
            "circles": [], "dimensions": []}


def two_bay_network():
    source = {"region_px": [1, 1, 10, 10], "confidence": 0.9,
              "classification": "measured"}
    vertices = [[0, 0], [2, 0], [5, 0], [5, 1.5],
                [2, 1.5], [0, 1.5]]
    edges = [[0, 1], [1, 2], [2, 3], [3, 4],
             [4, 5], [5, 0], [1, 4]]
    plan = {"schema_version": "planspec-1", "units": "m",
            "origin": {"x": 0, "y": 0},
            "nodes": [{"id": f"n{i}", "x": x, "y": y, "source": source}
                      for i, (x, y) in enumerate(vertices)],
            "lines": [{"id": f"l{i}", "start": f"n{a}", "end": f"n{b}",
                       "layer": "0", "source": source}
                      for i, (a, b) in enumerate(edges)],
            "circles": [], "dimensions": []}
    return plan, vertices, edges


class CliDevelopmentTrialTests(unittest.TestCase):
    def test_measured_rectangle_compiles(self):
        result = check_ct1(rectangle(), 100, 100)
        self.assertTrue(result["executable"])
        self.assertEqual(len(result["commands"]), 4)

    def test_wrong_metric_or_open_contour_rejected(self):
        with self.assertRaises(CliTrialError):
            check_ct1(rectangle(height=0.41), 100, 100)
        plan = rectangle()
        plan["lines"][-1]["end"] = "b"
        with self.assertRaises(CliTrialError):
            check_ct1(plan, 100, 100)

    def test_other_frozen_rectangle_size(self):
        self.assertEqual(len(check_rectangle(rectangle(2.85, 3.70), 100, 100,
                                             2.85, 3.70)["commands"]), 4)

    def test_explicit_two_bay_network_and_adversarial_edge(self):
        plan, vertices, edges = two_bay_network()
        self.assertEqual(len(check_explicit_line_graph(
            plan, 100, 100, vertices, edges, 2)["commands"]), 7)
        plan["lines"][-1]["end"] = "n3"
        with self.assertRaises(CliTrialError):
            check_explicit_line_graph(plan, 100, 100, vertices, edges, 2)

    def test_explicit_graph_rejects_invalid_frozen_oracle(self):
        plan, vertices, edges = two_bay_network()
        with self.assertRaises(CliTrialError):
            check_explicit_line_graph(plan, 100, 100, vertices, edges, 3)
        with self.assertRaises(CliTrialError):
            check_explicit_line_graph(plan, 100, 100, vertices,
                                      edges[:-1] + [[0, 1]], 2)

    def test_cli_requires_single_message_and_rejects_tools(self):
        events = [{"type": "thread.started"}, {"type": "turn.started"},
                  {"type": "item.completed", "item": {
                      "type": "agent_message", "text": json.dumps(rectangle())}},
                  {"type": "turn.completed", "usage": {
                      "input_tokens": 10, "cached_input_tokens": 0,
                      "output_tokens": 20}}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text("\n".join(json.dumps(event) for event in events),
                            encoding="utf-8")
            self.assertEqual(parse_cli_events(path)[1]["output_tokens"], 20)
            events.insert(2, {"type": "item.completed", "item": {
                "type": "command_execution", "text": "unexpected"}})
            path.write_text("\n".join(json.dumps(event) for event in events),
                            encoding="utf-8")
            with self.assertRaises(CliTrialError):
                parse_cli_events(path)

    def test_explicit_abstention_is_not_parsed_as_geometry(self):
        events = [{"type": "thread.started"}, {"type": "turn.started"},
                  {"type": "item.completed", "item": {
                      "type": "agent_message", "text": "UNSUPPORTED"}},
                  {"type": "turn.completed", "usage": {
                      "input_tokens": 10, "cached_input_tokens": 0,
                      "output_tokens": 1}}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text("\n".join(json.dumps(event) for event in events),
                            encoding="utf-8")
            with self.assertRaises(CliAbstained):
                parse_cli_events(path)


if __name__ == "__main__":
    unittest.main()
