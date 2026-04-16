import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import move_history


class MoveHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.memory_dir = self.base / "memory"
        self.logs_dir = self.base / "logs"
        self.store_file = self.memory_dir / "file_move_history.json"

        self.patches = [
            patch.object(move_history, "MEMORY_DIR", self.memory_dir),
            patch.object(move_history, "STORE_FILE", self.store_file),
            patch.object(move_history, "LOGS", self.logs_dir),
            patch.object(move_history, "LOG_FILE", self.logs_dir / "brain.log"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tempdir.cleanup()

    def test_move_history_persists_and_last_move_can_be_read(self):
        entries = move_history.make_history_entries(
            "downloads",
            "downloads-abc123",
            [
                {
                    "source": r"C:\Users\Test\Downloads\report.pdf",
                    "target": r"C:\Users\Test\Downloads\Organized\Documents\report.pdf",
                    "category": "Documents",
                }
            ],
        )
        record_result = move_history.record_moves(entries)
        self.assertTrue(record_result["success"])
        self.assertTrue(self.store_file.exists())

        last_move = move_history.get_last_move()
        self.assertTrue(last_move["success"])
        self.assertIn("report.pdf", last_move["result"])

    def test_find_move_by_name_returns_matching_destination(self):
        entries = move_history.make_history_entries(
            "downloads",
            "downloads-abc123",
            [
                {
                    "source": r"C:\Users\Test\Downloads\archive.zip",
                    "target": r"C:\Users\Test\Downloads\Organized\Archives\archive.zip",
                    "category": "Archives",
                }
            ],
        )
        move_history.record_moves(entries)

        lookup = move_history.find_move_by_name("archive.zip")
        self.assertTrue(lookup["success"])
        self.assertIn("Organized\\Archives\\archive.zip", lookup["result"])


if __name__ == "__main__":
    unittest.main()
