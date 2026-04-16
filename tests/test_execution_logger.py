import json
import tempfile
import unittest
from pathlib import Path

from execution_logger import ExecutionLogger


class ExecutionLoggerTests(unittest.TestCase):
    def test_logger_writes_json_line(self):
        with tempfile.TemporaryDirectory() as tempdir:
            log_file = Path(tempdir) / "agent.log"
            logger = ExecutionLogger(log_file)
            logger.log("task_started", task_id=1)

            payload = json.loads(log_file.read_text(encoding="utf-8").strip())
            self.assertEqual("task_started", payload["event"])
            self.assertEqual(1, payload["details"]["task_id"])


if __name__ == "__main__":
    unittest.main()
