"""Settings loader.

All tunables (API URL, paths, thresholds) live in config/settings.json so nothing is hard-coded.
Secrets never live there: the API key is read from the environment variable named in `api_key_env`.
"""

# =============================================================================
# Imports
# =============================================================================
import json
from pathlib import Path

# =============================================================================
# Constants
# =============================================================================
# Repo root = parent of the stormtwin/ package. Relative paths in settings resolve against it,
# so commands work no matter which directory they are launched from.
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = REPO_ROOT / "config" / "settings.json"

# Keys that must be present; a missing one is a config bug we want to catch at startup.
REQUIRED_KEYS = (
    "api_base_url",
    "api_key_env",
    "api_key_header",
    "data_dir",
    "raw_subdir",
    "page_size",
    "http_timeout_s",
    "http_max_retries",
    "http_backoff_base_s",
    "max_pages_per_entity",
    "entities",
)


# =============================================================================
# Public API
# =============================================================================
class ConfigError(Exception):
    """Raised when the settings file is missing, unreadable or incomplete."""


def load_settings(path=None):
    """Read settings JSON, check required keys, and add resolved absolute paths.

    Returns a plain dict. Adds:
      - "data_path": absolute Path of data_dir
      - "raw_path":  absolute Path of data_dir/raw_subdir
    """
    path = Path(path) if path else DEFAULT_SETTINGS_PATH
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Settings file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Settings file is not valid JSON: {path}: {exc}") from exc

    missing = [k for k in REQUIRED_KEYS if k not in settings]
    if missing:
        raise ConfigError(f"Settings file {path} is missing keys: {', '.join(missing)}")

    settings["data_path"] = _resolve(settings["data_dir"])
    settings["raw_path"] = settings["data_path"] / settings["raw_subdir"]
    return settings


# =============================================================================
# Helpers
# =============================================================================
def _resolve(p):
    """Resolve a path from settings: absolute stays absolute, relative is anchored at the repo root."""
    p = Path(p)
    return p if p.is_absolute() else (REPO_ROOT / p)
