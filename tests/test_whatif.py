import json
import tempfile
import unittest
from pathlib import Path

from stormtwin.config import load_settings
from stormtwin.whatif import WhatIfError, build_scenario, parse_fixes, run_whatif

SETTINGS = load_settings()


class WhatIfTests(unittest.TestCase):
    def test_tonight_default(self):
        r = run_whatif(SETTINGS)
        self.assertEqual(r["available"], 23)
        self.assertEqual(r["fix_first"][0], "T-109")

    def test_fixes_and_mild_weather(self):
        self.assertEqual(run_whatif(SETTINGS, fixes=["T-109:battery"])["available"], 24)
        self.assertEqual(run_whatif(SETTINGS, low=-8, snow=4)["available"], 30)

    def test_forecast_file_and_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "fc.json"
            p.write_text(json.dumps({"night_low_c": -19, "snow_cm": 30, "callout_local": "2026-12-16T01:00:00"}))
            sc = build_scenario(SETTINGS, forecast=p, snow=5)
        self.assertEqual((sc["night_low_c"], sc["snow_cm"], sc["callout_local"]), (-19, 5, "2026-12-16T01:00:00"))
        self.assertEqual(build_scenario(SETTINGS, callout="00:30")["callout_local"], "2026-12-16T00:30:00")

    def test_bad_fix_kind(self):
        with self.assertRaises(WhatIfError):
            parse_fixes(["T-101:tires"])


if __name__ == "__main__":
    unittest.main()
