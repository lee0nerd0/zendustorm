"""Command-line entry point: `python -m stormtwin <command> ...`

Commands
--------
    load    Download the fleet API into data/raw/ (needs the FLEET_API_KEY env var).
    weather Download Environment Canada weather into data/weather/ (no key needed).
    evidence Re-derive the hidden rules from history and backtest them (offline).
    replay  Predict ok / no_start / hydraulic per truck for a replay input file (offline).
    whatif  Tonight's action list under a weather scenario / forecast file / repairs.
"""

# =============================================================================
# Imports
# =============================================================================
import argparse
import logging
import sys

from .config import ConfigError, load_settings
from .load import LoadError, run_load
from .replay import ReplayError, run_replay
from .weather import run_weather
from .evidence import run_evidence
from .whatif import WhatIfError, run_whatif


# =============================================================================
# Argument parsing
# =============================================================================
def build_parser():
    parser = argparse.ArgumentParser(prog="stormtwin", description="Storm Twin what-if engine")
    parser.add_argument("--config", help="Path to settings JSON (default: config/settings.json)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p_load = sub.add_parser("load", help="Download the fleet API into data/raw/")
    p_load.add_argument("--only", nargs="+", metavar="ENTITY", help="Fetch only these entities, e.g. --only Vehicle WorkOrder")

    sub.add_parser("weather", help="Download historical weather into data/weather/")

    sub.add_parser("evidence", help="Backtest the hidden rules on history (offline)")

    p_replay = sub.add_parser("replay", help="Predict per-truck outcome for a replay input (offline)")
    p_replay.add_argument("--input", required=True, help="Replay input JSON (maintenance_input.json)")
    p_replay.add_argument("--output", required=True, help="Where to write the prediction JSON")

    p_wi = sub.add_parser("whatif", help="Tonight's maintenance action list under a scenario")
    p_wi.add_argument("--callout", help="HH:MM on the planned night, or full YYYY-MM-DDTHH:MM:SS")
    p_wi.add_argument("--low", type=float, help="Night low, °C")
    p_wi.add_argument("--snow", type=float, help="Snowfall, cm")
    p_wi.add_argument("--forecast", help="JSON with callout_local/night_low_c/snow_cm and/or a weather block")
    p_wi.add_argument("--fix", nargs="+", metavar="TRUCK[:battery|hydraulic|all]", help="Simulate repairs")
    p_wi.add_argument("--json", dest="json_out", help="Also write the full report as JSON")
    return parser


# =============================================================================
# Command handlers (each returns a process exit code)
# =============================================================================
def cmd_load(args, settings):
    return 0 if run_load(settings, only=args.only) else 1


def cmd_weather(args, settings):
    run_weather(settings)
    return 0


def cmd_evidence(args, settings):
    run_evidence(settings)
    return 0


def cmd_whatif(args, settings):
    run_whatif(settings, args.callout, args.low, args.snow, args.forecast, args.fix, args.json_out)
    return 0


def cmd_replay(args, settings):
    run_replay(args.input, args.output, settings)
    return 0


COMMANDS = {"load": cmd_load, "weather": cmd_weather, "evidence": cmd_evidence, "replay": cmd_replay, "whatif": cmd_whatif}


# =============================================================================
# Main
# =============================================================================
def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        settings = load_settings(args.config)
        return COMMANDS[args.command](args, settings)
    except (ConfigError, LoadError, ReplayError, WhatIfError) as exc:
        logging.getLogger("stormtwin").error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
