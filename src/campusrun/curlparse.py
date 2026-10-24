"""把浏览器 / 抓包工具复制出来的 cURL（或原始 HTTP 请求）解析成请求对象。

支持：
* Linux / macOS 风格单引号；
* Windows cmd 的 ``^`` 续行与双引号转义；
* ``-H`` / ``--header`` / ``-b`` / ``--cookie`` / ``-d`` / ``--data-raw``
  / ``--data-urlencode`` / ``-X`` / ``-G`` / ``--compressed`` 等常用开关。
"""

from __future__ import annotations

import base64
import re
import shlex
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .errors import CaptureParseError
from .models import CapturedRequest

_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
_RAW_HTTP_RE = re.compile(r"^\s*(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+\S+\s+HTTP/\d", re.IGNORECASE)
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

_VALUE_OPTIONS = {
    "-X": "method",
    "--request": "method",
    "-H": "header",
    "--header": "header",
    "-d": "data",
    "--data": "data",
    "--data-raw": "data",
    "--data-binary": "data",
    "--data-ascii": "data",
    "--data-urlencode": "data",
    "--json": "json",
    "-b": "cookie",
    "--cookie": "cookie",
    "-u": "user",
    "--user": "user",
    "-A": "user_agent",
    "--user-agent": "user_agent",
    "-e": "referer",
    "--referer": "referer",
    "--url": "url",
}

_FLAG_OPTIONS = {
    "-k",
    "--insecure",
    "--compressed",
    "-s",
    "--silent",
    "-v",
    "--verbose",
    "-L",
    "--location",
    "-i",
    "--include",
    "-f",
    "--fail",
    "-g",
    "--globoff",
    "--http1.1",
    "--http2",
    "--http2-prior-knowledge",
    "--no-buffer",
    "-G",
    "--get",
    "--no-keepalive",
}


def _strip_continuations(text: str) -> str:
    text = text.lstrip("\ufeff").strip()
    text = re.sub(r"\^\s*\r?\n", " ", text)
    text = re.sub(r"\\\s*\r?\n", " ", text)
    return text.strip()


def _tokenize(text: str) -> list[str]:
    try:
        return shlex.split(text, posix=True)
    except ValueError as exc:
        raise CaptureParseError(f"cURL 引号不匹配，无法解析：{exc}") from exc


def _add_header(headers: dict[str, str], raw: str) -> None:
    if ":" in raw:
        name, value = raw.split(":", 1)
        name = name.strip()
        if not name:
            return
        _set_header(headers, name, value.strip())
    elif raw.endswith(";"):
        name = raw[:-1].strip()
        if name:
            _set_header(headers, name, "")
    elif raw.strip():
        raise CaptureParseError(f"请求头格式不正确：{raw!r}（应为 Name: Value）")


def _set_header(headers: dict[str, str], name: str, value: str) -> None:
    for existing in list(headers):
        if existing.lower() == name.lower():
            headers[existing] = f"{headers[existing]}, {value}" if value and headers[existing] else value
            return
    headers[name] = value


def _has_header(headers: dict[str, str], name: str) -> bool:
    return any(key.lower() == name.lower() for key in headers)


def _parse_raw_http(text: str) -> CapturedRequest:
    head, _, body = text.replace("\r\n", "\n").partition("\n\n")
    lines = head.split("\n")
    first = lines[0].split()
    if len(first) < 2:
        raise CaptureParseError("原始 HTTP 请求的第一行格式不正确")
    method = first[0].upper()
    target = first[1]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        if ":" not in line:
            raise CaptureParseError(f"原始 HTTP 请求头格式不正确：{line!r}")
        name, value = line.split(":", 1)
        if name.strip():
            headers[name.strip()] = value.strip()
    host = next((v for k, v in headers.items() if k.lower() == "host"), "")
    if target.startswith("/"):
        if not host:
            raise CaptureParseError("原始 HTTP 请求缺少 Host 头，无法补全 URL")
        target = f"https://{host}{target}"
    headers = {k: v for k, v in headers.items() if k.lower() != "host"}
    return CapturedRequest(
        method=method,
        url=target,
        headers=headers,
        body=body.strip() or None,
        source="原始 HTTP 请求",
    )


def parse_capture(text: str) -> CapturedRequest:
    """解析 cURL 命令 / 原始 HTTP 请求 / 纯 URL。"""

    if not text or not text.strip():
        raise CaptureParseError("请先粘贴 cURL 或 HTTP 请求")
    normalized = _strip_continuations(text)

    if _RAW_HTTP_RE.match(normalized):
        return _parse_raw_http(normalized)
    if _URL_RE.match(normalized):
        return CapturedRequest(method="GET", url=normalized, source="URL")

    if not normalized.lower().startswith(("curl ", "curl.exe ")):
        raise CaptureParseError("未识别到 cURL 命令；请在抓包工具中选择“复制为 cURL”。")

    tokens = _tokenize(normalized)
    if tokens and tokens[0].lower() in ("curl", "curl.exe"):
        tokens = tokens[1:]

    method: str | None = None
    url: str | None = None
    headers: dict[str, str] = {}
    data_parts: list[str] = []
    json_body: str | None = None
    insecure = False
    use_get = False
    index = 0
    total = len(tokens)

    def take_value(option: str, position: int) -> str:
        if position + 1 >= total:
            raise CaptureParseError(f"cURL 参数 {option} 缺少取值")
        return tokens[position + 1]

    while index < total:
        token = tokens[index]
        lower = token.lower()
        # 短选项区分大小写（-H 与 -h、-G 与 -g 含义不同）
        option_key = token if token.startswith("-") and not token.startswith("--") else lower

        # 粘连写法：-H"..." / -d"..." 等经 shlex 后合并成一个 token
        attached: tuple[str, str] | None = None
        for short in ("-H", "-X", "-d", "-b", "-A", "-e", "-u"):
            if token.startswith(short) and token != short:
                attached = (short, token[len(short) :])
                break

        if attached is not None:
            option, value = attached
            kind = _VALUE_OPTIONS[option]
            if kind == "header":
                _add_header(headers, value)
            elif kind == "method":
                method = value.upper()
            elif kind == "data":
                data_parts.append(value)
            elif kind == "cookie":
                _set_header(headers, "Cookie", value)
            elif kind == "user_agent":
                _set_header(headers, "User-Agent", value)
            elif kind == "referer":
                _set_header(headers, "Referer", value)
            elif kind == "user":
                _set_header(headers, "Authorization", "Basic " + base64.b64encode(value.encode()).decode())
            index += 1
            continue

        if option_key in _VALUE_OPTIONS:
            kind = _VALUE_OPTIONS[option_key]
            value = take_value(token, index)
            if kind == "header":
                _add_header(headers, value)
            elif kind == "method":
                method = value.upper()
            elif kind == "data":
                data_parts.append(value)
            elif kind == "json":
                json_body = value
            elif kind == "cookie":
                _set_header(headers, "Cookie", value)
            elif kind == "user_agent":
                _set_header(headers, "User-Agent", value)
            elif kind == "referer":
                _set_header(headers, "Referer", value)
            elif kind == "user":
                _set_header(headers, "Authorization", "Basic " + base64.b64encode(value.encode()).decode())
            elif kind == "url":
                url = value
            index += 2
            continue

        if option_key in _FLAG_OPTIONS:
            if option_key in ("-k", "--insecure"):
                insecure = True
            elif option_key in ("-G", "--get"):
                use_get = True
            index += 1
            continue

        if lower.startswith("--") and "=" in token:
            # --header=... / --data-raw=... 这类写法
            name, value = token.split("=", 1)
            kind = _VALUE_OPTIONS.get(name.lower())
            if kind == "header":
                _add_header(headers, value)
            elif kind == "data":
                data_parts.append(value)
            elif kind == "method":
                method = value.upper()
            elif kind == "url":
                url = value
            index += 1
            continue

        if _URL_RE.match(token) and url is None:
            url = token
            index += 1
            continue

        # 未知选项：跳过；未知普通 token 也跳过，避免把 -- 参数值误当 URL
        index += 1

    if not url:
        raise CaptureParseError("cURL 中没有找到 http(s) URL")

    body: str | None = json_body if json_body is not None else ("&".join(data_parts) if data_parts else None)
    if json_body is not None and not _has_header(headers, "Content-Type"):
        _set_header(headers, "Content-Type", "application/json")

    if method is None:
        method = "GET" if body is None else "POST"
    if use_get and body is not None:
        url = _append_query(url, body)
        body = None
        method = "GET"
    elif body is not None and method == "GET":
        # 显式 -X GET 且带 body：仍然把 body 转成查询串，避免 GET 带请求体被服务器忽略
        url = _append_query(url, body)
        body = None

    if not _URL_RE.match(url):
        raise CaptureParseError(f"只支持 http/https 地址：{url}")
    if not urlsplit(url).netloc:
        raise CaptureParseError(f"URL 缺少主机名：{url}")
    if body is not None and not _has_header(headers, "Content-Type"):
        _set_header(headers, "Content-Type", "application/x-www-form-urlencoded")

    return CapturedRequest(
        method=method,
        url=url,
        headers=headers,
        body=body,
        insecure=insecure,
    )


def _append_query(url: str, body: str) -> str:
    parts = urlsplit(url)
    query = parts.query
    try:
        pairs = parse_qsl(body, keep_blank_values=True)
        extra = urlencode(pairs)
    except ValueError:
        extra = body
    merged = f"{query}&{extra}" if query and extra else (extra or query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, merged, parts.fragment))


def describe_capture(request: CapturedRequest) -> str:
    lines = [
        f"方法：{request.method}",
        f"地址：{request.url}",
        f"请求头：{len(request.headers)} 个"
        + ("（Authorization / Cookie 等已隐藏）" if any(
            word in key.lower() for key in request.headers for word in ("authorization", "cookie", "token")
        ) else ""),
        f"请求体：{len(request.body)} 字节" if request.body else "请求体：无",
    ]
    if request.insecure:
        lines.append("TLS：忽略证书校验")
    return "\n".join(lines)
