import tempfile
import unittest
from pathlib import Path

from status_reporter import StatusReporter


class StatusReporterTests(unittest.TestCase):
    def test_status_reporter_updates_markdown_sections(self):
        with tempfile.TemporaryDirectory() as tempdir:
            status_file = Path(tempdir) / "STATUS.md"
            reporter = StatusReporter(status_file)
            reporter.add_remaining("Implement planner")
            reporter.add_completed("Implement planner")
            reporter.add_validation("Planner tests passed")

            text = status_file.read_text(encoding="utf-8")
            self.assertIn("Implement planner", text)
            self.assertIn("Planner tests passed", text)


if __name__ == "__main__":
    unittest.main()
