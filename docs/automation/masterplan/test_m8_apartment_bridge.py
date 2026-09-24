from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from m8_apartment_bridge import ApartmentBridgeError, bind


class ApartmentBridgeTests(unittest.TestCase):
    def test_rejects_release_dwg_that_differs_from_external_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            m7, m8 = base / "m7", base / "m8"
            for root in (m7, m8):
                (root / "cad").mkdir(parents=True)
                (root / "cad" / "evidence.json").write_text("{}")
            (m7 / "model-plan.json").write_text("{}")
            release = {"entity_count": 55}
            compiled = {"commands_sha256": "COMMANDS"}
            local = {"entity_count": 55, "dwg_sha256": "DIFFERENT",
                     "capture_sha256": "CAPTURE", "contract_sha256": "CONTRACT",
                     "report_sha256": "REPORT"}
            l4 = {"status": "passed_scoped_l4", "geometry_matches": 55,
                  "geometry_total": 55, "dwg_sha256": "ORIGINAL"}
            cad = {"dwg": {"sha256": "ORIGINAL"},
                   "capture": {"sha256": "CAPTURE"},
                   "commands_sha256": "COMMANDS"}
            with patch("m8_apartment_bridge.validate", return_value=(release, compiled)), \
                    patch("m8_apartment_bridge.verify", return_value=local), \
                    patch("m8_apartment_bridge.assess_apartment", return_value=l4), \
                    patch("m8_apartment_bridge.verify_owned_cad_evidence",
                          return_value=cad):
                with self.assertRaisesRegex(ApartmentBridgeError,
                                            "M8 replay and audited M7 geometry differ"):
                    bind(m8, m7, base / "image.jpg", base / "binary.exe",
                         base / "external.json")


if __name__ == "__main__":
    unittest.main()
