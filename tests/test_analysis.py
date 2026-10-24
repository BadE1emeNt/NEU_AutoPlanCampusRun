from __future__ import annotations

import unittest
from datetime import date, timedelta

from campusrun.analysis import (
    PlanSettings,
    PlanStatus,
    Progress,
    available_dates,
    build_plan,
    ceil_div,
    schedule_for,
)

TODAY = date(2026, 10, 24)  # 周六
DEADLINE = date(2027, 1, 10)


def make_settings(**overrides) -> PlanSettings:
    values = dict(target_km=96.0, deadline=DEADLINE)
    values.update(overrides)
    return PlanSettings(**values)


def make_progress(**overrides) -> Progress:
    values = dict(completed_km=38.4, completed_runs=12, source="演示数据", has_data=True)
    values.update(overrides)
    return Progress(**values)


class CeilDivTests(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(ceil_div(10, 5), 2)

    def test_round_up(self):
        self.assertEqual(ceil_div(10.1, 5), 3)
        self.assertEqual(ceil_div(57.6, 5), 12)

    def test_zero(self):
        self.assertEqual(ceil_div(0, 5), 0)


class AvailableDatesTests(unittest.TestCase):
    def test_all_days(self):
        days = available_dates(TODAY, DEADLINE, frozenset())
        self.assertEqual(len(days), 79)
        self.assertEqual(days[0], TODAY)
        self.assertEqual(days[-1], DEADLINE)

    def test_weekends_rest(self):
        days = available_dates(TODAY, DEADLINE, frozenset({5, 6}))
        self.assertEqual(len(days), 55)
        self.assertTrue(all(d.weekday() < 5 for d in days))
        self.assertEqual(days[0], date(2026, 10, 26))

    def test_deadline_before_start(self):
        self.assertEqual(available_dates(TODAY, TODAY - timedelta(days=1), frozenset()), [])


class BuildPlanTests(unittest.TestCase):
    def test_basic_plan(self):
        plan = build_plan(make_progress(), make_settings(), TODAY)
        self.assertEqual(plan.remaining_km, 57.6)
        self.assertEqual(plan.available_days, 79)
        self.assertAlmostEqual(plan.required_per_day_km, 0.729, places=3)
        self.assertEqual(plan.min_days, 12)
        self.assertEqual(plan.earliest_finish, date(2026, 11, 4))
        self.assertTrue(plan.feasible)
        self.assertEqual(plan.status, PlanStatus.ON_TRACK)
        self.assertEqual(plan.slack_days, 67)
        self.assertEqual(plan.recommended_daily_km, 2.0)
        self.assertEqual(plan.min_run_km, 2.0)
        self.assertEqual(plan.max_run_km, 5.0)

    def test_scenarios(self):
        plan = build_plan(make_progress(), make_settings(), TODAY)
        by_option = {s.per_day_km: s for s in plan.scenarios}
        self.assertEqual(by_option[2.0].days, 29)
        self.assertEqual(by_option[3.0].days, 20)
        self.assertEqual(by_option[4.0].days, 15)
        self.assertEqual(by_option[5.0].days, 12)
        self.assertEqual(by_option[2.0].finish, date(2026, 11, 21))
        self.assertEqual(by_option[5.0].finish, date(2026, 11, 4))
        self.assertTrue(all(s.feasible for s in plan.scenarios))

    def test_ran_today_starts_tomorrow(self):
        plan = build_plan(make_progress(ran_today=True), make_settings(), TODAY)
        self.assertEqual(plan.available_days, 78)
        self.assertEqual(plan.first_run_day, date(2026, 10, 25))
        self.assertEqual(plan.earliest_finish, date(2026, 11, 5))
        self.assertTrue(any("今天已有有效记录" in w for w in plan.warnings))

    def test_rest_weekdays_reduce_capacity(self):
        plan = build_plan(make_progress(), make_settings(rest_weekdays=frozenset({5, 6})), TODAY)
        self.assertEqual(plan.available_days, 55)
        self.assertEqual(plan.first_run_day, date(2026, 10, 26))
        self.assertAlmostEqual(plan.required_per_day_km, 57.6 / 55, places=3)

    def test_deadline_today_is_tight(self):
        plan = build_plan(make_progress(completed_km=93.0), make_settings(deadline=TODAY), TODAY)
        self.assertEqual(plan.available_days, 1)
        self.assertEqual(plan.min_days, 1)
        self.assertEqual(plan.status, PlanStatus.TIGHT)
        self.assertEqual(plan.earliest_finish, TODAY)
        self.assertEqual(plan.scenarios[3].finish, TODAY)

    def test_deadline_passed(self):
        plan = build_plan(make_progress(), make_settings(deadline=TODAY - timedelta(days=1)), TODAY)
        self.assertEqual(plan.status, PlanStatus.EXPIRED)
        self.assertFalse(plan.feasible)
        self.assertEqual(plan.available_days, 0)

    def test_impossible(self):
        plan = build_plan(
            make_progress(completed_km=0, completed_runs=0),
            make_settings(deadline=TODAY + timedelta(days=5)),
            TODAY,
        )
        self.assertEqual(plan.status, PlanStatus.IMPOSSIBLE)
        self.assertFalse(plan.feasible)
        self.assertEqual(plan.min_days, 20)
        self.assertEqual(plan.available_days, 6)
        self.assertAlmostEqual(plan.max_reachable_km, 30.0)
        self.assertTrue(any("仍差" in w for w in plan.warnings))

    def test_done(self):
        plan = build_plan(make_progress(completed_km=100), make_settings(), TODAY)
        self.assertEqual(plan.status, PlanStatus.DONE)
        self.assertEqual(plan.remaining_km, 0)
        self.assertEqual(plan.progress_ratio, 1.0)
        self.assertEqual(plan.schedule, ())
        self.assertTrue(all(s.days == 0 for s in plan.scenarios))

    def test_min_run_floor(self):
        plan = build_plan(make_progress(completed_km=95.0), make_settings(), TODAY)
        scenario = next(s for s in plan.scenarios if s.per_day_km == 2.0)
        self.assertEqual(scenario.days, 1)
        self.assertEqual(scenario.planned_total_km, 2.0)
        self.assertEqual(plan.schedule[0].km, 2.0)

    def test_all_rest_days(self):
        plan = build_plan(
            make_progress(),
            make_settings(rest_weekdays=frozenset(range(7))),
            TODAY,
        )
        self.assertEqual(plan.available_days, 0)
        self.assertEqual(plan.status, PlanStatus.IMPOSSIBLE)

    def test_required_per_day_below_min_warns(self):
        plan = build_plan(make_progress(), make_settings(), TODAY)
        self.assertTrue(any("至少" in w for w in plan.warnings))

    def test_no_data_warning(self):
        plan = build_plan(Progress(), make_settings(), TODAY)
        self.assertFalse(plan.has_data)
        self.assertTrue(any("尚未获取真实账号数据" in w for w in plan.warnings))


class ScheduleTests(unittest.TestCase):
    def test_schedule_respects_bounds_and_dates(self):
        plan = build_plan(make_progress(), make_settings(), TODAY)
        runs = plan.schedule
        self.assertEqual(len(runs), 12)
        self.assertAlmostEqual(sum(r.km for r in runs), 57.6, places=1)
        self.assertTrue(all(2.0 <= r.km <= 5.0 for r in runs))
        self.assertEqual(runs[0].day, TODAY)
        self.assertEqual(runs[-1].day, date(2026, 11, 4))
        for run in runs:
            self.assertAlmostEqual(run.minutes, run.km * 6.5, places=1)

    def test_schedule_for_slow_option(self):
        plan = build_plan(make_progress(), make_settings(), TODAY)
        runs = schedule_for(plan.remaining_km, plan.available_dates, 2.0, make_settings())
        self.assertEqual(len(runs), 29)
        self.assertTrue(all(abs(r.km - 2.0) < 0.01 for r in runs))
        self.assertEqual(runs[-1].day, date(2026, 11, 21))

    def test_schedule_for_infeasible_returns_empty(self):
        plan = build_plan(
            make_progress(completed_km=0, completed_runs=0),
            make_settings(deadline=TODAY + timedelta(days=3)),
            TODAY,
        )
        self.assertEqual(plan.schedule, ())


class SettingsValidationTests(unittest.TestCase):
    def test_invalid_target(self):
        with self.assertRaises(ValueError):
            PlanSettings(target_km=0, deadline=DEADLINE)

    def test_invalid_bounds(self):
        with self.assertRaises(ValueError):
            PlanSettings(target_km=96, deadline=DEADLINE, min_run_km=6, max_run_km=5)

    def test_invalid_rest_day(self):
        with self.assertRaises(ValueError):
            PlanSettings(target_km=96, deadline=DEADLINE, rest_weekdays=frozenset({7}))

    def test_defaults(self):
        settings = PlanSettings(target_km=96, deadline=DEADLINE)
        self.assertEqual(settings.daily_options, (2.0, 3.0, 4.0, 5.0))
        self.assertEqual(settings.rest_labels, "无")


if __name__ == "__main__":
    unittest.main()
