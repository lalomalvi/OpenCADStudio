"""Synthetic stacked-dimension contract tests."""

import copy
import unittest

from cli_development_trial import check_rectangle
from measurement_stacked_span import StackedSpanError, compile_lower_span_rectangle


FROZEN = {"expected_upper_span_m": 1.2,
          "expected_lower_span_m": 1.5,
          "expected_level_delta_m": 2.4}


def measurement():
    return {"schema_version": "ocs-stacked-spans-1", "status": "measured",
            "units": "m", "upper_span_m": 1.2, "lower_span_m": 1.5,
            "level_delta_m": 2.4, "confidence": 0.9,
            "source_regions": {"upper_span_px": [120, 400, 300, 430],
                               "lower_span_px": [100, 450, 320, 480],
                               "level_delta_px": [500, 100, 600, 140]}}


class StackedSpanTests(unittest.TestCase):
    def test_uses_lower_span_and_compiles(self):
        plan = compile_lower_span_rectangle(
            measurement(), frozen=FROZEN, image_width=900, image_height=600)
        self.assertEqual(len(check_rectangle(plan, 900, 600, 1.5, 2.4)["commands"]), 4)
        self.assertEqual({item["source"]["classification"]
                          for item in plan["lines"]}, {"inferred"})

    def test_wrong_lower_metric_rejected(self):
        value = measurement()
        value["lower_span_m"] = 1.2
        with self.assertRaises(StackedSpanError):
            compile_lower_span_rectangle(value, frozen=FROZEN,
                                         image_width=900, image_height=600)

    def test_reversed_vertical_order_rejected(self):
        value = measurement()
        value["source_regions"]["lower_span_px"][1:3] = [410, 320]
        with self.assertRaises(StackedSpanError):
            compile_lower_span_rectangle(value, frozen=FROZEN,
                                         image_width=900, image_height=600)

    def test_source_and_contract_rejected(self):
        value = measurement()
        value["source_regions"]["level_delta_px"][3] = 601
        with self.assertRaises(StackedSpanError):
            compile_lower_span_rectangle(value, frozen=FROZEN,
                                         image_width=900, image_height=600)
        value = copy.deepcopy(measurement())
        del value["confidence"]
        with self.assertRaises(StackedSpanError):
            compile_lower_span_rectangle(value, frozen=FROZEN,
                                         image_width=900, image_height=600)


if __name__ == "__main__":
    unittest.main()
