import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from brain.sensor import RogueSensor


class RogueSensorTests(unittest.TestCase):
    def test_collect_state_reports_download_file_counts_size_and_recent_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            downloads = Path(tempdir) / "Downloads"
            downloads.mkdir()

            old_file = downloads / "old.txt"
            recent_file = downloads / "recent.txt"
            old_file.write_text("abc", encoding="utf-8")
            recent_file.write_text("abcdef", encoding="utf-8")

            now = datetime(2026, 4, 10, 12, 0, 0)
            old_time = (now - timedelta(hours=3)).timestamp()
            recent_time = (now - timedelta(minutes=10)).timestamp()
            os.utime(old_file, (old_time, old_time))
            os.utime(recent_file, (recent_time, recent_time))

            sensor = RogueSensor(
                downloads_path=downloads,
                recent_window_seconds=3600,
                max_recent_files=5,
                clock=lambda: now,
            )

            state = sensor.collect_state()

            self.assertEqual(str(downloads), state["downloads"]["path"])
            self.assertEqual(2, state["downloads"]["file_count"])
            self.assertEqual(9, state["downloads"]["total_size_bytes"])
            self.assertEqual(1, state["downloads"]["recent_file_count"])
            self.assertEqual("recent.txt", state["downloads"]["recent_files"][0]["name"])


if __name__ == "__main__":
    unittest.main()
