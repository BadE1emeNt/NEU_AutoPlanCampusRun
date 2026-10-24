from __future__ import annotations

import unittest
from datetime import datetime

from campusrun.errors import MappingError
from campusrun.models import FieldMapping
from campusrun.providers.autodetect import (
    describe_result,
    detect,
    looks_like_auth_error,
    summary_from_payload,
)

RECORDS_PAYLOAD = {
    "code": 0,
    "msg": "ok",
    "data": {
        "list": [
            {
                "runId": 1001,
                "runDate": "2026-10-20 19:30:00",
                "distance": 3200,
                "duration": 1200,
                "valid": 1,
            },
            {
                "runId": 1002,
                "runDate": "2026-10-22 20:05:00",
                "distance": 3600,
                "duration": 1350,
                "valid": 1,
            },
        ],
        "totalDistance": 6800,
        "totalCount": 2,
    },
}

AGGREGATE_PAYLOAD = {
    "code": 200,
    "data": {"studentName": "张三", "totalDistance": 96500, "totalRuns": 30},
}

EPOCH_PAYLOAD = {
    "data": {
        "records": [
            {
                "startTime": int(datetime(2026, 10, 18, 19, 0).timestamp() * 1000),
                "mileage": 2.4,
                "runTime": 900,
            }
        ]
    }
}


class DetectionTests(unittest.TestCase):
    def test_records_detection(self):
        detection = detect(RECORDS_PAYLOAD)
        mapping = detection.mapping
        self.assertEqual(mapping.mode, "records")
        self.assertEqual(mapping.records_path, "data.list")
        self.assertEqual(mapping.distance_field, "distance")
        self.assertEqual(mapping.date_field, "runDate")
        self.assertEqual(mapping.duration_field, "duration")
        self.assertEqual(mapping.valid_field, "valid")
        self.assertIn("data.list", detection.notes)

    def test_records_parse(self):
        mapping = detect(RECORDS_PAYLOAD).mapping
        summary = summary_from_payload(RECORDS_PAYLOAD, mapping)
        self.assertEqual(summary.completed_runs, 2)
        self.assertAlmostEqual(summary.completed_km, 6.8)
        self.assertEqual(summary.records[0].day.isoformat(), "2026-10-20")
        self.assertEqual(summary.records[0].duration_sec, 1200)

    def test_aggregate_detection(self):
        detection = detect(AGGREGATE_PAYLOAD)
        mapping = detection.mapping
        self.assertEqual(mapping.mode, "aggregate")
        self.assertEqual(mapping.total_distance_path, "data.totalDistance")
        self.assertEqual(mapping.total_runs_path, "data.totalRuns")
        summary = summary_from_payload(AGGREGATE_PAYLOAD, mapping)
        self.assertAlmostEqual(summary.completed_km, 96.5)
        self.assertEqual(summary.completed_runs, 30)

    def test_epoch_and_alt_keys(self):
        detection = detect(EPOCH_PAYLOAD)
        self.assertEqual(detection.mapping.records_path, "data.records")
        self.assertEqual(detection.mapping.distance_field, "mileage")
        self.assertEqual(detection.mapping.duration_field, "runTime")
        summary = summary_from_payload(EPOCH_PAYLOAD, detection.mapping)
        self.assertEqual(summary.completed_runs, 1)
        self.assertAlmostEqual(summary.completed_km, 2.4)
        self.assertEqual(summary.records[0].day.year, 2026)

    def test_empty_list_is_zero(self):
        payload = {"data": {"records": []}}
        detection = detect(payload)
        self.assertEqual(detection.mapping.records_path, "data.records")
        summary = summary_from_payload(payload, detection.mapping)
        self.assertEqual(summary.completed_km, 0)
        self.assertEqual(summary.completed_runs, 0)

    def test_invalid_records_are_skipped(self):
        payload = {
            "data": {
                "list": [
                    {"date": "2026-10-20", "distance": 2.5, "valid": 1},
                    {"date": "2026-10-21", "distance": 0, "valid": 1},
                ]
            }
        }
        mapping = detect(payload).mapping
        summary = summary_from_payload(payload, mapping)
        self.assertEqual(summary.completed_runs, 1)
        self.assertAlmostEqual(summary.completed_km, 2.5)

    def test_best_per_day_dedup(self):
        payload = {
            "data": {
                "list": [
                    {"date": "2026-10-20", "distance": 2.0},
                    {"date": "2026-10-20", "distance": 4.0},
                ]
            }
        }
        mapping = detect(payload).mapping
        summary = summary_from_payload(payload, mapping)
        self.assertEqual(summary.completed_runs, 1)
        self.assertAlmostEqual(summary.completed_km, 4.0)

    def test_unmappable_payload(self):
        with self.assertRaises(MappingError):
            detect({"code": 0, "msg": "ok"})

    def test_mapping_mismatch(self):
        mapping = FieldMapping(mode="records", records_path="data.list", date_field="missing", distance_field="distance")
        with self.assertRaises(MappingError):
            summary_from_payload(RECORDS_PAYLOAD, mapping)

    def test_auth_error(self):
        self.assertIsNotNone(looks_like_auth_error({"code": 401, "msg": "未登录"}))
        self.assertIsNone(looks_like_auth_error({"code": 0, "msg": "ok"}))
        with self.assertRaises(Exception):
            summary_from_payload({"code": 403, "msg": "禁止访问"}, FieldMapping())

    def test_describe_result(self):
        mapping = detect(RECORDS_PAYLOAD).mapping
        text = describe_result(RECORDS_PAYLOAD, mapping)
        self.assertIn("2 次", text)
        self.assertIn("6.80 km", text)


if __name__ == "__main__":
    unittest.main()
