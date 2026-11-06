"""Command-line entry point: `python -m stormtwin <command> ...`

Commands
--------
    load    Download the fleet API into data/raw/ (needs the FLEET_API_KEY env var).
    weather Download Environment Canada weather into data/weather/ (no key needed).
    replay  Predict ok / no_start / hydraulic per truck for a replay input file (offline).
    (whatif is added in a later step.)
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

    p_replay = sub.add_parser("replay", help="Predict per-truck outcome for a replay input (offline)")
    p_replay.add_argument("--input", required=True, help="Replay input JSON (maintenance_input.json)")
    p_replay.add_argument("--output", required=True, help="Where to write the prediction JSON")
    return parser


# =============================================================================
# Command handlers (each returns a process exit code)
# =============================================================================
def cmd_load(args, settings):
    return 0 if run_load(settings, only=args.only) else 1


def cmd_weather(args, settings):
    run_weather(settings)
    return 0


def cmd_replay(args, settings):
    run_replay(args.input, args.output, settings)
    return 0


COMMANDS = {"load": cmd_load, "weather": cmd_weather, "replay": cmd_replay}


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
    except (ConfigError, LoadError, ReplayError) as exc:
        logging.getLogger("stormtwin").error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
