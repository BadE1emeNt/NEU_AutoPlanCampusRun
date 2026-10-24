from __future__ import annotations

import json
import threading
import unittest
import urllib.parse
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from . import workspace_tmp
from campusrun.config import AppPaths
from campusrun.models import RunRecord, RunSummary
from campusrun.neu.cas import (
    CasGuideRequired,
    CasLoginClient,
    CasLoginError,
    FALLBACK_PUBLIC_KEY,
    _guide_url_for_browser,
    _is_guide_url,
)
from campusrun.neu.crypto import (
    aes_cbc_decrypt,
    aes_cbc_encrypt,
    aes_decrypt_base64,
    aes_encrypt_base64,
    parse_rsa_public_key,
    rsa_encrypt_base64,
)
from campusrun.neu.sports import (
    AES_IV,
    AES_KEY,
    SIGN_SALT,
    SportsClient,
    SportsFetch,
    SportsSession,
)
from campusrun.service import CampusRunService

PUB = FALLBACK_PUBLIC_KEY


class CryptoTests(unittest.TestCase):
    def test_aes_roundtrip_and_known_block(self):
        key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        plain = bytes.fromhex("00112233445566778899aabbccddeeff")
        cipher = aes_cbc_encrypt(plain, key, bytes(16))
        self.assertEqual(cipher[:16].hex(), "69c4e0d86a7b0430d8cdb78070b4c55a")
        self.assertEqual(aes_cbc_decrypt(cipher, key, bytes(16)), plain)

    def test_aes_captured_payload_shape(self):
        text = '{"total_num":"5","list":[]}'
        encrypted = aes_encrypt_base64(text, AES_KEY, AES_IV)
        self.assertEqual(aes_decrypt_base64(encrypted, AES_KEY, AES_IV), text)

    def test_rsa_encrypt(self):
        key = parse_rsa_public_key(FALLBACK_PUBLIC_KEY)
        self.assertEqual(key.n.bit_length(), 2048)
        cipher = rsa_encrypt_base64("20260001password", FALLBACK_PUBLIC_KEY)
        self.assertEqual(len(cipher), 344)
        self.assertNotIn("password", cipher)


class _SportsHandler(BaseHTTPRequestHandler):
    token_seen = ""
    signed_ok = True

    def log_message(self, *args):
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("ascii")
        form = urllib.parse.parse_qs(body)
        payload = json.loads(aes_decrypt_base64(form["data"][0], AES_KEY, AES_IV))
        _SportsHandler.token_seen = payload.get("token", "")
        sign = payload.pop("sign")
        concat = "".join(f"{key}{payload[key]}" for key in sorted(payload))
        import hashlib

        expected = hashlib.md5((concat + SIGN_SALT).encode()).hexdigest()
        _SportsHandler.signed_ok = sign == expected
        if self.path.endswith("WpLogin/UserInfo"):
            data = {"name": "测试同学", "role": 1, "uid": 123, "student_num": "20260001"}
        elif self.path.endswith("WpRun/getTermList"):
            data = [{"term_id": "4771", "term_name": "2026~2027学年上学期", "status": "1"}]
        else:
            data = {
                "total_num": "2",
                "total_distance": "6.08",
                "list": [
                    {
                        "id": "1",
                        "start_time": "1792406628",
                        "end_time": "1792408267",
                        "distance": "3.47",
                        "record_status": "1",
                    },
                    {
                        "id": "2",
                        "start_time": "1791803080",
                        "end_time": "1791805297",
                        "distance": "2.61",
                        "record_status": "1",
                    },
                ],
            }
        envelope = {
            "status": 1,
            "is_encrypt": 1,
            "data": aes_encrypt_base64(json.dumps(data, ensure_ascii=False), AES_KEY, AES_IV),
        }
        raw = json.dumps(envelope).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class _SportsServer:
    def __enter__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _SportsHandler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


class SportsClientTests(unittest.TestCase):
    def test_fetch_and_signature(self):
        session = SportsSession(
            token="test-token",
            uid="123",
            school_id="833",
            student_num="20260001",
            card_id="20260001",
        )
        with _SportsServer() as server:
            result = SportsClient(session, base_url=server.url).fetch()
        self.assertTrue(_SportsHandler.signed_ok)
        self.assertEqual(_SportsHandler.token_seen, "test-token")
        self.assertEqual(result.summary.completed_runs, 2)
        self.assertAlmostEqual(result.summary.completed_km, 6.08)
        self.assertEqual(result.term_id, "4771")
        self.assertEqual(result.summary.records[0].day, date(2026, 10, 19))


class _CasHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def _send(self, code, body="", headers=None):
        raw = body.encode("utf-8")
        self.send_response(code)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        port = self.server.server_port
        if self.path.startswith("/tpass/login"):
            action = (
                "/tpass/login?service=http%3A%2F%2F127.0.0.1%3A"
                f"{port}%2Fsports%2Flogin"
            )
            html = (
                '<html><form id="loginForm" action="' + action + '" method="post">'
                '<input name="lt" value="LT-test"><input name="execution" value="e1s1">'
                '</form><script src="/tpass/comm/neu/js/login_neu.js"></script></html>'
            )
            self._send(200, html, {"Content-Type": "text/html; charset=utf-8"})
        elif self.path.startswith("/tpass/comm/neu/js/login_neu.js"):
            self._send(200, f'const publicKeyStr = "{PUB}";', {"Content-Type": "application/javascript"})
        elif self.path.startswith("/sports/login"):
            self._send(
                302,
                "",
                {
                    "Location": "/sports/view#/pages/index/index?token=tok123&uid=123"
                    "&school_id=833&student_num=20260001&card_id=20260001&term_id=4771&user_type=2"
                },
            )
        else:
            self._send(200, "ok", {"Content-Type": "text/plain"})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        form = {key: values[0] for key, values in urllib.parse.parse_qs(self.rfile.read(length).decode()).items()}
        if self.path.startswith("/tpass/device"):
            info = "send" if form.get("m") == "2" else "ok"
            self._send(200, json.dumps({"info": info}), {"Content-Type": "application/json"})
            return
        if self.server.sms_mode and not self.server.sms_done:
            self.server.sms_done = True
            self._send(200, '<html><script>phone("m1","d1");</script></html>', {"Content-Type": "text/html"})
            return
        if form.get("un") == "20260001" and form.get("pd") == "pass" and form.get("rsa"):
            self._send(302, "", {"Location": "/sports/login?ticket=ST-123"})
        else:
            self._send(200, '<html><span id="errormsghide">账号或密码错误</span></html>', {"Content-Type": "text/html"})


class _CasServer:
    def __init__(self, sms_mode=False):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _CasHandler)
        self.httpd.sms_mode = sms_mode
        self.httpd.sms_done = False
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class CasTests(unittest.TestCase):
    def test_guide_url_detection(self):
        url = (
            "https://pass.neu.edu.cn/tp_tpass/h5?act=tpass%2Fguide"
            "&service=https%3A%2F%2Ftybzhtypt.neu.edu.cn%2Flogin"
        )
        self.assertTrue(_is_guide_url(url))
        self.assertFalse(_is_guide_url("https://pass.neu.edu.cn/tpass/login"))
        with self.assertRaises(CasGuideRequired) as ctx:
            CasLoginClient()._follow_to_token(url + "&ticket=ST-secret")
        self.assertNotIn("ST-secret", ctx.exception.url)
        self.assertTrue(ctx.exception.url.startswith("https://pass.neu.edu.cn/tp_tpass/h5"))

    def test_guide_url_strips_ticket(self):
        safe = _guide_url_for_browser(
            "https://pass.neu.edu.cn/tp_tpass/h5?act=tpass%2Fguide&ticket=ST-123&service=x"
        )
        self.assertNotIn("ST-123", safe)
        self.assertIn("service=x", safe)

    def test_login(self):
        server = _CasServer()
        try:
            client = CasLoginClient(
                service_url=server.url + "/sports/login",
                cas_base=server.url,
                timeout=10,
            )
            result = client.login("20260001", "pass")
            self.assertEqual(result.session.token, "tok123")
            self.assertEqual(result.session.uid, "123")
        finally:
            server.close()

    def test_wrong_password(self):
        server = _CasServer()
        try:
            client = CasLoginClient(
                service_url=server.url + "/sports/login",
                cas_base=server.url,
                timeout=10,
            )
            with self.assertRaises(CasLoginError):
                client.login("20260001", "wrong")
        finally:
            server.close()

    def test_sms(self):
        server = _CasServer(sms_mode=True)
        try:
            client = CasLoginClient(
                service_url=server.url + "/sports/login",
                cas_base=server.url,
                timeout=10,
            )
            result = client.login("20260001", "pass", sms_provider=lambda _challenge: "123456")
            self.assertEqual(result.session.token, "tok123")
        finally:
            server.close()


class ServiceLoginTests(unittest.TestCase):
    def test_login_persists_session_and_credentials(self):
        session = SportsSession(
            token="persist-token",
            uid="123",
            school_id="833",
            student_num="20260001",
            card_id="20260001",
            name="测试同学",
        )
        summary = RunSummary(
            fetched_at=datetime.now(),
            provider="测试体育平台",
            records=[
                RunRecord(day=date(2026, 10, 19), distance_km=3.47, duration_sec=1641, valid=True)
            ],
        )

        class FakeCas:
            def __init__(self):
                pass

            def login(self, username, password, sms_provider=None):
                from campusrun.neu.cas import CasLoginResult

                return CasLoginResult(session=session, final_url="http://test")

        class FakeSports:
            def __init__(self, sports_session):
                self.session = sports_session

            def fetch(self):
                return SportsFetch(summary=summary, term_id="4771", term_name="测试学期")

        with workspace_tmp() as tmp:
            paths = AppPaths(tmp)
            service = CampusRunService(paths)
            with patch("campusrun.service.CasLoginClient", FakeCas), patch(
                "campusrun.service.SportsClient", FakeSports
            ):
                result = service.login_neu("20260001", "pass", remember_password=True)
            self.assertAlmostEqual(result.completed_km, 3.47)
            self.assertEqual(service.config.auth_mode, "password")
            self.assertTrue(service.has_saved_credentials)
            reloaded = CampusRunService(paths)
            self.assertTrue(reloaded.has_neu_session)
            self.assertEqual(reloaded.sports_session.token, "persist-token")
            self.assertTrue(reloaded.has_saved_credentials)

    def test_test_login_does_not_persist(self):
        session = SportsSession(
            token="transient-token",
            uid="123",
            school_id="833",
            student_num="20260001",
            card_id="20260001",
        )
        summary = RunSummary(
            fetched_at=datetime.now(),
            provider="测试体育平台",
            records=[RunRecord(day=date(2026, 10, 19), distance_km=3.47, valid=True)],
        )

        class FakeCas:
            def __init__(self):
                pass

            def login(self, username, password, sms_provider=None):
                from campusrun.neu.cas import CasLoginResult

                return CasLoginResult(session=session, final_url="http://test")

        class FakeSports:
            def __init__(self, sports_session):
                self.session = sports_session

            def fetch(self):
                return SportsFetch(summary=summary, term_id="4771", term_name="测试学期")

        with workspace_tmp() as tmp:
            paths = AppPaths(tmp)
            service = CampusRunService(paths)
            with patch("campusrun.service.CasLoginClient", FakeCas), patch(
                "campusrun.service.SportsClient", FakeSports
            ):
                result = service.test_login_neu("20260001", "pass")
            self.assertAlmostEqual(result.completed_km, 3.47)
            self.assertIsNone(service.sports_session)
            self.assertIsNone(service.credentials)
            self.assertFalse(paths.sports_session_file.exists())
            self.assertFalse(paths.credentials_file.exists())
            self.assertTrue(service.config.demo_mode)


if __name__ == "__main__":
    unittest.main()
