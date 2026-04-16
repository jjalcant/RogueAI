import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.storage_overview import storage_overview


class StorageOverviewToolTests(unittest.TestCase):
    def test_storage_overview_returns_verified_folder_and_large_file_data(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            downloads = root / "Downloads"
            desktop = root / "Desktop"
            downloads.mkdir()
            desktop.mkdir()

            (downloads / "movie.bin").write_bytes(b"a" * 256)
            (downloads / "notes.txt").write_text("demo", encoding="utf-8")
            (desktop / "archive.zip").write_bytes(b"b" * 180)

            with patch(
                "tools.storage_overview._get_drive_snapshot",
                return_value={
                    "path": str(root),
                    "total_bytes": 1000,
                    "used_bytes": 600,
                    "free_bytes": 400,
                    "usage_percent": 60.0,
                },
            ):
                payload = storage_overview(
                    scan_roots=[root],
                    drive_path=root,
                    large_file_threshold_bytes=100,
                    top_folder_limit=5,
                    large_file_limit=5,
                    max_scanned_files=1000,
                )

        self.assertTrue(payload["success"])
        self.assertEqual("storage_overview", payload["action"])
        self.assertIn("Drive usage: 60%", payload["observed"])
        self.assertIn("Free space: 400 B", payload["observed"])
        self.assertEqual(["Downloads", "Desktop"], [item["name"] for item in payload["storage"]["largest_folders"][:2]])
        self.assertEqual("movie.bin", payload["storage"]["large_files"][0]["name"])
        self.assertIn("Largest folders: Downloads", payload["inferences"][0])
        self.assertIn("Run Scan Downloads", payload["suggestions"])

    def test_storage_overview_reports_high_disk_usage_warning(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            root.mkdir(exist_ok=True)
            with patch(
                "tools.storage_overview._get_drive_snapshot",
                return_value={
                    "path": str(root),
                    "total_bytes": 1000,
                    "used_bytes": 920,
                    "free_bytes": 80,
                    "usage_percent": 92.0,
                },
            ):
                payload = storage_overview(
                    scan_roots=[root],
                    drive_path=root,
                    large_file_threshold_bytes=100,
                    max_scanned_files=10,
                )

        self.assertTrue(payload["success"])
        self.assertIn("Disk usage is high", payload["warnings"])


if __name__ == "__main__":
    unittest.main()
