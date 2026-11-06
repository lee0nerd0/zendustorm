"""Offline tests for stormtwin.replay (stdlib only).  Run: python -m unittest discover -s tests -t . -v"""

# =============================================================================
# Imports
# =============================================================================
import json
import tempfile
import unittest
from pathlib import Path

from stormtwin.config import load_settings
from stormtwin.replay import ReplayError, parse_input, run_replay, sanitize

# =============================================================================
# Fixtures
# =============================================================================
SAMPLE_INPUT = {
    "night": "2026-01-10",
    "callout_local": "2026-01-10T02:00:00",
    "weather": {"daily": {}, "hourly": []},
    "trucks": [{"name": "T-102"}, {"name": "T-101"}],
    "records_since_your_data_ends": {"StatusData": [], "FaultData": [], "WorkOrder": []},
}


# =============================================================================
# Tests
# =============================================================================
class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, payload):
        inp, out = self.dir / "in.json", self.dir / "out.json"
        inp.write_text(json.dumps(payload))
        run_replay(inp, out, self.settings)
        return out.read_bytes()

    def test_output_shape_and_determinism(self):
        first = self._run(SAMPLE_INPUT)
        self.assertEqual(first, self._run(SAMPLE_INPUT))  # byte-identical re-run
        out = json.loads(first)
        self.assertEqual(out["persona"], "maintenance")
        self.assertEqual(out["trucks"], {"T-101": "ok", "T-102": "ok"})

    def test_truck_shapes_accepted(self):
        for trucks in (["T-101"], [{"truck": "T-101"}], {"T-101": {}}, [{"vehicleName": "T-101"}]):
            night = parse_input({**SAMPLE_INPUT, "trucks": trucks}, self.settings)
            self.assertEqual(night["trucks"], ["T-101"])

    def test_missing_trucks_falls_back_to_roster(self):
        night = parse_input({**SAMPLE_INPUT, "trucks": None}, self.settings)
        self.assertEqual(len(night["trucks"]), 30)

    def test_sanitize_repairs_bad_labels(self):
        self.assertEqual(sanitize({"T-101": "boom", "T-999": "ok"}, ["T-101", "T-102"]), {"T-101": "ok", "T-102": "ok"})

    def test_bad_input_raises(self):
        with self.assertRaises(ReplayError):
            run_replay(self.dir / "missing.json", self.dir / "o.json", self.settings)


if __name__ == "__main__":
    unittest.main()
