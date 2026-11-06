"""Fleet history: turn raw API rows into per-truck timelines the rules can query.

Why this module exists
----------------------
* Telematics (StatusData, FaultData) is keyed by DEVICE and stamped in UTC.
* The shop and dispatch systems are keyed by TRUCK and stamped in LOCAL time.
* Devices move between trucks (T-118 and T-129 swapped devices on 2026-01-08), so a device's readings
  must be attributed to whichever truck it was in AT THE TIME of the reading.
* Work-order meter readings are sometimes empty; we fall back to the telematics PTO reading at that time.

All times inside this module are naive LOCAL datetimes (America/Toronto wall clock).
UTC is converted with a fixed offset from config (EST, -5h): every date we model (Nov 2 onward, Dec, Jan)
is outside daylight saving time, and a fixed offset keeps the replay free of tz-database differences.
"""

# =============================================================================
# Imports
# =============================================================================
import bisect
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("stormtwin.history")

# =============================================================================
# Constants
# =============================================================================
DIAG_VOLTAGE = "DiagnosticBatteryRestingVoltageId"
DIAG_PTO = "DiagnosticPtoHoursId"
DIAG_ENGINE = "DiagnosticEngineHoursId"

WO_HYD_RESET = ("HYDRAULIC_SERVICE", "HYDRAULIC_REPAIR")  # work orders that reset hydraulic wear
WO_BATTERY = "BATTERY_REPLACED"

LOCAL_FMT = "%Y-%m-%dT%H:%M:%S"


# =============================================================================
# Time helpers
# =============================================================================
def parse_local(stamp):
    """'2026-01-15T00:00:00' -> naive local datetime."""
    return datetime.strptime(stamp[:19], LOCAL_FMT)


def utc_to_local(stamp, utc_offset_hours):
    """'2026-01-15T05:00:00Z' -> naive local datetime using a fixed offset."""
    return datetime.strptime(stamp[:19], LOCAL_FMT) + timedelta(hours=utc_offset_hours)


# =============================================================================
# Device -> truck mapping (time-aware)
# =============================================================================
class DeviceMap:
    """Answers 'which truck was device X in at UTC time T?' from DeviceAssignment rows."""

    def __init__(self, assignments):
        self._by_device = defaultdict(list)
        for a in assignments:
            self._by_device[a["device"]["id"]].append((a["activeFrom"], a["activeTo"], a["vehicleName"]))

    def truck_for(self, device_id, utc_stamp):
        # ISO-8601 UTC strings compare correctly as text.
        for start, end, truck in self._by_device.get(device_id, ()):
            if start <= utc_stamp < end:
                return truck
        return None


# =============================================================================
# Fleet history
# =============================================================================
class FleetHistory:
    """Per-truck timelines of readings and shop events, all in local time."""

    def __init__(self, raw, utc_offset_hours):
        self.utc_offset = utc_offset_hours
        self.trucks = sorted(v["name"] for v in raw.get("Vehicle", []))
        self.device_map = DeviceMap(raw.get("DeviceAssignment", []))
        self.readings = defaultdict(lambda: defaultdict(list))  # truck -> diag -> sorted [(local_dt, value)]
        self.work_orders = defaultdict(list)                     # truck -> sorted [(local_dt, row)]
        self.unmapped = 0
        self.add_records(raw)

    # --- ingestion ------------------------------------------------------------
    def add_records(self, records):
        """Add StatusData / WorkOrder rows (used at load time and again for the replay's extra records)."""
        for s in records.get("StatusData", []) or []:
            truck = self.device_map.truck_for(s["device"]["id"], s["dateTime"])
            if truck is None or s.get("data") is None:
                self.unmapped += 1
                continue
            series = self.readings[truck][s["diagnostic"]["id"]]
            series.append((utc_to_local(s["dateTime"], self.utc_offset), float(s["data"])))
        for w in records.get("WorkOrder", []) or []:
            if w.get("vehicleName") and w.get("openedLocal"):
                self.work_orders[w["vehicleName"]].append((parse_local(w["openedLocal"]), w))
        self._sort()

    def _sort(self):
        for diags in self.readings.values():
            for series in diags.values():
                series.sort(key=lambda x: x[0])
        for wos in self.work_orders.values():
            wos.sort(key=lambda x: x[0])

    # --- queries --------------------------------------------------------------
    def last_reading(self, truck, diag, before):
        """Latest (time, value) for a diagnostic strictly before `before`, or None."""
        series = self.readings.get(truck, {}).get(diag, [])
        i = bisect.bisect_left(series, (before,)) - 1
        return series[i] if i >= 0 else None

    def last_work_order(self, truck, types, before):
        """Latest (time, row) of the given work-order types opened before `before`, or None."""
        hits = [(t, w) for t, w in self.work_orders.get(truck, []) if t < before and w.get("type") in types]
        return hits[-1] if hits else None

    def pto_since_hyd_service(self, truck, at):
        """PTO hours run since the last hydraulic service/repair, as of `at`.

        Returns (hours or None, details dict). Uses the mechanic's meter reading when present,
        otherwise the telematics PTO reading just before the work order.
        """
        last = self.last_work_order(truck, WO_HYD_RESET, at)
        now = self.last_reading(truck, DIAG_PTO, at)
        if last is None or now is None:
            return None, {"reason": "no hydraulic service on record" if last is None else "no PTO reading"}
        svc_time, wo = last
        base = (wo.get("meterReadings") or {}).get("ptoHours")
        source = "work order"
        if base is None:
            ref = self.last_reading(truck, DIAG_PTO, svc_time + timedelta(hours=12))
            base, source = (ref[1] if ref else None), "telematics at service"
        if base is None:
            return None, {"reason": "no PTO baseline at service"}
        return round(now[1] - base, 1), {"service": wo.get("type"), "service_at": svc_time.strftime(LOCAL_FMT),
                                         "baseline_source": source}

    def battery_replaced_between(self, truck, start, end):
        """True if a BATTERY_REPLACED work order was opened in [start, end)."""
        return any(start <= t < end and w.get("type") == WO_BATTERY for t, w in self.work_orders.get(truck, []))


# =============================================================================
# Loading from data/raw
# =============================================================================
RAW_ENTITIES = ("Vehicle", "DeviceAssignment", "StatusData", "WorkOrder", "FaultData", "Callout", "DispatchAssignment")


def load_raw(settings, entities=RAW_ENTITIES):
    """Read committed API snapshots from data/raw/ into {entity: rows}."""
    raw = {}
    for e in entities:
        path = Path(settings["raw_path"]) / f"{e}.json"
        try:
            raw[e] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            log.warning("%s missing; run `python -m stormtwin load`", path)
            raw[e] = []
    return raw


def load_history(settings, raw=None):
    raw = raw if raw is not None else load_raw(settings)
    hist = FleetHistory(raw, settings["model"]["utc_offset_hours"])
    if hist.unmapped:
        log.warning("%d telematics rows could not be mapped to a truck", hist.unmapped)
    return hist
