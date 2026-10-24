from __future__ import annotations

import gzip
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from campusrun.curlparse import parse_capture
from campusrun.errors import ProviderError
from campusrun.models import CapturedRequest, FieldMapping, HttpConnection
from campusrun.providers import HttpProvider
from campusrun.providers.autodetect import detect

RECORDS = {
    "code": 0,
    "data": {
        "list": [
            {"runDate": "2026-10-20 19:30:00", "distance": 3200, "duration": 1200, "valid": 1},
            {"runDate": "2026-10-22 20:00:00", "distance": 2000, "duration": 760, "valid": 1},
        ]
    },
}

AGGREGATE = {"code": 200, "data": {"totalDistance": 9600, "totalRuns": 3}}
AUTH_ERROR = {"code": 401, "msg": "登录已过期"}


class _Server:
    def __init__(self, payload: dict[str, Any], status: int = 200, compressed: bool = False):
        self.payload = payload
        self.status = status
        self.compressed = compressed
        self.last_headers: dict[str, str] = {}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                owner.last_headers = {k: v for k, v in self.headers.items()}
                body = json.dumps(owner.payload, ensure_ascii=False).encode("utf-8")
                if owner.compressed:
                    body = gzip.compress(body)
                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                if owner.compressed:
                    self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # noqa: D401
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address
        return f"http://{host}:{port}/api/run?page=1"

    def __enter__(self) -> "_Server":
        self.thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def make_connection(url: str, mapping: FieldMapping) -> HttpConnection:
    request = parse_capture(
        f"curl '{url}' -H 'Authorization: Bearer test-token' -H 'Accept: application/json'"
    )
    return HttpConnection(request=request, mapping=mapping)


class HttpProviderTests(unittest.TestCase):
    def test_records_fetch_and_headers(self):
        with _Server(RECORDS) as server:
            mapping = detect(RECORDS).mapping
            provider = HttpProvider(make_connection(server.url, mapping))
            summary = provider.fetch()
            self.assertEqual(summary.completed_runs, 2)
            self.assertAlmostEqual(summary.completed_km, 5.2)
            self.assertEqual(server.last_headers.get("Authorization"), "Bearer test-token")
            self.assertEqual(server.last_headers.get("Accept-Encoding"), "identity")

    def test_aggregate_fetch(self):
        with _Server(AGGREGATE) as server:
            mapping = detect(AGGREGATE).mapping
            provider = HttpProvider(make_connection(server.url, mapping))
            summary = provider.fetch()
            self.assertEqual(summary.completed_runs, 3)
            self.assertAlmostEqual(summary.completed_km, 9.6)

    def test_gzip_response(self):
        with _Server(RECORDS, compressed=True) as server:
            provider = HttpProvider(make_connection(server.url, detect(RECORDS).mapping))
            summary = provider.fetch()
            self.assertEqual(summary.completed_runs, 2)

    def test_http_401(self):
        with _Server(AUTH_ERROR, status=401) as server:
            provider = HttpProvider(make_connection(server.url, detect(RECORDS).mapping))
            with self.assertRaises(ProviderError) as ctx:
                provider.fetch()
            self.assertIn("登录状态", str(ctx.exception))

    def test_json_auth_error(self):
        with _Server({"code": 403, "msg": "未登录"}) as server:
            provider = HttpProvider(make_connection(server.url, detect(RECORDS).mapping))
            with self.assertRaises(ProviderError) as ctx:
                provider.fetch()
            self.assertIn("未登录", str(ctx.exception))

    def test_connection_requires_url(self):
        with self.assertRaises(ProviderError):
            HttpProvider(
                HttpConnection(
                    request=CapturedRequest(method="GET", url=""),
                    mapping=FieldMapping(),
                )
            )


if __name__ == "__main__":
    unittest.main()
