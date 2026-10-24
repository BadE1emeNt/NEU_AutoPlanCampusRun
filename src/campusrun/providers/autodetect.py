"""从抓包返回的 JSON 中自动识别跑步记录 / 汇总字段，并转换为领域模型。

目标：用户只需要粘贴一条 cURL，程序尽量自动找出“记录数组”和字段；
识别不准时仍可在界面里手工改 JSON 路径。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from ..errors import MappingError, ProviderError
from ..jsonpath import get_path, walk_paths
from ..models import FieldMapping, RunRecord, RunSummary

DISTANCE_KEYS = {
    "distance",
    "dist",
    "km",
    "mileage",
    "kilometre",
    "kilometer",
    "kilometres",
    "kilometers",
    "distancekm",
    "distancem",
    "totaldistance",
    "totaldistancekm",
    "totalmileage",
    "totalkm",
    "sumkm",
    "runkm",
    "sportdistance",
    "runmileage",
    "sumdistance",
    "mileages",
    "distancevalue",
    "里程",
    "距离",
    "公里数",
}

DATE_KEYS = {
    "date",
    "day",
    "rundate",
    "starttime",
    "begintime",
    "endtime",
    "createtime",
    "recorddate",
    "sportdate",
    "startdate",
    "datestr",
    "datetime",
    "time",
    "recordtime",
    "enddate",
    "日期",
    "开始时间",
    "跑步时间",
}

DURATION_KEYS = {
    "duration",
    "runtime",
    "usetime",
    "costtime",
    "elapsed",
    "sporttime",
    "totaltime",
    "durationsecond",
    "durationseconds",
    "runsecond",
    "seconds",
    "用时",
    "时长",
}

VALID_KEYS = {"valid", "isvalid", "effective", "iseffective", "status", "state", "auditstatus", "是否有效"}
ID_KEYS = {"id", "runid", "recordid", "sportid", "pk", "recordno"}
RUNS_KEYS = {
    "count",
    "times",
    "runcount",
    "totalcount",
    "totaltimes",
    "totalruns",
    "totalrun",
    "runs",
    "num",
    "runnum",
    "frequency",
    "days",
    "totalnum",
    "runscount",
    "number",
    "次数",
    "总次数",
}
CONTAINER_NAMES = {"list", "rows", "records", "items", "data", "result", "runs", "sports", "details", "content"}

_TOTAL_PREFIXES = ("total", "sum", "all", "accumulate", "累计", "总")
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y年%m月%d日 %H:%M:%S",
    "%Y年%m月%d日 %H:%M",
    "%Y年%m月%d日",
    "%Y%m%d%H%M%S",
    "%Y%m%d",
    "%m-%d",
    "%m/%d",
)


def _norm_key(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


def coerce_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("，", "")
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def coerce_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone().replace(tzinfo=None)
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, (int, float)):
        return _from_epoch(float(value))
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{10}|\d{13}", text):
        return _from_epoch(float(text))
    if re.fullmatch(r"\d{8}", text):
        try:
            return datetime.strptime(text, "%Y%m%d")
        except ValueError:
            return None
    if re.fullmatch(r"\d{14}", text):
        try:
            return datetime.strptime(text, "%Y%m%d%H%M%S")
        except ValueError:
            return None
    # ISO（含 Z / 时区偏移）
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            if "%Y" not in fmt:
                parsed = parsed.replace(year=date.today().year)
            return parsed
        except ValueError:
            continue
    return None


def _from_epoch(number: float) -> datetime | None:
    seconds = number / 1000.0 if number >= 1e12 else number
    if seconds < 946684800 or seconds > 4102444800:  # 2000–2100
        return None
    try:
        return datetime.fromtimestamp(seconds)
    except (OverflowError, OSError, ValueError):
        return None


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "valid", "effective", "有效", "是", "成功", "正常"}:
        return True
    if text in {"false", "0", "no", "invalid", "无效", "否", "失败"}:
        return False
    return True


def _to_km(value: float, unit: str, aggregate: bool = False) -> float:
    if unit == "m":
        return value / 1000.0
    if unit == "km":
        return value
    threshold = 500.0 if aggregate else 100.0
    return value / 1000.0 if value >= threshold else value


def _to_seconds(value: float, unit: str) -> int:
    if unit == "ms":
        return int(round(value / 1000.0))
    if unit == "min":
        return int(round(value * 60))
    if unit == "s":
        return int(round(value))
    if value >= 100000:
        return int(round(value / 1000.0))
    if value >= 120:
        return int(round(value))
    return int(round(value * 60))


def _find_field(record: dict[str, Any], candidates: set[str]) -> str:
    for key in record:
        if _norm_key(str(key)) in candidates:
            return str(key)
    for key, value in record.items():
        if isinstance(value, dict):
            nested = _find_field(value, candidates)
            if nested:
                return f"{key}.{nested}"
    return ""


def _find_date_field(record: dict[str, Any]) -> str:
    candidates: list[tuple[str, Any]] = []
    for key, value in record.items():
        if _norm_key(str(key)) in DATE_KEYS:
            candidates.append((str(key), value))
        elif isinstance(value, dict):
            for nested_key, nested_value in value.items():
                if _norm_key(str(nested_key)) in DATE_KEYS:
                    candidates.append((f"{key}.{nested_key}", nested_value))
    for path, value in candidates:
        if coerce_datetime(value) is not None:
            return path
    return candidates[0][0] if candidates else ""


def _looks_like_record_list(path: str, data: list[Any]) -> dict[str, Any] | None:
    if not data or not all(isinstance(item, dict) for item in data[:5]):
        return None
    first = data[0]
    distance_field = _find_field(first, DISTANCE_KEYS)
    if not distance_field:
        return None
    date_field = _find_date_field(first)
    duration_field = _find_field(first, DURATION_KEYS)
    valid_field = _find_field(first, VALID_KEYS)
    id_field = _find_field(first, ID_KEYS)
    score = 10
    if date_field:
        score += 5
    if duration_field:
        score += 2
    if valid_field:
        score += 1
    if path == "" or path.split(".")[-1].split("[")[0] in CONTAINER_NAMES:
        score += 2

    distance_values = [coerce_number(get_path(item, distance_field)) for item in data[:3]]
    numeric = [v for v in distance_values if v is not None]
    if numeric and any(0.5 <= v <= 10 or 500 <= v <= 10000 for v in numeric):
        score += 2
    if date_field:
        dates = [coerce_datetime(get_path(item, date_field)) for item in data[:3]]
        if any(d is not None for d in dates):
            score += 3
    return {
        "path": path,
        "score": score,
        "distance": distance_field,
        "date": date_field,
        "duration": duration_field,
        "valid": valid_field,
        "id": id_field,
    }


def _best_record_list(payload: Any) -> tuple[dict[str, Any] | None, list[str]]:
    best: dict[str, Any] | None = None
    empty_candidates: list[str] = []
    for path, value in walk_paths(payload):
        if not isinstance(value, list):
            continue
        if not value:
            last = path.split(".")[-1].split("[")[0]
            if path == "" or last in CONTAINER_NAMES:
                empty_candidates.append(path)
            continue
        candidate = _looks_like_record_list(path, value)
        if candidate and (best is None or (candidate["score"], -len(path)) > (best["score"], -len(best["path"]))):
            best = candidate
    return best, empty_candidates


def _find_aggregate_paths(payload: Any) -> tuple[str, str]:
    distance_choice: tuple[int, int, str] | None = None
    runs_choice: tuple[int, int, str] | None = None
    for path, value in walk_paths(payload):
        if isinstance(value, (dict, list)):
            continue
        if path.endswith("]"):
            continue
        key = path.split(".")[-1]
        norm = _norm_key(key)
        number = coerce_number(value)
        if number is None or number <= 0:
            continue
        if norm in DISTANCE_KEYS:
            score = 3 if norm.startswith(_TOTAL_PREFIXES) else 1
            choice = (score, -len(path), path)
            if distance_choice is None or choice[:2] > distance_choice[:2]:
                distance_choice = choice
        if norm in RUNS_KEYS:
            score = 3 if norm.startswith(_TOTAL_PREFIXES) else 1
            choice = (score, -len(path), path)
            if runs_choice is None or choice[:2] > runs_choice[:2]:
                runs_choice = choice
    return (distance_choice[2] if distance_choice else "", runs_choice[2] if runs_choice else "")


@dataclass
class Detection:
    mapping: FieldMapping
    notes: str
    sample_records: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def detect(payload: Any) -> Detection:
    best, empty_candidates = _best_record_list(payload)
    aggregate_distance, aggregate_runs = _find_aggregate_paths(payload)

    if best:
        mapping = FieldMapping(
            mode="records",
            records_path=best["path"],
            date_field=best["date"],
            distance_field=best["distance"],
            duration_field=best["duration"],
            valid_field=best["valid"],
            id_field=best["id"],
        )
        field_summary = f"日期 {best['date'] or '未识别'}"
        if best["duration"]:
            field_summary += f" / 用时 {best['duration']}"
        notes = (
            f"找到记录数组：{best['path'] or '根数组'}；字段："
            f"里程 {best['distance']}、{field_summary}。"
        )
        return Detection(mapping=mapping, notes=notes, sample_records=len(get_path(payload, best["path"]) or []))

    if aggregate_distance:
        mapping = FieldMapping(
            mode="aggregate",
            total_distance_path=aggregate_distance,
            total_runs_path=aggregate_runs,
        )
        notes = f"只找到汇总字段：总里程 ← {aggregate_distance}"
        if aggregate_runs:
            notes += f"；总次数 ← {aggregate_runs}"
        return Detection(mapping=mapping, notes=notes + "。")

    if empty_candidates:
        path = min(empty_candidates, key=len)
        mapping = FieldMapping(mode="records", records_path=path)
        return Detection(
            mapping=mapping,
            notes=f"记录数组 {path or '根数组'} 当前为空（可能本学期还没有有效记录），请确认后保存。",
            sample_records=0,
        )

    keys = ", ".join(list(payload.keys())[:12]) if isinstance(payload, dict) else type(payload).__name__
    raise MappingError(
        "响应中没有找到跑步记录数组或总里程字段。\n"
        f"顶层字段：{keys}\n"
        "请确认这条请求返回的是跑步统计/记录，或在高级设置里手工填写 JSON 路径。"
    )


def _record_from_item(item: dict[str, Any], mapping: FieldMapping) -> tuple[RunRecord | None, str]:
    distance_field = mapping.distance_field or _find_field(item, DISTANCE_KEYS)
    if not distance_field:
        return None, "缺少里程字段"
    date_field = mapping.date_field or _find_date_field(item)
    if not date_field:
        return None, "缺少日期字段"

    distance_raw = coerce_number(get_path(item, distance_field))
    if distance_raw is None or distance_raw <= 0:
        return None, "里程无效"
    distance_km = _to_km(distance_raw, mapping.distance_unit)
    if distance_km <= 0 or distance_km > 100:
        return None, "里程超出合理范围"

    start = coerce_datetime(get_path(item, date_field))
    if start is None:
        return None, "日期无法解析"

    duration: int | None = None
    if mapping.duration_field:
        duration_raw = coerce_number(get_path(item, mapping.duration_field))
        if duration_raw and duration_raw > 0:
            duration = _to_seconds(duration_raw, mapping.time_unit)

    valid = True
    if mapping.valid_field:
        raw_valid = get_path(item, mapping.valid_field)
        if raw_valid is not None:
            valid = coerce_bool(raw_valid)

    run_id = None
    if mapping.id_field:
        raw_id = get_path(item, mapping.id_field)
        if raw_id is not None and str(raw_id).strip():
            run_id = str(raw_id)

    start_time = None if start.time() == time.min else start
    return (
        RunRecord(
            day=start.date(),
            distance_km=round(distance_km, 3),
            duration_sec=duration,
            valid=valid,
            run_id=run_id,
            start_time=start_time,
            raw=item,
        ),
        "",
    )


def summary_from_payload(
    payload: Any,
    mapping: FieldMapping,
    provider: str = "抓包接口",
    count_mode: str = "best_per_day",
) -> RunSummary:
    mapping_error = looks_like_auth_error(payload)
    if mapping_error:
        raise ProviderError(mapping_error)

    if mapping.mode == "aggregate":
        if not mapping.total_distance_path:
            raise MappingError("汇总模式缺少“总里程”路径")
        raw = get_path(payload, mapping.total_distance_path)
        number = coerce_number(raw)
        if number is None:
            raise MappingError(f"总里程路径没有取到数字：{mapping.total_distance_path}")
        km = _to_km(number, mapping.distance_unit, aggregate=True)
        runs: int | None = None
        if mapping.total_runs_path:
            raw_runs = coerce_number(get_path(payload, mapping.total_runs_path))
            if raw_runs is not None:
                runs = max(0, int(round(raw_runs)))
        return RunSummary(
            fetched_at=datetime.now(),
            provider=provider,
            records=[],
            aggregate_km=round(km, 2),
            aggregate_runs=runs,
            count_mode="best_per_day" if count_mode != "sum" else "sum",
            note=mapping.describe(),
        )

    data = get_path(payload, mapping.records_path)
    if data is None:
        raise MappingError(f"记录数组路径没有取到数据：{mapping.records_path or '（根）'}")
    if not isinstance(data, list):
        raise MappingError(f"记录数组路径不是数组：{mapping.records_path or '（根）'}（实际为 {type(data).__name__}）")

    records: list[RunRecord] = []
    skipped = 0
    reasons: dict[str, int] = {}
    for item in data[:5000]:
        if not isinstance(item, dict):
            skipped += 1
            continue
        record, reason = _record_from_item(item, mapping)
        if record is None:
            skipped += 1
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            records.append(record)

    if data and not records:
        sample_keys = ", ".join(list(data[0].keys())[:12]) if isinstance(data[0], dict) else "?"
        detail = "；".join(f"{k} {v} 条" for k, v in reasons.items()) or "字段映射不匹配"
        raise MappingError(
            f"读取到 {len(data)} 条原始记录，但没有一条能解析。\n"
            f"原因：{detail}\n"
            f"记录里的字段：{sample_keys}\n"
            "请在高级设置里核对日期、里程字段名（或重新粘贴 cURL 自动识别）。"
        )

    note = mapping.describe()
    if skipped:
        note += f"；跳过 {skipped} 条无法解析的记录"
    return RunSummary(
        fetched_at=datetime.now(),
        provider=provider,
        records=records,
        count_mode="best_per_day" if count_mode != "sum" else "sum",
        note=note,
    )


def looks_like_auth_error(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    code = payload.get("code", payload.get("status", payload.get("errCode")))
    message = str(payload.get("msg") or payload.get("message") or payload.get("error") or "")
    code_text = str(code) if code is not None else ""
    if code_text in {"401", "403"}:
        suffix = f"（接口提示：{message}）" if message else ""
        return f"接口返回未授权（401/403）：登录状态可能已过期，请重新抓包更新 Authorization / Cookie。{suffix}"
    if any(word in message for word in ("未登录", "登录失效", "登录已过期", "token 失效", "token无效", "Token失效")):
        return "接口提示未登录或登录已过期，请重新抓包。"
    if code_text in {"-1", "500"} and ("登录" in message or "token" in message.lower()):
        return f"接口提示：{message}。请重新抓包更新凭据。"
    return None


def describe_result(payload: Any, mapping: FieldMapping) -> str:
    try:
        summary = summary_from_payload(payload, mapping)
    except (ProviderError, MappingError) as exc:
        return f"暂不能解析：{exc}"
    if mapping.mode == "aggregate":
        runs = f"{summary.completed_runs} 次" if summary.aggregate_runs is not None else "次数未知"
        return f"解析成功：总里程 {summary.completed_km:.2f} km，{runs}（汇总字段）"
    return (
        f"解析成功：{summary.completed_runs} 次有效记录，共 {summary.completed_km:.2f} km"
        f"（原始 {summary.raw_record_count} 条）。"
    )
