"""What-if: tonight's maintenance action list under a weather scenario, forecast file, and/or repairs."""

import json
import logging
from pathlib import Path

from .history import load_history, load_raw, parse_local
from .night import night_conditions, weather_from_block
from .rules import classify, truck_features

log = logging.getLogger("stormtwin.whatif")

FIX_KINDS = ("battery", "hydraulic")


class WhatIfError(Exception):
    pass


def build_scenario(settings, callout=None, low=None, snow=None, forecast=None):
    sc = dict(settings["scenario"])
    if forecast:
        try:
            fc = json.loads(Path(forecast).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise WhatIfError(f"Cannot read forecast file {forecast}: {exc}") from exc
        sc.update({k: fc[k] for k in ("callout_local", "night_low_c", "snow_cm", "plan_date") if k in fc})
        if "weather" in fc:
            cond = night_conditions(fc.get("callout_local", sc["callout_local"]), weather_from_block(fc["weather"]),
                                    settings["night"])
            sc.update({k: v for k, v in cond.items() if v is not None and k in ("night_low_c", "snow_cm")})
    if callout:
        sc["callout_local"] = callout if "T" in callout else f"{sc['callout_local'][:10]}T{callout}:00"[:19]
    if low is not None:
        sc["night_low_c"] = low
    if snow is not None:
        sc["snow_cm"] = snow
    return sc


def parse_fixes(items):
    fixes = {}
    for item in items or []:
        truck, _, kind = item.partition(":")
        kinds = FIX_KINDS if kind in ("", "all") else (kind,)
        if any(k not in FIX_KINDS for k in kinds):
            raise WhatIfError(f"--fix {item}: kind must be one of {FIX_KINDS} or all")
        fixes.setdefault(truck, set()).update(kinds)
    return fixes


def apply_fixes(f, kinds):
    f = dict(f)
    if "battery" in kinds:
        f["battery_replaced_since_reading"] = True
    if "hydraulic" in kinds:
        f["pto_since_service_h"] = 0.0
    return f


def plan_context(raw, plan_date):
    routes = {r["id"]: r for r in raw["Route"]}
    tandem = {v["name"]: "tandem" in v.get("bodyType", "").lower() for v in raw["Vehicle"]}
    plan = {p["vehicleName"]: p for p in raw["DispatchPlan"] if p.get("planDate") == plan_date}
    return routes, tandem, plan


def watch_notes(f, label, rules, margins):
    if label != "ok":
        return []
    ns, hy = rules["no_start"], rules["hydraulic"]
    notes = []
    v, low = f["voltage_v"], f["night_low_c"]
    if v is not None and not f["battery_replaced_since_reading"]:
        if v < ns["max_voltage_v"]:
            notes.append(f"weak battery {v:.2f} V: fails if night low <= {ns['night_low_max_c']} °C")
        elif v < ns["max_voltage_v"] + margins["voltage_v"]:
            notes.append(f"battery {v:.2f} V within {margins['voltage_v']} V of {ns['max_voltage_v']} V")
    p = f["pto_since_service_h"]
    if p is not None:
        if p >= hy["min_pto_hours_since_service"]:
            notes.append(f"{p:.1f} PTO h since service: fails if snow >= {hy['min_snow_cm']} cm")
        elif p >= hy["min_pto_hours_since_service"] - margins["pto_h"]:
            notes.append(f"{p:.1f} PTO h since service, {hy['min_pto_hours_since_service'] - p:.1f} h below limit")
    return notes


def run_whatif(settings, callout=None, low=None, snow=None, forecast=None, fixes=None, json_out=None):
    sc = build_scenario(settings, callout, low, snow, forecast)
    fixes = parse_fixes(fixes)
    raw = load_raw(settings, ("Vehicle", "DeviceAssignment", "StatusData", "WorkOrder", "Route", "DispatchPlan"))
    hist = load_history(settings, raw)
    routes, tandem, plan = plan_context(raw, sc["plan_date"])
    callout_dt = parse_local(sc["callout_local"])
    cond = {"night_low_c": sc["night_low_c"], "snow_cm": sc["snow_cm"]}
    rules, margins = settings["rules"], settings["whatif"]["watch_margins"]

    trucks = []
    for truck in hist.trucks:
        f = apply_fixes(truck_features(hist, truck, callout_dt, cond), fixes.get(truck, ()))
        label, reasons = classify(f, rules)
        planned = [routes[r] for r in plan.get(truck, {}).get("sequence", []) if r in routes]
        trucks.append({
            "truck": truck, "label": label, "reasons": reasons if label != "ok" else [],
            "watch": watch_notes(f, label, rules, margins), "fixed": sorted(fixes.get(truck, ())),
            "tandem": tandem.get(truck, False),
            "planned_routes": [{"route": r["id"], "class": r["roadClass"], "km": r["lengthKm"],
                                "tandem_required": r["requiresTandem"]} for r in planned],
            "voltage_v": f["voltage_v"], "pto_since_service_h": f["pto_since_service_h"],
        })

    down = [t for t in trucks if t["label"] != "ok"]
    down.sort(key=lambda t: (min([r["class"] for r in t["planned_routes"]] or [9]),
                             -sum(r["km"] for r in t["planned_routes"]), t["truck"]))
    report = {
        "scenario": sc, "fixes": {k: sorted(v) for k, v in fixes.items()},
        "available": len(trucks) - len(down), "fleet": len(trucks),
        "fix_first": [t["truck"] for t in down],
        "routes_at_risk": sorted(({**r, "truck": t["truck"], "failure": t["label"]}
                                  for t in down for r in t["planned_routes"]), key=lambda r: (r["class"], r["route"])),
        "watch": [{"truck": t["truck"], "notes": t["watch"]} for t in trucks if t["watch"]],
        "trucks": trucks,
    }
    print(render(report, rules))
    if json_out:
        Path(json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(json_out).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        log.info("Wrote %s", json_out)
    return report


def render(r, rules):
    sc = r["scenario"]
    by = {t["truck"]: t for t in r["trucks"]}
    standard = {int(k): v for k, v in rules.get("standard_hours_by_class", {}).items()}
    lines = [
        f"WHAT-IF  callout {sc['callout_local']}  night low {sc['night_low_c']} °C  snow {sc['snow_cm']} cm"
        + (f"  fixes {r['fixes']}" if r["fixes"] else ""),
        f"Trucks ready: {r['available']}/{r['fleet']}",
        "",
        "FIX FIRST (ordered by most urgent planned road class, then km):",
    ]
    for i, name in enumerate(r["fix_first"], 1):
        t = by[name]
        rts = ", ".join(f"{p['route']} (class {p['class']}{', tandem' if p['tandem_required'] else ''})"
                        for p in t["planned_routes"]) or "no planned route"
        lines.append(f"  {i}. {name:6} {t['label'].upper():9} {t['reasons'][0]}")
        lines.append(f"     planned: {rts}")
    if not r["fix_first"]:
        lines.append("  none")
    lines += ["", "ROUTES THAT NEED ANOTHER TRUCK:"]
    for p in r["routes_at_risk"]:
        hrs = standard.get(p["class"])
        lines.append(f"  {p['route']}  class {p['class']}{f' (clear within {hrs} h)' if hrs else ''}"
                     f"{'  tandem required' if p['tandem_required'] else ''}  {p['km']} km  was {p['truck']} ({p['failure']})")
    if not r["routes_at_risk"]:
        lines.append("  none")
    lines += ["", "WATCH (ok tonight, close to a limit or would fail under other weather):"]
    lines += [f"  {w['truck']:6} " + "; ".join(w["notes"]) for w in r["watch"]] or ["  none"]
    return "\n".join(lines)
