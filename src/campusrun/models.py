"""领域模型：跑步记录、里程汇总、抓包请求与字段映射。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal
from urllib.parse import urlsplit

CountMode = Literal["best_per_day", "sum"]
MappingMode = Literal["records", "aggregate"]
DistanceUnit = Literal["auto", "km", "m"]
TimeUnit = Literal["auto", "s", "ms", "min"]


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class RunRecord:
    """一次跑步记录（已统一换算为 km / 秒）。"""

    day: date
    distance_km: float
    duration_sec: int | None = None
    valid: bool = True
    run_id: str | None = None
    start_time: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def pace_sec_per_km(self) -> float | None:
        if self.duration_sec and self.duration_sec > 0 and self.distance_km > 0:
            return self.duration_sec / self.distance_km
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "distance_km": round(self.distance_km, 3),
            "duration_sec": self.duration_sec,
            "valid": self.valid,
            "run_id": self.run_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunRecord":
        raw_day = data.get("day")
        day = date.fromisoformat(raw_day) if isinstance(raw_day, str) else date.today()
        raw_start = data.get("start_time")
        start = datetime.fromisoformat(raw_start) if isinstance(raw_start, str) else None
        duration = data.get("duration_sec")
        return cls(
            day=day,
            distance_km=max(0.0, _coerce_float(data.get("distance_km"))),
            duration_sec=int(duration) if duration is not None else None,
            valid=bool(data.get("valid", True)),
            run_id=str(data["run_id"]) if data.get("run_id") else None,
            start_time=start,
        )


@dataclass
class RunSummary:
    """一次数据获取的汇总。

    两种来源：
    * records    —— 接口返回逐条记录，本地汇总（可识别“每天只算一次”的规则）；
    * aggregate  —— 接口只返回总里程/总次数，直接采用。
    """

    fetched_at: datetime
    provider: str
    records: list[RunRecord] = field(default_factory=list)
    aggregate_km: float | None = None
    aggregate_runs: int | None = None
    student: str | None = None
    count_mode: CountMode = "best_per_day"
    note: str = ""

    # ---- 有效记录 -------------------------------------------------
    def effective_records(self) -> list[RunRecord]:
        valid = [r for r in self.records if r.valid and r.distance_km > 0]
        if self.count_mode == "sum":
            return sorted(valid, key=lambda r: r.day)
        # 校园乐跑每天最多 1 条有效记录：同一天只取最远的一次，避免高估。
        best: dict[date, RunRecord] = {}
        for rec in valid:
            current = best.get(rec.day)
            if current is None or rec.distance_km > current.distance_km:
                best[rec.day] = rec
        return sorted(best.values(), key=lambda r: r.day)

    @property
    def completed_km(self) -> float:
        if self.aggregate_km is not None:
            return round(max(0.0, float(self.aggregate_km)), 2)
        return round(sum(r.distance_km for r in self.effective_records()), 2)

    @property
    def completed_runs(self) -> int:
        if self.aggregate_runs is not None:
            return max(0, int(self.aggregate_runs))
        return len(self.effective_records())

    @property
    def raw_record_count(self) -> int:
        return len(self.records)

    @property
    def invalid_count(self) -> int:
        return sum(1 for r in self.records if not r.valid)

    @property
    def last_day(self) -> date | None:
        days = [r.day for r in self.records if r.valid]
        return max(days) if days else None

    def ran_today(self, today: date | None = None) -> bool:
        today = today or date.today()
        return any(r.valid and r.day == today for r in self.records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "fetched_at": self.fetched_at.isoformat(timespec="seconds"),
            "provider": self.provider,
            "student": self.student,
            "count_mode": self.count_mode,
            "aggregate_km": self.aggregate_km,
            "aggregate_runs": self.aggregate_runs,
            "note": self.note,
            "records": [r.to_dict() for r in self.records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunSummary":
        fetched_raw = data.get("fetched_at")
        try:
            fetched = datetime.fromisoformat(fetched_raw) if isinstance(fetched_raw, str) else datetime.now()
        except ValueError:
            fetched = datetime.now()
        mode = data.get("count_mode")
        return cls(
            fetched_at=fetched,
            provider=str(data.get("provider") or "缓存"),
            records=[RunRecord.from_dict(item) for item in data.get("records") or [] if isinstance(item, dict)],
            aggregate_km=_coerce_float(data["aggregate_km"]) if data.get("aggregate_km") is not None else None,
            aggregate_runs=int(data["aggregate_runs"]) if data.get("aggregate_runs") is not None else None,
            student=data.get("student"),
            count_mode="sum" if mode == "sum" else "best_per_day",
            note=str(data.get("note") or ""),
        )


@dataclass
class CapturedRequest:
    """从 cURL / 原始 HTTP 文本中解析出的请求。"""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    insecure: bool = False
    source: str = "cURL"

    @property
    def host(self) -> str:
        try:
            return urlsplit(self.url).netloc or self.url
        except ValueError:
            return self.url

    @property
    def path(self) -> str:
        try:
            parts = urlsplit(self.url)
            path = parts.path or "/"
            return f"{path}?{parts.query}" if parts.query else path
        except ValueError:
            return self.url

    def redacted_headers(self) -> dict[str, str]:
        sensitive = ("authorization", "cookie", "token", "session", "sign", "secret", "ticket")
        out: dict[str, str] = {}
        for key, value in self.headers.items():
            if any(word in key.lower() for word in sensitive):
                out[key] = _mask(value)
            else:
                out[key] = value
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "headers": self.headers,
            "body": self.body,
            "insecure": self.insecure,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CapturedRequest":
        headers = data.get("headers") or {}
        return cls(
            method=str(data.get("method") or "GET").upper(),
            url=str(data.get("url") or ""),
            headers={str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) else {},
            body=data.get("body"),
            insecure=bool(data.get("insecure", False)),
        )


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}…{value[-4:]}（已隐藏）"


@dataclass
class FieldMapping:
    """响应 JSON → 领域模型的字段映射。

    路径使用点号 + 下标：``data.list`` / ``data.rows[0].items``；
    记录字段既可以写键名，也可以写嵌套路径（如 ``sport.distance``）。
    """

    mode: MappingMode = "records"
    records_path: str = ""
    date_field: str = "date"
    distance_field: str = "distance"
    duration_field: str = ""
    valid_field: str = ""
    id_field: str = ""
    distance_unit: DistanceUnit = "auto"
    time_unit: TimeUnit = "auto"
    total_distance_path: str = ""
    total_runs_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "records_path": self.records_path,
            "date_field": self.date_field,
            "distance_field": self.distance_field,
            "duration_field": self.duration_field,
            "valid_field": self.valid_field,
            "id_field": self.id_field,
            "distance_unit": self.distance_unit,
            "time_unit": self.time_unit,
            "total_distance_path": self.total_distance_path,
            "total_runs_path": self.total_runs_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FieldMapping":
        mode = data.get("mode")
        distance_unit = data.get("distance_unit")
        time_unit = data.get("time_unit")
        return cls(
            mode="aggregate" if mode == "aggregate" else "records",
            records_path=str(data.get("records_path") or ""),
            date_field=str(data.get("date_field") or ""),
            distance_field=str(data.get("distance_field") or ""),
            duration_field=str(data.get("duration_field") or ""),
            valid_field=str(data.get("valid_field") or ""),
            id_field=str(data.get("id_field") or ""),
            distance_unit=distance_unit if distance_unit in ("auto", "km", "m") else "auto",  # type: ignore[arg-type]
            time_unit=time_unit if time_unit in ("auto", "s", "ms", "min") else "auto",  # type: ignore[arg-type]
            total_distance_path=str(data.get("total_distance_path") or ""),
            total_runs_path=str(data.get("total_runs_path") or ""),
        )

    def describe(self) -> str:
        if self.mode == "aggregate":
            return f"汇总模式：里程 ← {self.total_distance_path or '?'}；次数 ← {self.total_runs_path or '?'}"
        return (
            f"记录模式：列表 ← {self.records_path or '?'}；"
            f"日期 ← {self.date_field}；里程 ← {self.distance_field}"
            + (f"；用时 ← {self.duration_field}" if self.duration_field else "")
        )


@dataclass
class HttpConnection:
    """从抓包保存下来的只读接口连接。"""

    request: CapturedRequest
    mapping: FieldMapping
    label: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def display_name(self) -> str:
        return self.label or self.request.host

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "label": self.label,
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "request": self.request.to_dict(),
            "mapping": self.mapping.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HttpConnection":
        created_raw = data.get("created_at")
        try:
            created = datetime.fromisoformat(created_raw) if isinstance(created_raw, str) else datetime.now()
        except ValueError:
            created = datetime.now()
        request_data = data.get("request")
        if not isinstance(request_data, dict):
            raise ValueError("连接文件缺少 request 字段")
        mapping_data = data.get("mapping")
        return cls(
            request=CapturedRequest.from_dict(request_data),
            mapping=FieldMapping.from_dict(mapping_data if isinstance(mapping_data, dict) else {}),
            label=str(data.get("label") or ""),
            created_at=created,
        )
