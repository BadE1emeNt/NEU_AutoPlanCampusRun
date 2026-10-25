from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from campusrun.elevation import ensure_elevated, is_admin


class ElevationTests(unittest.TestCase):
    def test_admin_check_returns_bool(self):
        self.assertIsInstance(is_admin(), bool)

    def test_no_elevate_bypass(self):
        with patch.dict(os.environ, {"CAMPUSRUN_NO_ELEVATE": "1"}):
            self.assertTrue(ensure_elevated())


if __name__ == "__main__":
    unittest.main()
