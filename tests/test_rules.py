"""Tests for the hidden-rule classifier and the replay wiring.  Run: python -m unittest discover -s tests -t . -v"""

# =============================================================================
# Imports
# =============================================================================
import json
import tempfile
import unittest
from pathlib import Path

from stormtwin.config import load_settings
from stormtwin.replay import run_replay
from stormtwin.rules import classify

# =============================================================================
# Fixtures
# =============================================================================
SETTINGS = load_settings()
RULES = SETTINGS["rules"]


def feats(**kw):
    base = {"voltage_v": 12.6, "voltage_at": "2026-01-14T18:00:00", "battery_replaced_since_reading": False,
            "pto_since_service_h": 100.0, "pto_info": {}, "night_low_c": -5.0, "snow_cm": 2.0}
    return {**base, **kw}


# =============================================================================
# Classifier: boundaries come from data/derived/evidence.json margins
# =============================================================================
class ClassifyTests(unittest.TestCase):
    def test_no_start_needs_low_voltage_and_cold(self):
        self.assertEqual(classify(feats(voltage_v=12.24, night_low_c=-10.5), RULES)[0], "no_start")
        self.assertEqual(classify(feats(voltage_v=12.25, night_low_c=-20.0), RULES)[0], "ok")   # healthy battery
        self.assertEqual(classify(feats(voltage_v=11.65, night_low_c=-9.2), RULES)[0], "ok")    # not cold enough

    def test_new_battery_voids_low_reading(self):
        f = feats(voltage_v=11.9, night_low_c=-15.0, battery_replaced_since_reading=True)
        self.assertEqual(classify(f, RULES)[0], "ok")

    def test_hydraulic_needs_wear_and_heavy_snow(self):
        self.assertEqual(classify(feats(pto_since_service_h=181.8, snow_cm=9.8), RULES)[0], "hydraulic")
        self.assertEqual(classify(feats(pto_since_service_h=189.2, snow_cm=2.6), RULES)[0], "ok")  # light snow
        self.assertEqual(classify(feats(pto_since_service_h=180.0, snow_cm=20.0), RULES)[0], "ok")

    def test_no_start_wins_over_hydraulic(self):
        f = feats(voltage_v=12.0, night_low_c=-14.0, pto_since_service_h=190.0, snow_cm=20.0)
        self.assertEqual(classify(f, RULES)[0], "no_start")

    def test_missing_numbers_never_flag(self):
        f = feats(voltage_v=None, pto_since_service_h=None, night_low_c=-20.0, snow_cm=30.0)
        self.assertEqual(classify(f, RULES)[0], "ok")


# =============================================================================
# Replay end to end on a historical night (Jan 15 2026) using committed data
# =============================================================================
class ReplayHistoricalTests(unittest.TestCase):
    def test_jan15_reproduces_history(self):
        payload = {"night": "2026-01-15", "callout_local": "2026-01-15T00:00:00",
                   "weather": {}, "trucks": [f"T-{i}" for i in range(101, 131)],
                   "records_since_your_data_ends": {}}
        with tempfile.TemporaryDirectory() as d:
            inp, out = Path(d) / "in.json", Path(d) / "out.json"
            inp.write_text(json.dumps(payload))
            got = run_replay(inp, out, SETTINGS)["trucks"]
        flagged = {t: l for t, l in got.items() if l != "ok"}
        self.assertEqual(flagged, {"T-111": "no_start", "T-112": "no_start", "T-119": "no_start",
                                   "T-108": "hydraulic", "T-120": "hydraulic", "T-125": "hydraulic"})

    def test_input_weather_and_battery_record_override_history(self):
        # Warm input weather removes the no-starts; a new battery record would too.
        payload = {"night": "2026-01-15", "callout_local": "2026-01-15T00:00:00",
                   "weather": {"hourly": [{"time": f"2026-01-14T{h:02d}:00", "temp": 1.0} for h in range(18, 24)]
                                       + [{"time": f"2026-01-15T{h:02d}:00", "temp": 1.0} for h in range(0, 8)],
                               "daily": [{"date": "2026-01-15", "snowfall_cm": 1.0}]},
                   "trucks": ["T-111", "T-108"], "records_since_your_data_ends": {}}
        with tempfile.TemporaryDirectory() as d:
            inp, out = Path(d) / "in.json", Path(d) / "out.json"
            inp.write_text(json.dumps(payload))
            got = run_replay(inp, out, SETTINGS)["trucks"]
        self.assertEqual(got, {"T-108": "ok", "T-111": "ok"})


if __name__ == "__main__":
    unittest.main()
