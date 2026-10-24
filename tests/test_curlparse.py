from __future__ import annotations

import unittest

from campusrun.curlparse import describe_capture, parse_capture
from campusrun.errors import CaptureParseError


class CurlParseTests(unittest.TestCase):
    def test_linux_style(self):
        text = r"""curl 'https://example.edu/api/run/list?page=1' \
  -H 'accept: application/json' \
  -H 'authorization: Bearer abc.def.ghi' \
  -H 'content-type: application/json' \
  --data-raw '{"page":1,"size":20}' \
  --compressed"""
        request = parse_capture(text)
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url, "https://example.edu/api/run/list?page=1")
        self.assertEqual(request.headers["authorization"], "Bearer abc.def.ghi")
        self.assertEqual(request.body, '{"page":1,"size":20}')
        self.assertIn("example.edu", describe_capture(request))

    def test_windows_continuation_and_quotes(self):
        text = (
            'curl "https://example.edu/api/run/list" ^\n'
            '  -H "accept: application/json" ^\n'
            '  -H "cookie: session=xyz" ^\n'
            '  --data-raw "{\\"page\\":1}"'
        )
        request = parse_capture(text)
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.headers["cookie"], "session=xyz")
        self.assertEqual(request.body, '{"page":1}')

    def test_attached_header(self):
        request = parse_capture("curl https://x.test/api -H'X-Token: t1'")
        self.assertEqual(request.headers["X-Token"], "t1")

    def test_cookie_option(self):
        request = parse_capture("curl 'https://x.test/a' -b 'a=1; b=2'")
        self.assertEqual(request.headers["Cookie"], "a=1; b=2")

    def test_get_with_data_moves_to_query(self):
        request = parse_capture("curl 'https://x.test/api?a=1' -G --data-urlencode 'b=2' --data 'c=3'")
        self.assertEqual(request.method, "GET")
        self.assertIsNone(request.body)
        self.assertIn("a=1", request.url)
        self.assertIn("b=2", request.url)
        self.assertIn("c=3", request.url)

    def test_explicit_get_with_body(self):
        request = parse_capture("curl 'https://x.test/api' -X GET -d 'page=2'")
        self.assertEqual(request.method, "GET")
        self.assertIsNone(request.body)
        self.assertEqual(request.url, "https://x.test/api?page=2")

    def test_raw_http_request(self):
        text = (
            "GET /api/run?x=1 HTTP/1.1\n"
            "Host: example.edu\n"
            "Cookie: a=b\n"
            "Accept: application/json\n\n"
        )
        request = parse_capture(text)
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.url, "https://example.edu/api/run?x=1")
        self.assertEqual(request.headers["Cookie"], "a=b")
        self.assertNotIn("Host", request.headers)

    def test_plain_url(self):
        request = parse_capture("https://example.edu/api/stats")
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.url, "https://example.edu/api/stats")

    def test_missing_url(self):
        with self.assertRaises(CaptureParseError):
            parse_capture("curl -X POST -H 'a: b'")

    def test_garbage(self):
        with self.assertRaises(CaptureParseError):
            parse_capture("这不是 cURL")

    def test_secret_headers_are_masked(self):
        request = parse_capture(
            "curl 'https://x.test/a' -H 'Authorization: Bearer 1234567890abcdef' -H 'Accept: application/json'"
        )
        redacted = request.redacted_headers()
        self.assertNotIn("1234567890abcdef", redacted["Authorization"])
        self.assertEqual(redacted["Accept"], "application/json")


if __name__ == "__main__":
    unittest.main()
