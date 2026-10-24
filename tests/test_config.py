from __future__ import annotations

import unittest
from datetime import date, datetime
from pathlib import Path

from . import workspace_tmp
from campusrun.analysis import PlanSettings
from campusrun.config import AppConfig, AppPaths, ConnectionStore, SummaryCache, default_deadline
from campusrun.errors import ConfigError, ProviderError
from campusrun.models import CapturedRequest, FieldMapping, HttpConnection, RunRecord, RunSummary
from campusrun.secrets import available as dpapi_available
from campusrun.service import CampusRunService


class ConfigTests(unittest.TestCase):
    def test_roundtrip(self):
        with workspace_tmp() as tmp:
            paths = AppPaths(Path(tmp))
            config = AppConfig(
                target_km=80,
                deadline=date(2026, 12, 31),
                rest_weekdays=[5, 6],
                pace_min_per_km=6.0,
                demo_mode=False,
                onboarding_seen=True,
            )
            config.save(paths)
            loaded = AppConfig.load(paths)
            self.assertEqual(loaded.target_km, 80)
            self.assertEqual(loaded.deadline, date(2026, 12, 31))
            self.assertEqual(loaded.rest_weekdays, [5, 6])
            self.assertFalse(loaded.demo_mode)
            self.assertTrue(loaded.onboarding_seen)
            self.assertEqual(loaded.to_plan_settings().rest_weekdays, frozenset({5, 6}))

    def test_missing_uses_defaults(self):
        with workspace_tmp() as tmp:
            loaded = AppConfig.load(AppPaths(Path(tmp)))
            self.assertEqual(loaded.target_km, 96)
            self.assertTrue(loaded.demo_mode)
            self.assertFalse(loaded.onboarding_seen)

    def test_corrupt_raises(self):
        with workspace_tmp() as tmp:
            paths = AppPaths(Path(tmp))
            paths.config_file.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ConfigError):
                AppConfig.load(paths)

    def test_invalid_target(self):
        with self.assertRaises(ConfigError):
            AppConfig.from_dict({"target_km": -1})

    def test_default_deadline(self):
        self.assertEqual(default_deadline(date(2026, 1, 5)), date(2026, 1, 10))
        self.assertEqual(default_deadline(date(2026, 4, 1)), date(2026, 6, 30))
        self.assertEqual(default_deadline(date(2026, 9, 1)), date(2027, 1, 10))

    def test_to_plan_settings(self):
        settings = AppConfig(target_km=50, deadline=date(2026, 12, 1)).to_plan_settings()
        self.assertIsInstance(settings, PlanSettings)
        self.assertEqual(settings.target_km, 50)


class ConnectionStoreTests(unittest.TestCase):
    def test_roundtrip(self):
        with workspace_tmp() as tmp:
            paths = AppPaths(Path(tmp))
            store = ConnectionStore(paths)
            request = CapturedRequest(
                method="POST",
                url="https://example.edu/api/run/list",
                headers={"Authorization": "Bearer secret-token", "Content-Type": "application/json"},
                body='{"page":1}',
            )
            mapping = FieldMapping(records_path="data.list", date_field="runDate", distance_field="distance")
            saved_secure = store.save(HttpConnection(request=request, mapping=mapping))
            self.assertTrue(store.exists())
            self.assertEqual(saved_secure, dpapi_available())
            loaded = store.load()
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.request.url, request.url)
            self.assertEqual(loaded.request.headers["Authorization"], "Bearer secret-token")
            self.assertEqual(loaded.mapping.records_path, "data.list")
            self.assertEqual(loaded.mapping.date_field, "runDate")
            if saved_secure:
                raw = paths.connection_file.read_bytes()
                self.assertTrue(raw.startswith(b"CRDP1\n"))
                self.assertNotIn(b"secret-token", raw)
            store.clear()
            self.assertIsNone(store.load())

    def test_corrupt_connection(self):
        with workspace_tmp() as tmp:
            paths = AppPaths(Path(tmp))
            paths.connection_file.write_bytes(b"????")
            with self.assertRaises(ConfigError):
                ConnectionStore(paths).load()


class SummaryCacheTests(unittest.TestCase):
    def test_roundtrip(self):
        with workspace_tmp() as tmp:
            paths = AppPaths(Path(tmp))
            summary = RunSummary(
                fetched_at=datetime(2026, 10, 24, 21, 0, 0),
                provider="测试接口",
                records=[
                    RunRecord(day=date(2026, 10, 22), distance_km=3.2, duration_sec=1230, valid=True, run_id="1")
                ],
                count_mode="best_per_day",
            )
            cache = SummaryCache(paths)
            cache.save(summary)
            loaded = cache.load()
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.completed_km, 3.2)
            self.assertEqual(loaded.records[0].run_id, "1")
            self.assertEqual(loaded.fetched_at.hour, 21)


class ServiceTests(unittest.TestCase):
    def test_demo_and_plan(self):
        with workspace_tmp() as tmp:
            service = CampusRunService(AppPaths(Path(tmp)))
            self.assertTrue(service.is_demo)
            self.assertIsNotNone(service.summary)
            assert service.summary is not None
            self.assertAlmostEqual(service.summary.completed_km, 38.4)
            plan = service.plan()
            self.assertEqual(plan.target_km, 96)
            self.assertAlmostEqual(plan.completed_km, 38.4)
            self.assertTrue(plan.has_data)

    def test_update_config(self):
        with workspace_tmp() as tmp:
            paths = AppPaths(Path(tmp))
            service = CampusRunService(paths)
            service.update_config(target_km=120, deadline=date(2026, 12, 1))
            self.assertEqual(service.plan().target_km, 120)
            reloaded = AppConfig.load(paths)
            self.assertEqual(reloaded.target_km, 120)

    def test_refresh_without_connection(self):
        with workspace_tmp() as tmp:
            service = CampusRunService(AppPaths(Path(tmp)))
            service.set_demo_mode(False)
            with self.assertRaises(ProviderError):
                service.refresh()

    def test_export_csv(self):
        with workspace_tmp() as tmp:
            service = CampusRunService(AppPaths(Path(tmp)))
            path = service.export_csv()
            text = path.read_text(encoding="utf-8-sig")
            self.assertIn("日期", text)
            self.assertGreater(len(text.splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
