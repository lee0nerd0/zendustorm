"""Offline tests for stormtwin.weather parsing and callout summaries.  Run: python -m unittest discover -s tests -t . -v"""

# =============================================================================
# Imports
# =============================================================================
import unittest

from stormtwin.weather import HOURLY_COLUMNS, normalise, summarise_callouts

# =============================================================================
# Fixtures
# =============================================================================
CFG = {"hours_before_callout": 2, "hours_after_callout": 2}


def hour(stamp, temp, wind=10, precip=None):
    return {"datetime_local": stamp, "temp_c": temp, "wind_kmh": wind, "precip_mm": precip}


# =============================================================================
# Tests
# =============================================================================
class WeatherTests(unittest.TestCase):
    def test_normalise_converts_and_blanks(self):
        rows = [{"Date/Time (LST)": "2026-01-01 00:00", "Temp (°C)": "-10.1", "Precip. Amount (mm)": "", "Weather": "NA"}]
        rec = normalise(rows, HOURLY_COLUMNS)[0]
        self.assertEqual(rec["temp_c"], -10.1)
        self.assertIsNone(rec["precip_mm"])
        self.assertEqual(rec["datetime_local"], "2026-01-01 00:00")

    def test_summary_windows(self):
        hourly = [hour("2026-01-14 22:00", -9), hour("2026-01-14 23:00", -5, precip=1.0),
                  hour("2026-01-15 00:00", -12, wind=40, precip=0.5), hour("2026-01-15 01:00", None),
                  hour("2026-01-15 02:00", -20)]  # 02:00 is outside [22:00, 02:00)
        daily = [{"date": "2026-01-15", "snow_cm": 20.2}]
        n = summarise_callouts([{"id": "c1", "calloutLocal": "2026-01-15T00:00:00"}], hourly, daily, CFG)[0]
        self.assertEqual(n["min_temp_before_c"], -9)
        self.assertEqual(n["min_temp_window_c"], -12)
        self.assertEqual(n["max_wind_window_kmh"], 40)
        self.assertEqual(n["precip_window_mm"], 1.5)
        self.assertEqual(n["hours_with_data"], 3)
        self.assertEqual(n["daily_snow_cm"], 20.2)


if __name__ == "__main__":
    unittest.main()
