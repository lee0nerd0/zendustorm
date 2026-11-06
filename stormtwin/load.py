"""Load step: download every fleet API entity into data/raw/ so the replay can run offline.

Pipeline
--------
    for each entity in settings["entities"]:
        rows = []
        cursor = None
        loop:
            page = GET /<Entity>?resultsLimit=N[&cursor=...]   (retries + backoff on transient errors)
            rows += page["data"]
            stop when page["next"] is null
        validate rows (list of dicts, count vs the count the docs advertise)
        write data/raw/<Entity>.json atomically
    write data/raw/_manifest.json  (counts, sha256, status, fetch time)

Design notes
------------
* Standard library only (urllib), so the clean replay container needs no installs.
* We pull every row with no date filter. The largest entity is ~8k rows (about 9 pages), so this is cheap
  and avoids text-compare date filters across UTC and local-time fields.
* One entity failing does not stop the others. The run exits non-zero and the manifest records the failure.
* Files are written via temp file + rename, so an interrupted run never leaves a half-written JSON.
* The API key is never logged or written to disk.
"""

# =============================================================================
# Imports
# =============================================================================
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger("stormtwin.load")

# =============================================================================
# Constants
# =============================================================================
# HTTP statuses worth retrying (rate limit and server-side hiccups). 400/401/404 are our fault: fail fast.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# Human-readable hints for the non-retryable statuses the API docs list.
FATAL_STATUS_HINTS = {
    400: "bad parameter (check page_size / filters)",
    401: "bad or missing API key (check the FLEET_API_KEY env var)",
    404: "unknown entity name (check settings['entities'])",
}

MANIFEST_NAME = "_manifest.json"


# =============================================================================
# Errors
# =============================================================================
class LoadError(Exception):
    """A non-recoverable problem fetching one entity."""


class AuthError(LoadError):
    """401: every later request will fail too, so the whole run aborts."""


# =============================================================================
# HTTP layer: one GET with timeout, retries and exponential backoff
# =============================================================================
def build_url(base_url, entity, params):
    """Join base URL, entity path and query string. `params` with None values are dropped."""
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    path = f"{base_url.rstrip('/')}/{entity}" if entity else base_url.rstrip("/")
    return f"{path}?{query}" if query else path


def http_get_json(url, api_key, settings):
    """GET a URL and parse JSON. Retries transient failures; raises LoadError/AuthError otherwise."""
    headers = {settings["api_key_header"]: api_key, "Accept": "application/json"}
    max_retries = int(settings["http_max_retries"])
    backoff = float(settings["http_backoff_base_s"])
    timeout = float(settings["http_timeout_s"])

    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))

        except urllib.error.HTTPError as exc:
            # --- Non-retryable: tell the user what to fix ---
            if exc.code not in RETRYABLE_STATUSES:
                hint = FATAL_STATUS_HINTS.get(exc.code, "unexpected status")
                err_cls = AuthError if exc.code == 401 else LoadError
                raise err_cls(f"HTTP {exc.code} for {_redact(url)}: {hint}") from exc
            # --- Retryable: honour Retry-After if the server sent one ---
            wait = _retry_after_seconds(exc) or backoff * (2 ** attempt)
            reason = f"HTTP {exc.code}"

        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            # Network-level failure (DNS, reset, timeout): retry with backoff.
            wait = backoff * (2 ** attempt)
            reason = f"network error: {getattr(exc, 'reason', exc)}"

        except json.JSONDecodeError as exc:
            # A 200 with non-JSON body is a server problem; one retry is reasonable, more is not useful.
            wait = backoff * (2 ** attempt)
            reason = f"invalid JSON: {exc}"

        if attempt == max_retries:
            raise LoadError(f"Giving up on {_redact(url)} after {max_retries + 1} attempts ({reason})")
        log.warning("Retry %d/%d in %.0fs for %s (%s)", attempt + 1, max_retries, wait, _redact(url), reason)
        time.sleep(wait)

    raise LoadError("unreachable")  # loop always returns or raises; kept for linters


def _retry_after_seconds(exc):
    """Parse a numeric Retry-After header; return None if absent or not a number."""
    value = exc.headers.get("Retry-After") if exc.headers else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _redact(url):
    """URLs never contain the key (it goes in a header), but strip the cursor to keep logs short."""
    parsed = urllib.parse.urlsplit(url)
    return parsed.path


# =============================================================================
# Pagination: follow `next` cursors until the API says we have everything
# =============================================================================
def fetch_entity(entity, api_key, settings):
    """Return every row of one entity as a list of dicts."""
    rows = []
    cursor = None
    seen_cursors = set()  # guards against an API bug that loops on the same cursor

    for page_no in range(1, int(settings["max_pages_per_entity"]) + 1):
        params = {"resultsLimit": settings["page_size"], "cursor": cursor}
        page = http_get_json(build_url(settings["api_base_url"], entity, params), api_key, settings)

        data = _page_rows(page, entity)
        rows.extend(data)
        log.debug("%s page %d: %d rows (total %d)", entity, page_no, len(data), len(rows))

        cursor = page.get("next")
        if not cursor:
            return rows
        if cursor in seen_cursors:
            raise LoadError(f"{entity}: API returned a repeated cursor on page {page_no}; stopping to avoid a loop")
        seen_cursors.add(cursor)

    raise LoadError(f"{entity}: exceeded max_pages_per_entity={settings['max_pages_per_entity']}")


def _page_rows(page, entity):
    """Pull the `data` list out of one page response, checking its shape."""
    if not isinstance(page, dict) or not isinstance(page.get("data"), list):
        raise LoadError(f"{entity}: unexpected response shape (expected an object with a 'data' list)")
    return page["data"]


# =============================================================================
# Validation: cheap sanity checks, reported as warnings (the data is messy on purpose)
# =============================================================================
def validate_rows(entity, rows, expected_count):
    """Return a list of warning strings. Never raises: messy data is evidence, not an error."""
    warnings = []
    if expected_count is not None and len(rows) != expected_count:
        warnings.append(f"row count {len(rows)} != documented {expected_count}")
    non_dicts = sum(1 for r in rows if not isinstance(r, dict))
    if non_dicts:
        warnings.append(f"{non_dicts} rows are not JSON objects")
    ids = [r.get("id") for r in rows if isinstance(r, dict) and "id" in r]
    if ids and len(ids) != len(set(ids)):
        warnings.append(f"{len(ids) - len(set(ids))} duplicate ids")
    return warnings


def list_remote_entities(api_key, settings):
    """Ask the API which entities exist (GET base URL). Returns a set of names, or None if unavailable."""
    try:
        listing = http_get_json(build_url(settings["api_base_url"], "", {}), api_key, settings)
    except AuthError:
        raise
    except LoadError as exc:
        log.warning("Could not list entities from the API root: %s", exc)
        return None
    # The docs don't specify the listing shape, so accept a list, {"data": [...]}, or a dict of names.
    items = listing.get("data", listing) if isinstance(listing, dict) else listing
    if isinstance(items, dict):
        return set(items.keys())
    if isinstance(items, list):
        return {i if isinstance(i, str) else i.get("name") for i in items if i} - {None}
    return None


# =============================================================================
# Persistence: atomic JSON writes + a manifest describing the snapshot
# =============================================================================
def write_json_atomic(path, obj):
    """Write JSON to a temp file then rename, so readers never see a partial file. Returns sha256 hex."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)
    return hashlib.sha256(payload).hexdigest()


# =============================================================================
# Orchestration
# =============================================================================
def run_load(settings, only=None):
    """Download the configured entities (or the `only` subset) into data/raw/.

    Returns True if every requested entity loaded, False otherwise.
    """
    # --- 1. Resolve inputs ---------------------------------------------------
    api_key = os.environ.get(settings["api_key_env"], "").strip()
    if not api_key:
        raise LoadError(f"Environment variable {settings['api_key_env']} is not set. Export your API key first.")

    expected = settings["entities"]
    entities = list(only) if only else list(expected)
    unknown = [e for e in entities if e not in expected]
    if unknown:
        log.warning("Not in settings['entities'] (no expected count): %s", ", ".join(unknown))

    raw_path = settings["raw_path"]
    log.info("Loading %d entities from %s into %s", len(entities), settings["api_base_url"], raw_path)

    # --- 2. Compare the remote entity list with our config (informational) ---
    remote = list_remote_entities(api_key, settings)
    if remote:
        extra = sorted(remote - set(expected))
        if extra:
            log.warning("API offers entities not in settings: %s", ", ".join(extra))

    # --- 3. Fetch each entity independently ----------------------------------
    manifest = _read_manifest(raw_path)
    manifest["api_base_url"] = settings["api_base_url"]
    entries = manifest.setdefault("entities", {})
    all_ok = True

    for entity in entities:
        started = time.monotonic()
        try:
            rows = fetch_entity(entity, api_key, settings)
        except AuthError:
            raise  # a bad key will fail every entity; stop now with a clear message
        except LoadError as exc:
            log.error("%s: FAILED: %s", entity, exc)
            entries[entity] = {"status": "failed", "error": str(exc), "fetched_at_utc": _now_utc()}
            all_ok = False
            continue

        warnings = validate_rows(entity, rows, expected.get(entity))
        digest = write_json_atomic(raw_path / f"{entity}.json", rows)
        elapsed = time.monotonic() - started

        entries[entity] = {
            "status": "ok",
            "rows": len(rows),
            "expected_rows": expected.get(entity),
            "warnings": warnings,
            "sha256": digest,
            "fetched_at_utc": _now_utc(),
        }
        log.info("%-20s %6d rows  %5.1fs%s", entity, len(rows), elapsed,
                 ("  WARN: " + "; ".join(warnings)) if warnings else "")

    # --- 4. Write the manifest (always, so failures are recorded) ------------
    manifest["updated_at_utc"] = _now_utc()
    write_json_atomic(raw_path / MANIFEST_NAME, manifest)

    loaded = sum(1 for e in entities if entries.get(e, {}).get("status") == "ok")
    log.info("Done: %d/%d entities loaded. Manifest: %s", loaded, len(entities), raw_path / MANIFEST_NAME)
    return all_ok


def _read_manifest(raw_path):
    """Load the existing manifest so a partial re-run (--only) keeps the other entries."""
    path = raw_path / MANIFEST_NAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
