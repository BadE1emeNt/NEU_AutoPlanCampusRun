"""演示数据源：没有抓包连接时也能完整体验规划功能。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ..models import RunRecord, RunSummary
from .base import Provider

_DEMO_RUNS = (
    (29, 3.2, 6.4),
    (26, 2.8, 6.1),
    (23, 4.0, 6.8),
    (20, 3.5, 6.2),
    (17, 2.0, 7.1),
    (14, 5.0, 6.6),
    (12, 2.4, 6.0),
    (9, 3.6, 6.5),
    (7, 4.2, 6.9),
    (5, 2.5, 6.3),
    (3, 3.2, 6.2),
    (2, 2.0, 7.0),
)


class MockProvider(Provider):
    name = "演示数据"
    is_demo = True

    def __init__(self, today: date | None = None):
        self.today = today or date.today()

    def fetch(self) -> RunSummary:
        records: list[RunRecord] = []
        for days_ago, km, pace in _DEMO_RUNS:
            day = self.today - timedelta(days=days_ago)
            records.append(
                RunRecord(
                    day=day,
                    distance_km=km,
                    duration_sec=int(round(km * pace * 60)),
                    valid=True,
                    run_id=f"demo-{days_ago}",
                    start_time=datetime.combine(day, datetime.min.time()).replace(hour=19, minute=30),
                )
            )
        return RunSummary(
            fetched_at=datetime.now(),
            provider=self.name,
            records=records,
            student="演示同学",
            count_mode="best_per_day",
            note="这是用于演示的模拟数据，不是你的真实记录。",
        )
