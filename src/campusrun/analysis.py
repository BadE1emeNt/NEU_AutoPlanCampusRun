"""配速规划核心算法。

规则依据（东北大学体育部“校园智慧跑”）：
* 单次有效里程 2–5 km，配速 3–10 min/km；
* 每天最多 1 条有效记录；
* 每学期里程目标（默认 96 km，可在界面中修改）。

本模块只做“读数据之后的算术”，不涉及网络和界面，因此可以单独测试。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from .models import RunSummary

EPS = 1e-9
WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
DEFAULT_DAILY_OPTIONS = (2.0, 3.0, 4.0, 5.0)


def ceil_div(value: float, divisor: float) -> int:
    if divisor <= 0:
        raise ValueError("除数必须为正数")
    if value <= 0:
        return 0
    return max(1, math.ceil(value / divisor - EPS))


class PlanStatus(str, Enum):
    DONE = "done"
    ON_TRACK = "on_track"
    TIGHT = "tight"
    IMPOSSIBLE = "impossible"
    EXPIRED = "expired"

    @property
    def label(self) -> str:
        return {
            PlanStatus.DONE: "目标已达成",
            PlanStatus.ON_TRACK: "进度正常",
            PlanStatus.TIGHT: "时间偏紧",
            PlanStatus.IMPOSSIBLE: "无法完成",
            PlanStatus.EXPIRED: "已过截止日",
        }[self]

    @property
    def tone(self) -> str:
        return {
            PlanStatus.DONE: "success",
            PlanStatus.ON_TRACK: "ok",
            PlanStatus.TIGHT: "warn",
            PlanStatus.IMPOSSIBLE: "danger",
            PlanStatus.EXPIRED: "danger",
        }[self]


@dataclass(frozen=True, slots=True)
class PlanSettings:
    """用户可配置的规则参数。"""

    target_km: float = 96.0
    deadline: date = date.today()
    min_run_km: float = 2.0
    max_run_km: float = 5.0
    rest_weekdays: frozenset[int] = frozenset()
    daily_options: tuple[float, ...] = DEFAULT_DAILY_OPTIONS
    pace_min_per_km: float = 6.5
    max_runs_per_day: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.deadline, date):
            raise ValueError("截止日期必须是 date 类型")
        if self.target_km <= 0:
            raise ValueError("目标里程必须大于 0")
        if self.min_run_km <= 0:
            raise ValueError("单次最少里程必须大于 0")
        if self.max_run_km < self.min_run_km:
            raise ValueError("单次最多里程不能小于单次最少里程")
        if self.max_runs_per_day < 1:
            raise ValueError("每天有效次数至少为 1")
        if self.pace_min_per_km <= 0:
            raise ValueError("配速必须大于 0")
        rest = frozenset(int(x) for x in self.rest_weekdays)
        if any(x < 0 or x > 6 for x in rest):
            raise ValueError("休息日必须是 0（周一）到 6（周日）")
        object.__setattr__(self, "rest_weekdays", rest)
        options = tuple(float(x) for x in self.daily_options)
        if not options or any(x <= 0 for x in options):
            raise ValueError("每日里程选项必须为正数")
        if any(x > self.max_run_km + EPS for x in options):
            raise ValueError("每日里程选项不能超过单次上限")
        object.__setattr__(self, "daily_options", options)

    @property
    def rest_labels(self) -> str:
        return "、".join(WEEKDAY_NAMES[i] for i in sorted(self.rest_weekdays)) or "无"


@dataclass(frozen=True, slots=True)
class Progress:
    """当前进度快照。"""

    completed_km: float = 0.0
    completed_runs: int = 0
    ran_today: bool = False
    last_run: date | None = None
    source: str = "尚未连接"
    has_data: bool = False

    @classmethod
    def from_summary(cls, summary: RunSummary, today: date | None = None) -> "Progress":
        return cls(
            completed_km=summary.completed_km,
            completed_runs=summary.completed_runs,
            ran_today=summary.ran_today(today),
            last_run=summary.last_day,
            source=summary.provider,
            has_data=True,
        )


@dataclass(frozen=True, slots=True)
class Scenario:
    """“每天跑 d km” 的完成方案。"""

    per_day_km: float
    days: int
    finish: date | None
    slack_days: int | None
    feasible: bool
    planned_total_km: float
    avg_per_run_km: float


@dataclass(frozen=True, slots=True)
class PlannedRun:
    day: date
    km: float
    minutes: float

    @property
    def weekday(self) -> str:
        return WEEKDAY_NAMES[self.day.weekday()]


@dataclass(frozen=True, slots=True)
class PlanResult:
    today: date
    deadline: date
    target_km: float
    completed_km: float
    remaining_km: float
    completed_runs: int
    min_run_km: float
    max_run_km: float
    available_days: int
    calendar_days_left: int
    required_per_day_km: float
    min_days: int
    earliest_finish: date | None
    slack_days: int
    max_reachable_km: float
    feasible: bool
    status: PlanStatus
    scenarios: tuple[Scenario, ...]
    schedule: tuple[PlannedRun, ...]
    warnings: tuple[str, ...]
    ran_today: bool
    first_run_day: date | None
    available_dates: tuple[date, ...]
    source: str
    has_data: bool

    @property
    def progress_ratio(self) -> float:
        if self.target_km <= 0:
            return 1.0
        return max(0.0, min(1.0, self.completed_km / self.target_km))

    @property
    def recommended_daily_km(self) -> float:
        """把剩余里程摊到每个可跑日的建议值（已按 2–5 km 的边界修正）。"""

        if self.remaining_km <= 0:
            return 0.0
        if self.available_days <= 0:
            return float("inf")
        raw = self.required_per_day_km
        return max(self.min_run_km, min(self.max_run_km, raw))

    @property
    def total_minutes(self) -> float:
        return self.remaining_km * self.pace_min_per_km


def _daterange(start: date, end: date):
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def available_dates(first: date, deadline: date, rest_weekdays: frozenset[int]) -> list[date]:
    if deadline < first:
        return []
    return [day for day in _daterange(first, deadline) if day.weekday() not in rest_weekdays]


def build_plan(
    progress: Progress,
    settings: PlanSettings,
    today: date | None = None,
) -> PlanResult:
    today = today or date.today()
    target = round(float(settings.target_km), 2)
    completed = round(max(0.0, float(progress.completed_km)), 2)
    remaining = round(max(0.0, target - completed), 2)
    deadline = settings.deadline

    if deadline >= today:
        calendar_days_left = (deadline - today).days + 1
    else:
        calendar_days_left = 0

    first = today
    if progress.ran_today and settings.max_runs_per_day <= 1:
        first = today + timedelta(days=1)

    dates = available_dates(first, deadline, settings.rest_weekdays)
    avail_count = len(dates)

    min_days = ceil_div(remaining, settings.max_run_km) if remaining > 0 else 0
    max_reachable = round(avail_count * settings.max_run_km, 2)
    feasible = remaining <= 0 or (avail_count > 0 and min_days <= avail_count)
    required_per_day = (remaining / avail_count) if avail_count > 0 and remaining > 0 else 0.0

    if remaining <= 0:
        status = PlanStatus.DONE
    elif deadline < today:
        status = PlanStatus.EXPIRED
    elif not feasible:
        status = PlanStatus.IMPOSSIBLE
    elif avail_count - min_days <= 2:
        status = PlanStatus.TIGHT
    else:
        status = PlanStatus.ON_TRACK

    scenarios = tuple(
        _scenario_for(remaining, option, dates, settings.min_run_km, settings.max_run_km)
        for option in settings.daily_options
    )

    schedule = (
        schedule_for(remaining, dates, settings.max_run_km, settings)
        if feasible and remaining > 0
        else ()
    )

    warnings: list[str] = []
    if not progress.has_data:
        warnings.append("尚未获取真实账号数据，当前按 0 km 估算；连接后会自动刷新。")

    if remaining <= 0:
        warnings.append("目标已完成，可以保持每周 2–3 次轻松跑。")
    else:
        if progress.ran_today and settings.max_runs_per_day <= 1:
            warnings.append("检测到今天已有有效记录，计划从明天开始（每天最多计 1 次）。")
        if deadline < today:
            warnings.append(f"截止日期 {deadline.isoformat()} 已过，仍有 {remaining:.1f} km 未完成。")
        elif deadline == today:
            warnings.append("今天就是截止日。")
        if feasible and required_per_day < settings.min_run_km:
            warnings.append(
                f"按天摊平只需 {required_per_day:.2f} km，但单次有效记录至少 "
                f"{settings.min_run_km:g} km，实际需要约 {min_days} 次。"
            )
        if not feasible:
            if avail_count == 0:
                warnings.append("从现在到截止日没有可跑的日子，无法再完成剩余里程。")
            else:
                shortfall = max(0.0, remaining - max_reachable)
                warnings.append(
                    f"即使每个可跑日都跑满 {settings.max_run_km:g} km，最多完成 "
                    f"{max_reachable:.1f} km，仍差 {shortfall:.1f} km；需要放宽截止日或调整目标。"
                )
        elif status is PlanStatus.TIGHT:
            warnings.append(f"时间很紧：最多只剩 {avail_count - min_days} 天余量，建议尽早开始。")
        if settings.rest_weekdays and avail_count > 0:
            warnings.append(f"已排除每周休息日：{settings.rest_labels}；实际可跑 {avail_count} 天。")

    return PlanResult(
        today=today,
        deadline=deadline,
        target_km=target,
        completed_km=completed,
        remaining_km=remaining,
        completed_runs=max(0, int(progress.completed_runs)),
        min_run_km=settings.min_run_km,
        max_run_km=settings.max_run_km,
        available_days=avail_count,
        calendar_days_left=calendar_days_left,
        required_per_day_km=round(required_per_day, 3),
        min_days=min_days,
        earliest_finish=dates[min_days - 1] if feasible and remaining > 0 and min_days else None,
        slack_days=avail_count - min_days if remaining > 0 else 0,
        max_reachable_km=max_reachable,
        feasible=feasible,
        status=status,
        scenarios=scenarios,
        schedule=schedule,
        warnings=tuple(warnings),
        ran_today=progress.ran_today,
        first_run_day=dates[0] if dates else None,
        available_dates=tuple(dates),
        source=progress.source,
        has_data=progress.has_data,
    )


def _scenario_for(
    remaining: float,
    per_day: float,
    dates: list[date],
    min_run: float,
    max_run: float,
) -> Scenario:
    if remaining <= 0:
        return Scenario(per_day, 0, None, None, True, 0.0, 0.0)

    days = ceil_div(remaining, per_day)
    planned = max(remaining, days * min_run)
    planned = min(planned, days * max_run)
    feasible = days <= len(dates)
    finish = dates[days - 1] if feasible and days > 0 else None
    slack = (len(dates) - days) if feasible else None
    return Scenario(
        per_day_km=per_day,
        days=days,
        finish=finish,
        slack_days=slack,
        feasible=feasible,
        planned_total_km=round(planned, 2),
        avg_per_run_km=round(planned / days, 2) if days else 0.0,
    )


def schedule_for(
    remaining: float,
    dates: list[date] | tuple[date, ...],
    per_day: float,
    settings: PlanSettings,
) -> tuple[PlannedRun, ...]:
    """按“每次约 per_day km”生成逐日安排；最后一天吸收取整误差。"""

    if remaining <= 0 or not dates or per_day <= 0:
        return ()
    days = ceil_div(remaining, per_day)
    if days > len(dates):
        return ()

    total = max(remaining, days * settings.min_run_km)
    total = min(total, days * settings.max_run_km)
    per = total / days
    runs: list[PlannedRun] = []
    accumulated = 0.0
    for index in range(days):
        if index == days - 1:
            km = total - accumulated
        else:
            km = round(per, 2)
            accumulated += km
        km = max(settings.min_run_km, min(settings.max_run_km, round(km, 2)))
        runs.append(
            PlannedRun(
                day=dates[index],
                km=km,
                minutes=round(km * settings.pace_min_per_km, 1),
            )
        )
    return tuple(runs)
