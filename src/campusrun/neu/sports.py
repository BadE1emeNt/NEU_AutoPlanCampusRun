"""东北大学体育平台（tybzhtypt）校园乐跑查询客户端。

协议来自 2026-10 的官方 H5 包：
* 请求体 ``ostype=5&data=<AES-128-CBC(JSON)>``；
* JSON 含 uid/token/school_id/... 与 MD5 签名；
* 响应 data 同样加密，status=1 成功。
"""

from __future__ import annotations

import hashlib
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..errors import CampusRunError
from ..models import RunRecord, RunSummary
from .crypto import aes_decrypt_base64, aes_encrypt_base64

BASE_URL = "https://tybzhtypt.neu.edu.cn"
API_PREFIX = "/v3/api.php/"
AES_KEY = b"Wet2C8d34f62ndi3"
AES_IV = b"K6iv85jBD8jgf32D"
SIGN_SALT = "rDJiNB9j7vD2"
USER_AGENT = (
    "Mozilla/5.0 (iPad; CPU OS 18_7 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 uni-app flutter ZhilinEai "
    "ZhilinNeuApp/3.1.8 iPad16,8 iOS 27.0"
)
MAX_PAGES = 20


class SportsError(CampusRunError):
    pass


class SportsSessionExpired(SportsError):
    pass


@dataclass
class SportsSession:
    token: str
    uid: str
    school_id: str
    student_num: str
    card_id: str
    role: int = 1
    term_id: str = "0"
    name: str = ""
    user_type: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "uid": self.uid,
            "school_id": self.school_id,
            "student_num": self.student_num,
            "card_id": self.card_id,
            "role": self.role,
            "term_id": self.term_id,
            "name": self.name,
            "user_type": self.user_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SportsSession":
        return cls(
            token=str(data.get("token") or ""),
            uid=str(data.get("uid") or ""),
            school_id=str(data.get("school_id") or ""),
            student_num=str(data.get("student_num") or ""),
            card_id=str(data.get("card_id") or ""),
            role=int(data.get("role") or 1),
            term_id=str(data.get("term_id") or "0"),
            name=str(data.get("name") or ""),
            user_type=int(data.get("user_type") or 2),
        )

    def is_complete(self) -> bool:
        return bool(self.token and self.uid and self.school_id and self.student_num)


@dataclass
class SportsFetch:
    summary: RunSummary
    term_id: str
    term_name: str
    identity: dict[str, Any] = field(default_factory=dict)


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _nonce() -> str:
    return str(random.randint(100000, 999999))


class SportsClient:
    def __init__(
        self,
        session: SportsSession,
        timeout: float = 25.0,
        base_url: str = BASE_URL,
    ):
        if not session.is_complete():
            raise SportsError("体育平台会话缺少 token/uid/学号，请重新登录。")
        self.session = session
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    def _payload(self, extra: dict[str, Any] | None = None, page: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "uid": self.session.uid,
            "token": self.session.token,
            "school_id": self.session.school_id,
            "term_id": self.session.term_id or "0",
            "course_id": 0,
            "class_id": 0,
            "student_num": self.session.student_num,
            "card_id": self.session.card_id,
            "timestamp": int(time.time()),
            "version": 1,
            "nonce": _nonce(),
            "ostype": "5",
            "role": self.session.role,
        }
        if extra:
            payload.update(extra)
        if page is not None:
            payload["page"] = page
        unsigned = {key: value for key, value in payload.items() if key != "sign"}
        concat = "".join(
            f"{key}{unsigned[key]}" for key in sorted(unsigned) if unsigned[key] is not None
        )
        payload["sign"] = _md5(concat + SIGN_SALT)
        return payload

    def _call(self, endpoint: str, extra: dict[str, Any] | None = None, page: int | None = None) -> Any:
        payload = self._payload(extra, page)
        encrypted = aes_encrypt_base64(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            AES_KEY,
            AES_IV,
        )
        body = urllib.parse.urlencode({"ostype": "5", "data": encrypted}).encode("ascii")
        request = urllib.request.Request(
            self.base_url + API_PREFIX + endpoint.lstrip("/"),
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "*/*",
                "Origin": self.base_url,
                "Referer": self.base_url + "/bdlp_h5_fitness_test/view/db/",
                "User-Agent": USER_AGENT,
                "Accept-Encoding": "identity",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(4 * 1024 * 1024)
                charset = response.headers.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            raise SportsError(f"体育平台返回 HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SportsError(f"无法连接体育平台：{exc}") from exc

        try:
            envelope = json.loads(text)
        except ValueError as exc:
            raise SportsError(f"体育平台返回不是 JSON：{text[:200]}") from exc
        if not isinstance(envelope, dict):
            raise SportsError("体育平台返回格式异常")
        status = str(envelope.get("status"))
        if status in {"101", "102", "103"}:
            raise SportsSessionExpired("体育平台登录态已失效，请重新登录。")
        if status != "1":
            raise SportsError(str(envelope.get("info") or f"体育平台错误 status={status}"))
        data = envelope.get("data")
        if isinstance(data, str):
            if not data:
                return None
            try:
                return json.loads(aes_decrypt_base64(data, AES_KEY, AES_IV))
            except (ValueError, UnicodeDecodeError) as exc:
                raise SportsError("体育平台响应解密失败") from exc
        return data

    # ------------------------------------------------------------------
    def get_term_list(self) -> list[dict[str, Any]]:
        data = self._call("WpRun/getTermList", {"term_id": "0"})
        return data if isinstance(data, list) else []

    def get_user_info(self) -> dict[str, Any]:
        data = self._call("WpLogin/UserInfo")
        return data if isinstance(data, dict) else {}

    def get_records(self, term_id: str, page: int = 1) -> dict[str, Any]:
        data = self._call("WpRun/getTermRunRecord", {"term_id": term_id}, page=page)
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    def fetch(self) -> SportsFetch:
        user = self.get_user_info()
        terms = self.get_term_list()
        current = next((term for term in terms if str(term.get("status")) == "1"), None)
        if current is None:
            current = terms[0] if terms else None
        if not current:
            raise SportsError("体育平台没有返回学期信息。")
        term_id = str(current.get("term_id") or "")
        term_name = str(current.get("term_name") or "")
        if not term_id:
            raise SportsError("体育平台学期 ID 为空。")

        all_records: list[RunRecord] = []
        total_km = 0.0
        total_runs = 0
        for page in range(1, MAX_PAGES + 1):
            page_data = self.get_records(term_id, page)
            total_km = float(page_data.get("total_distance") or 0.0)
            total_runs = int(page_data.get("total_num") or 0)
            items = page_data.get("list") or []
            for item in items:
                record = _record_from_item(item)
                if record is not None:
                    all_records.append(record)
            if len(items) < 10:
                break

        summary = RunSummary(
            fetched_at=datetime.now(),
            provider="东北大学体育平台",
            records=all_records,
            student=str(user.get("name") or "") or None,
            count_mode="best_per_day",
            note=f"{term_name} · 第 {term_id} 学期".strip(),
        )
        if not all_records and total_km > 0:
            summary.aggregate_km = round(total_km, 2)
            summary.aggregate_runs = total_runs or None
        self.session.term_id = term_id
        if user.get("name"):
            self.session.name = str(user["name"])
        return SportsFetch(summary=summary, term_id=term_id, term_name=term_name, identity=user)

    def fetch_summary(self) -> RunSummary:
        return self.fetch().summary


def _record_from_item(item: dict[str, Any]) -> RunRecord | None:
    try:
        start = int(float(item.get("start_time") or 0))
        end = int(float(item.get("end_time") or 0))
        distance = float(item.get("distance") or 0.0)
    except (TypeError, ValueError):
        return None
    if start <= 0 or distance <= 0:
        return None
    day = datetime.fromtimestamp(start).date()
    duration = max(0, end - start)
    valid = str(item.get("record_status") or "1") == "1"
    return RunRecord(
        day=day,
        distance_km=round(distance, 3),
        duration_sec=duration or None,
        valid=valid,
        run_id=str(item.get("id")) if item.get("id") is not None else None,
        start_time=datetime.fromtimestamp(start),
        raw=item,
    )
