"""Offline tests for stormtwin.load against a local mock of the fleet API (stdlib only).

Run:  python -m unittest discover -s tests -v
"""

# =============================================================================
# Imports
# =============================================================================
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from stormtwin import load as loader

# =============================================================================
# Mock API
# =============================================================================
GOOD_KEY = "test-key"
VEHICLES = [{"id": f"b{i}", "name": f"T-{100 + i}"} for i in range(1, 6)]  # 5 rows -> 3 pages at size 2


class MockApi(BaseHTTPRequestHandler):
    """Serves /api/v1/<Entity> with cursor pagination, a one-off 503, and a looping-cursor entity."""

    fail_once = {"Flaky"}  # entities that return 503 on their first call

    def do_GET(self):  # noqa: N802 (http.server naming)
        parsed = urllib.parse.urlsplit(self.path)
        entity = parsed.path.rsplit("/", 1)[-1]
        qs = dict(urllib.parse.parse_qsl(parsed.query))

        if self.headers.get("X-Api-Key") != GOOD_KEY:
            return self._send(401, {"error": "bad key"})
        if entity == "v1":
            return self._send(200, {"entities": ["Vehicle", "Flaky", "Looping"], "meta": {}, "docs": "x"})
        if entity in MockApi.fail_once:
            MockApi.fail_once.discard(entity)
            return self._send(503, {"error": "try later"})
        if entity == "Looping":
            return self._send(200, {"data": [{"id": "x"}], "next": "same"})
        if entity in ("Vehicle", "Flaky"):
            size = int(qs.get("resultsLimit", 200))
            offset = int(qs.get("cursor", 0))
            chunk = VEHICLES[offset:offset + size]
            nxt = str(offset + size) if offset + size < len(VEHICLES) else None
            return self._send(200, {"data": chunk, "count": len(chunk), "next": nxt})
        return self._send(404, {"error": "unknown entity"})

    def _send(self, code, body):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # keep test output quiet
        pass


# =============================================================================
# Tests
# =============================================================================
class LoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockApi)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/api/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = {
            "api_base_url": self.base, "api_key_env": "STORMTWIN_TEST_KEY", "api_key_header": "X-Api-Key",
            "page_size": 2, "http_timeout_s": 5, "http_max_retries": 2, "http_backoff_base_s": 0,
            "max_pages_per_entity": 10, "entities": {"Vehicle": 5, "Flaky": 4},
            "raw_path": Path(self.tmp.name) / "raw",
        }
        os.environ["STORMTWIN_TEST_KEY"] = GOOD_KEY

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("STORMTWIN_TEST_KEY", None)

    def test_paginates_and_writes_files(self):
        self.assertTrue(loader.run_load(self.settings, only=["Vehicle"]))
        rows = json.loads((self.settings["raw_path"] / "Vehicle.json").read_text())
        self.assertEqual(rows, VEHICLES)
        manifest = json.loads((self.settings["raw_path"] / "_manifest.json").read_text())
        self.assertEqual(manifest["entities"]["Vehicle"]["rows"], 5)
        self.assertEqual(manifest["entities"]["Vehicle"]["warnings"], [])

    def test_retries_transient_503_and_flags_count_mismatch(self):
        self.assertTrue(loader.run_load(self.settings, only=["Flaky"]))
        entry = json.loads((self.settings["raw_path"] / "_manifest.json").read_text())["entities"]["Flaky"]
        self.assertEqual(entry["status"], "ok")
        self.assertIn("row count 5 != documented 4", entry["warnings"])

    def test_bad_key_aborts(self):
        os.environ["STORMTWIN_TEST_KEY"] = "wrong"
        with self.assertRaises(loader.AuthError):
            loader.run_load(self.settings, only=["Vehicle"])

    def test_missing_key_is_clear_error(self):
        del os.environ["STORMTWIN_TEST_KEY"]
        with self.assertRaisesRegex(loader.LoadError, "STORMTWIN_TEST_KEY"):
            loader.run_load(self.settings)

    def test_unknown_and_looping_entities_fail_without_stopping_others(self):
        ok = loader.run_load(self.settings, only=["Nope", "Looping", "Vehicle"])
        self.assertFalse(ok)
        entries = json.loads((self.settings["raw_path"] / "_manifest.json").read_text())["entities"]
        self.assertEqual(entries["Nope"]["status"], "failed")
        self.assertIn("repeated cursor", entries["Looping"]["error"])
        self.assertEqual(entries["Vehicle"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
