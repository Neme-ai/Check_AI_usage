import tempfile
import unittest
from pathlib import Path

from usage_core import countdown, is_stale, load_cache, timestamp, write_json


class UsageTests(unittest.TestCase):
    def test_timestamp_requires_timezone_and_seconds(self):
        self.assertIsNone(timestamp("2030-01-01T00:00:00"))
        self.assertIsNone(timestamp(1900000000000))
        self.assertEqual(timestamp("2030-01-01T08:00:00+08:00"), timestamp("2030-01-01T00:00:00Z"))

    def test_expiry_never_infers_replenishment(self):
        state = {"status": "正常", "updated_at": 999, "windows": [{"reset_at": 1000}]}
        self.assertFalse(is_stale(state, 999))
        self.assertTrue(is_stale(state, 1000))
        self.assertIn("待刷新", countdown(1000, 1001))
        state["windows"] = []
        self.assertTrue(is_stale(state, 1150))

    def test_cache_validates_and_recalculates_remaining(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.json"
            write_json(path, {"codex": {"windows": [{"used": 20, "remaining": 999, "label": "每周"}], "updated_at": 1000}})
            state = load_cache(path)
            self.assertEqual(state["codex"]["windows"][0]["remaining"], 80)
            self.assertTrue(is_stale(state["codex"], 1001))
            path.write_text("broken")
            self.assertEqual(load_cache(path)["codex"]["windows"], [])


if __name__ == "__main__":
    unittest.main()
