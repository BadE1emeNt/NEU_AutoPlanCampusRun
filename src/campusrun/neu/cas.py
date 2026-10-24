"""东北大学统一身份认证（CAS）登录 + 体育平台 H5 token 获取。

登录流程（2026-10 抓包/页面确认）：

1. GET  https://pass.neu.edu.cn/tpass/login?service=<体育平台 neuLogin>
2. 解析 lt / execution，RSA(PKCS#1 v1.5) 加密 ``学号+密码`` 后 POST 登录表单
3. CAS 302 到体育平台 ``/login/neuLogin?ticket=ST-...``
4. 体育平台用 ticket 换 PHPSESSID，再 302 到 ``/view/db/#/pages/index/index?...&token=...``
5. 从最终 URL 取出 token / uid / 学号等，即可调用体育平台 API

若 CAS 返回“二次认证”，支持短信验证码回调；信任设备后后续通常不再要求。
"""

from __future__ import annotations

import base64
import http.client
import json
import re
import ssl
import urllib.parse
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from typing import Callable

from ..errors import CampusRunError
from .crypto import rsa_encrypt_base64
from .sports import SportsSession

CAS_BASE = "https://pass.neu.edu.cn"
CAS_LOGIN_PATH = "/tpass/login"
SPORTS_LOGIN_URL = (
    "https://tybzhtypt.neu.edu.cn/bdlp_h5_fitness_test/public/index.php/index/login/neuLogin"
)
USER_AGENT = (
    "Mozilla/5.0 (iPad; CPU OS 18_7 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 uni-app flutter ZhilinEai "
    "ZhilinNeuApp/3.1.8 iPad16,8 iOS 27.0"
)
# 仅作网络不可用时的兜底；优先从 login_neu.js 动态读取，密钥轮换时无需改代码。
FALLBACK_PUBLIC_KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnjA28DLKXZzxbKmo9/1WkVLf1mr+wtLXLXt6sC4WiBCts"
    "bzF5ewm7ARZeAdS3iZtqlYPn6IcUoOw42H8nAK/tfFcIb6dZ1K0atn0U39oWCGPzYuKtLJeMuNZiDXVuAXtojrc"
    "kOjLW9B3gUnaNGLuIx0fYe66l0o9WjU2cGLNZQfiIxs2h00z1EA9IdSnVxiVQWSD+lsP3JZXh2TT287la4Y4603SQN"
    "KTK/QvXfcmccwTEd1IW6HwGxD6QrkInBiHisKWxmveN7UDSaQRZ/J97G0YC32pD38WT53izXeK0p/kU/X37VP555um"
    "1wVWFvPIuc9I7gMP1+hq5a+X6c++tQIDAQAB"
)


class CasError(CampusRunError):
    pass


class CasLoginError(CasError):
    pass


@dataclass
class SmsChallenge:
    murmur: str = ""
    details: str = ""
    hint: str = ""


class SmsRequired(CasError):
    def __init__(self, challenge: SmsChallenge):
        super().__init__("统一身份认证要求短信二次验证。")
        self.challenge = challenge


@dataclass
class CasLoginResult:
    session: SportsSession
    final_url: str


@dataclass
class _Response:
    status: int
    headers: list[tuple[str, str]]
    body: bytes
    url: str

    @property
    def text(self) -> str:
        content_type = self.header("content-type") or ""
        match = re.search(r"charset=([\w-]+)", content_type, re.I)
        charset = match.group(1) if match else "utf-8"
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    def header(self, name: str) -> str | None:
        wanted = name.lower()
        for key, value in self.headers:
            if key.lower() == wanted:
                return value
        return None

    def header_values(self, name: str) -> list[str]:
        wanted = name.lower()
        return [value for key, value in self.headers if key.lower() == wanted]


class _Browser:
    def __init__(self, timeout: float = 25.0, insecure: bool = False):
        self.timeout = timeout
        self.insecure = insecure
        self._cookies: list[dict[str, object]] = []
        self._context = ssl.create_default_context()
        if insecure:
            self._context.check_hostname = False
            self._context.verify_mode = ssl.CERT_NONE

    # -- cookies -----------------------------------------------------
    def _store_cookies(self, response: _Response) -> None:
        for raw in response.header_values("set-cookie"):
            cookie = SimpleCookie()
            try:
                cookie.load(raw)
            except CookieError:
                continue
            for morsel in cookie.values():
                host = urllib.parse.urlsplit(response.url).hostname or ""
                domain = (morsel["domain"] or host).lstrip(".").lower()
                path = morsel["path"] or "/"
                entry = {
                    "domain": domain,
                    "path": path,
                    "name": morsel.key,
                    "value": morsel.value,
                    "secure": bool(morsel["secure"]),
                }
                self._cookies = [
                    item
                    for item in self._cookies
                    if not (
                        item["domain"] == domain
                        and item["path"] == path
                        and item["name"] == morsel.key
                    )
                ]
                self._cookies.append(entry)

    def _cookie_header(self, url: str) -> str:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        path = parts.path or "/"
        secure = parts.scheme == "https"
        values: list[str] = []
        for item in self._cookies:
            domain = str(item["domain"])
            if not (host == domain or host.endswith("." + domain)):
                continue
            if not path.startswith(str(item["path"])):
                continue
            if item["secure"] and not secure:
                continue
            values.append(f"{item['name']}={item['value']}")
        return "; ".join(values)

    def has_cookie(self, name: str) -> bool:
        return any(str(item["name"]).upper() == name.upper() for item in self._cookies)

    # -- request -----------------------------------------------------
    def request(
        self,
        method: str,
        url: str,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> _Response:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise CasError(f"无效 URL：{url}")
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        request_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        if headers:
            request_headers.update(headers)
        cookie = self._cookie_header(url)
        if cookie:
            request_headers["Cookie"] = cookie
        if data is not None:
            request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

        port = parts.port or (443 if parts.scheme == "https" else 80)
        if parts.scheme == "https":
            connection = http.client.HTTPSConnection(
                parts.hostname, port, timeout=self.timeout, context=self._context
            )
        else:
            connection = http.client.HTTPConnection(parts.hostname, port, timeout=self.timeout)
        try:
            connection.request(method, path, body=data, headers=request_headers)
            raw = connection.getresponse()
            body = raw.read(4 * 1024 * 1024)
            response = _Response(
                status=raw.status,
                headers=raw.getheaders(),
                body=body,
                url=url,
            )
        except (OSError, http.client.HTTPException) as exc:
            raise CasError(f"无法连接 {parts.hostname}：{exc}") from exc
        finally:
            connection.close()
        self._store_cookies(response)
        return response

    def get(self, url: str, headers: dict[str, str] | None = None) -> _Response:
        return self.request("GET", url, headers=headers)

    def post(
        self,
        url: str,
        form: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> _Response:
        body = urllib.parse.urlencode(form).encode("utf-8")
        return self.request("POST", url, data=body, headers=headers)


class CasLoginClient:
    def __init__(
        self,
        service_url: str = SPORTS_LOGIN_URL,
        cas_base: str = CAS_BASE,
        timeout: float = 25.0,
        insecure: bool = False,
    ):
        self.service_url = service_url
        self.cas_base = cas_base.rstrip("/")
        self.browser = _Browser(timeout=timeout, insecure=insecure)
        self._public_key: str | None = None
        self._login_html = ""
        self._login_response_url = ""
        self.trace: list[str] = []

    def _record(self, text: str) -> None:
        self.trace.append(text)
        if len(self.trace) > 20:
            del self.trace[:-20]

    def _trace_suffix(self) -> str:
        if not self.trace:
            return ""
        return "\n\n登录跳转链（ticket/token 已隐藏）：\n" + "\n".join(self.trace[-10:])

    def _error(self, message: str) -> CasLoginError:
        return CasLoginError(message + self._trace_suffix())

    # ------------------------------------------------------------------
    def _login_url(self) -> str:
        return f"{self.cas_base}{CAS_LOGIN_PATH}?service={urllib.parse.quote(self.service_url, safe='')}"

    def _login_page(self) -> tuple[str, dict[str, str]]:
        response = self.browser.get(self._login_url())
        if response.status != 200:
            raise CasLoginError(f"统一身份认证页面返回 HTTP {response.status}")
        html = response.text
        fields = _parse_hidden_fields(html)
        if "lt" not in fields or "execution" not in fields:
            raise CasLoginError("统一身份认证页面结构变化：未找到 lt / execution。")
        action = _parse_form_action(html) or self._login_url()
        action_url = urllib.parse.urljoin(response.url, action)
        self._login_html = html
        self._login_response_url = response.url
        return action_url, fields

    def _fetch_public_key(self) -> str:
        if self._public_key:
            return self._public_key
        try:
            script = _parse_script(self._login_html, "login_neu.js")
            if script:
                script_url = urllib.parse.urljoin(self._login_response_url, script)
                script_response = self.browser.get(script_url)
                match = re.search(r'publicKeyStr\s*=\s*["\']([^"\']+)["\']', script_response.text)
                if match:
                    self._public_key = match.group(1).strip()
                    return self._public_key
        except CasError:
            pass
        self._public_key = FALLBACK_PUBLIC_KEY
        return self._public_key

    # ------------------------------------------------------------------
    def login(
        self,
        username: str,
        password: str,
        sms_provider: Callable[[SmsChallenge], str] | None = None,
        trust_device: bool = True,
    ) -> CasLoginResult:
        if not username or not password:
            raise CasLoginError("账号和密码不能为空。")
        self.trace.clear()
        action_url, fields = self._login_page()
        self._record("GET 登录页 200")
        public_key = self._fetch_public_key()
        try:
            encrypted = rsa_encrypt_base64(username + password, public_key)
        except ValueError as exc:
            raise CasLoginError(f"登录密码加密失败：{exc}") from exc

        form = {
            "un": username,
            "pd": password,
            "rsa": encrypted,
            "ul": str(_js_length(username)),
            "pl": str(_js_length(password)),
            "lt": fields.get("lt", ""),
            "execution": fields.get("execution", ""),
            "_eventId": "submit",
            "t_un": "",
            "t_pd": "",
            "t_c": "",
        }
        response = self.browser.post(
            action_url,
            form,
            headers={
                "Origin": self.cas_base,
                "Referer": self._login_url(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        self._record(
            f"POST CAS 登录 -> {response.status}"
            + (f" Location {_redact_url(response.header('location') or '')}" if response.header("location") else "")
        )

        if response.status in (301, 302, 303, 307, 308):
            location = response.header("location")
            if not location:
                raise self._error("登录成功但没有跳转地址。")
            return self._follow_to_token(urllib.parse.urljoin(response.url, location))

        if response.status == 200:
            challenge = _parse_sms_challenge(response.text)
            if challenge is not None:
                self._record("CAS 200 短信二次认证")
                if sms_provider is None:
                    raise SmsRequired(challenge)
                return self._complete_sms(
                    action_url,
                    form,
                    challenge,
                    sms_provider,
                    trust_device,
                )
            message = _parse_login_error(response.text)
            if not message and self.browser.has_cookie("CASTGC"):
                # 少数情况下 CAS 返回 200 + 页面内 JS 跳转，但 CASTGC 已下发
                self._record("CAS 200，CASTGC 已下发，继续走服务")
                return self._follow_to_token(self.service_url)
            raise self._error(message or "登录失败：账号或密码错误，或需要短信二次认证。")

        raise self._error(f"登录请求返回 HTTP {response.status}")

    # ------------------------------------------------------------------
    def _complete_sms(
        self,
        action_url: str,
        form: dict[str, str],
        challenge: SmsChallenge,
        sms_provider: Callable[[SmsChallenge], str],
        trust_device: bool,
    ) -> CasLoginResult:
        sent = self._send_sms_code()
        if not sent:
            raise CasLoginError("短信验证码发送失败，请稍后重试或使用 cURL 登录态。")
        code = str(sms_provider(challenge)).strip()
        if not code:
            raise CasLoginError("未输入短信验证码。")
        verify = self.browser.post(
            urllib.parse.urljoin(self.cas_base, "/tpass/device"),
            {
                "d": challenge.murmur,
                "i": challenge.details,
                "m": "3",
                "u": form.get("un", ""),
                "c": code,
                "s": "1" if trust_device else "0",
            },
            headers={"Origin": self.cas_base, "Referer": self._login_url()},
        )
        try:
            result = json.loads(verify.text)
        except ValueError:
            result = {}
        info = str(result.get("info") or "")
        if info not in {"ok", "most"}:
            if info == "codeErr":
                raise CasLoginError("短信验证码有误。")
            if info == "timeout":
                raise CasLoginError("短信验证码已超时。")
            raise CasLoginError("短信二次认证失败。")

        # 二次认证通过后，浏览器会重新提交登录表单
        response = self.browser.post(
            action_url,
            form,
            headers={
                "Origin": self.cas_base,
                "Referer": self._login_url(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        if response.status not in (301, 302, 303, 307, 308):
            raise CasLoginError("短信验证通过后登录仍未跳转，请稍后重试。")
        location = response.header("location") or ""
        return self._follow_to_token(urllib.parse.urljoin(response.url, location))

    def _send_sms_code(self) -> bool:
        response = self.browser.post(
            urllib.parse.urljoin(self.cas_base, "/tpass/device"),
            {"m": "2"},
            headers={"Origin": self.cas_base, "Referer": self._login_url()},
        )
        try:
            data = json.loads(response.text)
        except ValueError:
            return False
        return str(data.get("info") or "") in {"send", "max"}

    # ------------------------------------------------------------------
    def _follow_to_token(self, location: str) -> CasLoginResult:
        current = location
        visited: set[str] = set()
        self._record(f"START {_redact_url(current)}")
        for _ in range(10):
            token = _parse_sports_token(current)
            if token is not None:
                if token.is_complete():
                    self._record(f"TOKEN 成功 uid={token.uid}（值已隐藏）")
                    return CasLoginResult(session=token, final_url=current)
                self._record("URL 含 token，但缺少 uid/学号等字段")
            if current in visited:
                self._record("检测到跳转循环")
                break
            visited.add(current)
            response = self.browser.get(current)
            self._record(
                f"GET {_redact_url(current)} -> {response.status}"
                + (f" Location {_redact_url(response.header('location') or '')}" if response.header("location") else "")
            )
            if response.status in (301, 302, 303, 307, 308):
                next_location = response.header("location")
                if not next_location:
                    break
                current = urllib.parse.urljoin(response.url, next_location)
                continue
            if response.status == 200:
                # 某些 WebView 会在页面里用 JS 跳转，兜底从 HTML 找 token
                token = _parse_sports_token(response.text)
                if token is not None and token.is_complete():
                    self._record("TOKEN 从页面内容解析成功")
                    return CasLoginResult(session=token, final_url=response.url)
                message = _parse_login_error(response.text)
                if message:
                    self._record(f"PAGE 错误：{message[:160]}")
                    raise self._error(message)
                self._record(f"PAGE {_page_hint(response.text)}")
                raise self._error(
                    "登录跳转后没有拿到体育平台 token；可能触发了短信二次认证或页面结构变化。"
                )
            raise self._error(f"登录跳转返回 HTTP {response.status}")
        raise self._error("登录跳转次数过多，或没有拿到 token。")


# ---------------------------------------------------------------------------
# 解析工具
# ---------------------------------------------------------------------------
def _parse_hidden_fields(html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for tag in re.findall(r"<input\b[^>]*>", html, re.I):
        attrs = _attrs(tag)
        name = attrs.get("name")
        if name:
            fields[name] = attrs.get("value", "")
    return fields


def _parse_form_action(html: str) -> str | None:
    match = re.search(r"<form\b[^>]*id=[\"']loginForm[\"'][^>]*>", html, re.I)
    if match:
        attrs = _attrs(match.group(0))
        return attrs.get("action")
    match = re.search(r"<form\b[^>]*>", html, re.I)
    return _attrs(match.group(0)).get("action") if match else None


def _parse_script(html: str, needle: str) -> str | None:
    for tag in re.findall(r"<script\b[^>]*>", html, re.I):
        attrs = _attrs(tag)
        src = attrs.get("src", "")
        if needle in src:
            return src
    return None


def _attrs(tag: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for match in re.finditer(r"([a-zA-Z_:][\w:.-]*)\s*=\s*([\"'])(.*?)\2", tag, re.S):
        result[match.group(1).lower()] = match.group(3)
    return result


def _js_length(value: str) -> int:
    """JavaScript String.length 按 UTF-16 代码单元计数。"""

    return len(value.encode("utf-16-le")) // 2


def _parse_login_error(html: str) -> str:
    for pattern in (
        r"<span[^>]*id=[\"']errormsghide[\"'][^>]*>(.*?)</span>",
        r"<span[^>]*id=[\"']errormsg[\"'][^>]*>(.*?)</span>",
    ):
        match = re.search(pattern, html, re.S | re.I)
        if match:
            text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            if text:
                return text
    match = re.search(r"layer\.msg\([\"']([^\"']+)[\"']\)", html)
    if match:
        return match.group(1)
    return ""


def _parse_sms_challenge(html: str) -> SmsChallenge | None:
    # 登录页本身就包含隐藏的 mcode 模板，不能只看 mcode；必须看到 phone(...) 调用。
    match = re.search(
        r"phone\(\s*([\"'])(.*?)\1\s*,\s*([\"'])(.*?)\3\s*\)",
        html,
        re.S,
    )
    if match:
        return SmsChallenge(murmur=match.group(2), details=match.group(4), hint="请输入短信验证码")
    return None


def _page_hint(html: str) -> str:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
    body = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    body = re.sub(
        r"(?i)\b(ticket|token|code|session|student_num|card_id|uid|account)=([^\s&]+)",
        r"\1=<hidden>",
        body,
    )
    text = (title + " | " if title else "") + body[:180]
    return text


def _redact_url(value: str) -> str:
    if not value:
        return ""
    sensitive = {"ticket", "token", "code", "session", "student_num", "card_id", "uid", "account"}
    try:
        parts = urllib.parse.urlsplit(value)
        query = []
        for key, item in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
            query.append((key, "<hidden>" if key.lower() in sensitive else item))
        fragment = parts.fragment
        fragment = re.sub(
            r"(?i)\b(ticket|token|code|session|student_num|card_id|uid|account)=([^&]+)",
            r"\1=<hidden>",
            fragment,
        )
        redacted = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), fragment)
        )
        return redacted[:260]
    except ValueError:
        return value[:260]


def _parse_sports_token(value: str) -> SportsSession | None:
    if "token=" not in value:
        return None
    try:
        parts = urllib.parse.urlsplit(value)
        query = parts.query
        if parts.fragment and "?" in parts.fragment:
            query += "&" + parts.fragment.split("?", 1)[1]
        params = urllib.parse.parse_qs(query)
    except ValueError:
        return None
    token = (params.get("token") or [""])[0]
    if not token:
        return None
    return SportsSession(
        token=token,
        uid=(params.get("uid") or [""])[0],
        school_id=(params.get("school_id") or [""])[0],
        student_num=(params.get("student_num") or [""])[0],
        card_id=(params.get("card_id") or [""])[0],
        role=1,
        term_id=(params.get("term_id") or ["0"])[0],
        user_type=int((params.get("user_type") or ["2"])[0] or 2),
    )
