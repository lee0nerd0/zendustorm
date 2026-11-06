"""The hidden rules, as deterministic code. Thresholds live in config/settings.json ("rules").

Rule 1 - no_start  : resting battery voltage (last evening reading before the callout) < max_voltage_v
                     AND night low <= night_low_max_c.
                     A battery replaced after that reading voids it (the new battery is assumed good).
Rule 2 - hydraulic : PTO hours since the last hydraulic service/repair >= min_pto_hours_since_service
                     AND snowfall on the callout date >= min_snow_cm.
Priority           : no_start wins (a truck that does not start cannot lose its hydraulics on a route).
Unknown inputs     : never flag. A missing number is reported, not guessed (false alarms cost points).
"""

# =============================================================================
# Imports
# =============================================================================
from .history import DIAG_VOLTAGE

# =============================================================================
# Single-truck evaluation
# =============================================================================
def truck_features(hist, truck, callout, cond):
    """Collect the numbers both rules need for one truck on one night."""
    volt = hist.last_reading(truck, DIAG_VOLTAGE, callout)
    battery_new = bool(volt) and hist.battery_replaced_between(truck, volt[0], callout)
    pto_since, pto_info = hist.pto_since_hyd_service(truck, callout)
    return {
        "voltage_v": volt[1] if volt else None,
        "voltage_at": volt[0].strftime("%Y-%m-%dT%H:%M:%S") if volt else None,
        "battery_replaced_since_reading": battery_new,
        "pto_since_service_h": pto_since,
        "pto_info": pto_info,
        "night_low_c": cond["night_low_c"],
        "snow_cm": cond["snow_cm"],
    }


def classify(f, rules):
    """Return (label, reasons[]) from one truck's features."""
    ns, hy = rules["no_start"], rules["hydraulic"]
    reasons = []

    # --- Rule 1: no_start --------------------------------------------------------
    if f["battery_replaced_since_reading"]:
        reasons.append("battery replaced after last voltage reading: treated as healthy")
    elif f["voltage_v"] is not None and f["night_low_c"] is not None:
        if f["voltage_v"] < ns["max_voltage_v"] and f["night_low_c"] <= ns["night_low_max_c"]:
            return "no_start", [f"battery {f['voltage_v']:.2f} V < {ns['max_voltage_v']} V "
                                f"and night low {f['night_low_c']:.1f} °C <= {ns['night_low_max_c']} °C"]
    else:
        reasons.append("no_start not assessed: missing voltage or night low")

    # --- Rule 2: hydraulic ------------------------------------------------------
    if f["pto_since_service_h"] is not None and f["snow_cm"] is not None:
        if f["pto_since_service_h"] >= hy["min_pto_hours_since_service"] and f["snow_cm"] >= hy["min_snow_cm"]:
            return "hydraulic", [f"{f['pto_since_service_h']:.1f} PTO h since hydraulic service >= "
                                 f"{hy['min_pto_hours_since_service']} h and {f['snow_cm']:.1f} cm snow >= {hy['min_snow_cm']} cm"]
    else:
        reasons.append("hydraulic not assessed: missing PTO-since-service or snowfall")

    return "ok", reasons


# =============================================================================
# Fleet evaluation
# =============================================================================
def assess_fleet(hist, trucks, callout, cond, rules):
    """Return {truck: {"label", "reasons", "features"}} for one night."""
    out = {}
    for truck in trucks:
        f = truck_features(hist, truck, callout, cond)
        label, reasons = classify(f, rules)
        out[truck] = {"label": label, "reasons": reasons, "features": f}
    return out
