"""基于抓包请求的 HTTP 数据源（只读 GET/POST，不提交任何跑步数据）。"""

from __future__ import annotations

import gzip
import json
import re
import socket
import ssl
import urllib.error
import urllib.request
import zlib
from typing import Any

from ..errors import MappingError, ProviderError
from ..models import HttpConnection, RunSummary
from .autodetect import looks_like_auth_error, summary_from_payload
from .base import Provider

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_DROP_HEADERS = {"host", "content-length", "accept-encoding", "connection", "transfer-encoding"}


class HttpProvider(Provider):
    """按保存的 cURL 请求取一次 JSON，再映射成 RunSummary。"""

    is_demo = False

    def __init__(self, connection: HttpConnection, timeout: float = 25.0, count_mode: str = "best_per_day"):
        if not connection.request.url:
            raise ProviderError("连接缺少 URL")
        self.connection = connection
        self.timeout = timeout
        self.count_mode = count_mode
        self.name = connection.display_name

    def fetch_json(self) -> Any:
        captured = self.connection.request
        headers = self._prepare_headers(captured.headers)
        body = captured.body.encode("utf-8") if captured.body is not None else None
        request = urllib.request.Request(
            captured.url,
            data=body,
            headers=headers,
            method=captured.method.upper(),
        )
        context = ssl.create_default_context()
        if captured.insecure:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=context) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                charset = response.headers.get_content_charset() or "utf-8"
                encoding = (response.headers.get("Content-Encoding") or "").lower()
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = _read_error_body(exc)
            if exc.code in (401, 403):
                raise ProviderError(
                    f"接口返回 HTTP {exc.code}：登录状态可能已过期。\n"
                    "请在小程序里重新进入页面并抓包，更新 Authorization / Cookie 后重试。"
                ) from exc
            raise ProviderError(f"接口返回 HTTP {exc.code}：{detail}") from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError, ssl.SSLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise ProviderError(
                "网络请求失败。\n"
                f"原因：{reason}\n"
                "请确认电脑网络能访问该接口（必要时连校园网），并检查系统代理设置。"
            ) from exc

        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProviderError("接口返回内容超过 8 MB，已停止读取。")
        if status == 204 or not raw:
            raise ProviderError("接口返回空内容（HTTP 204）。请确认抓到的请求仍然有效。")

        payload_bytes = _decompress(raw, encoding)
        text = payload_bytes.decode(charset, errors="replace").lstrip("\ufeff").strip()
        return _parse_json(text, captured.url)

    def fetch(self) -> RunSummary:
        payload = self.fetch_json()
        hint = looks_like_auth_error(payload)
        if hint:
            raise ProviderError(hint)
        try:
            summary = summary_from_payload(
                payload,
                self.connection.mapping,
                provider=self.name,
                count_mode=self.count_mode,
            )
        except MappingError as exc:
            raise ProviderError(str(exc)) from exc
        return summary

    @staticmethod
    def _prepare_headers(headers: dict[str, str]) -> dict[str, str]:
        prepared: dict[str, str] = {}
        for key, value in headers.items():
            lower = key.lower().strip()
            if lower in _DROP_HEADERS or lower.startswith(":"):
                continue
            prepared[key] = value
        if not any(key.lower() == "accept" for key in prepared):
            prepared["Accept"] = "application/json, text/plain, */*"
        if not any(key.lower() == "user-agent" for key in prepared):
            prepared["User-Agent"] = "CampusRun/0.1 (Windows)"
        prepared["Accept-Encoding"] = "identity"
        return prepared


def _decompress(raw: bytes, encoding: str) -> bytes:
    if "gzip" in encoding or raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw)
        except OSError:
            return raw
    if "deflate" in encoding:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            try:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
            except zlib.error:
                return raw
    return raw


def _parse_json(text: str, url: str) -> Any:
    if not text:
        raise ProviderError("接口返回空文本。")
    cleaned = text
    if cleaned.startswith(")]}',"):
        cleaned = cleaned.split("\n", 1)[-1]
    jsonp = re.match(r"^[\w$.]+\((.*)\)\s*;?\s*$", cleaned, re.DOTALL)
    if jsonp and not cleaned.startswith(("{", "[")):
        cleaned = jsonp.group(1)
    try:
        return json.loads(cleaned)
    except ValueError as exc:
        snippet = cleaned[:300].replace("\n", " ")
        hint = ""
        if cleaned.lstrip().startswith("<"):
            hint = "\n返回的是 HTML（可能是登录页或网关拦截页），说明登录状态已经失效。"
        raise ProviderError(
            f"返回内容不是 JSON，无法解析。\n地址：{url}\n片段：{snippet}{hint}"
        ) from exc


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read(600)
        charset = exc.headers.get_content_charset() if exc.headers else None
        text = raw.decode(charset or "utf-8", errors="replace").strip().replace("\n", " ")
        return text[:300] or "（无内容）"
    except Exception:  # noqa: BLE001 - 错误提示不应再次抛出
        return "（无法读取响应体）"
