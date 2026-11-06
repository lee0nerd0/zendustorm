"""Command-line entry point: `python -m stormtwin <command> ...`

Commands
--------
    load    Download the fleet API into data/raw/ (needs the FLEET_API_KEY env var).
    (replay and whatif are added in later steps.)
"""

# =============================================================================
# Imports
# =============================================================================
import argparse
import logging
import sys

from .config import ConfigError, load_settings
from .load import LoadError, run_load


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
    return parser


# =============================================================================
# Command handlers (each returns a process exit code)
# =============================================================================
def cmd_load(args, settings):
    return 0 if run_load(settings, only=args.only) else 1


COMMANDS = {"load": cmd_load}


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
    except (ConfigError, LoadError) as exc:
        logging.getLogger("stormtwin").error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
