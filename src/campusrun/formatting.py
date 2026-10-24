"""中文展示格式化工具，CLI 与 GUI 共用。"""

from __future__ import annotations

from datetime import date


def fmt_number(value: float, digits: int = 1) -> str:
    if value == int(value):
        return f"{int(value)}"
    return f"{value:.{digits}f}"


def fmt_km(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f} km"


def fmt_km_compact(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))} km"
    return f"{value:.1f} km"


def fmt_date_iso(day: date) -> str:
    return day.isoformat()


def fmt_date_cn(day: date) -> str:
    return f"{day.year}年{day.month}月{day.day}日"


def fmt_date_short(day: date) -> str:
    return f"{day.month:02d}-{day.day:02d}"


def fmt_date_week(day: date) -> str:
    return f"{day.month}月{day.day}日 {weekday_cn(day)}"


def weekday_cn(day: date) -> str:
    return ("周一", "周二", "周三", "周四", "周五", "周六", "周日")[day.weekday()]


def fmt_minutes(minutes: float) -> str:
    if minutes < 1:
        return "不到 1 分钟"
    total = int(round(minutes))
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"{hours} 小时 {mins} 分"
    if hours:
        return f"{hours} 小时"
    return f"{mins} 分钟"


def fmt_duration(seconds: int | None) -> str:
    if not seconds or seconds <= 0:
        return "—"
    minutes, sec = divmod(int(seconds), 60)
    return f"{minutes}:{sec:02d}"


def fmt_pace(seconds_per_km: float | None) -> str:
    if not seconds_per_km or seconds_per_km <= 0:
        return "—"
    whole = int(seconds_per_km)
    minutes, sec = divmod(whole, 60)
    return f"{minutes}'{sec:02d}\"/km"


def fmt_percent(ratio: float) -> str:
    return f"{max(0.0, min(1.0, ratio)) * 100:.0f}%"


def fmt_signed_days(days: int) -> str:
    if days > 0:
        return f"余 {days} 天"
    if days == 0:
        return "刚好赶上"
    return f"缺 {abs(days)} 天"
