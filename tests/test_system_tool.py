import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.system_tool import open_application, open_folder, run_shell_command


class SystemToolTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_open_folder_works(self):
        folder = self.base / "example"
        folder.mkdir()
        with patch("tools.system_tool._start_path") as start_path:
            result = open_folder(str(folder))
        self.assertTrue(result["success"])
        self.assertEqual("open_folder", result["action"])
        self.assertIn("I cannot confirm", "\n".join(result["warnings"]))
        start_path.assert_called_once()

    def test_open_downloads_folder_alias(self):
        with patch("tools.system_tool._start_path") as start_path:
            result = open_folder("download folder")
        self.assertTrue(result["success"])
        self.assertEqual("open_folder", result["action"])
        start_path.assert_called_once()

    def test_open_desktop_alias(self):
        with patch("tools.system_tool._start_path") as start_path:
            result = open_folder("my desktop")
        self.assertTrue(result["success"])
        self.assertEqual("open_folder", result["action"])
        start_path.assert_called_once()

    def test_open_notepad_alias(self):
        with patch("tools.system_tool._spawn_process") as spawn_process:
            result = open_application("notepad")
        self.assertTrue(result["success"])
        self.assertEqual("open_application", result["action"])
        spawn_process.assert_called_once_with(["notepad.exe"])

    def test_open_calculator_alias(self):
        with patch("tools.system_tool._spawn_process") as spawn_process:
            result = open_application("calculator")
        self.assertTrue(result["success"])
        self.assertEqual("open_application", result["action"])
        spawn_process.assert_called_once_with(["calc.exe"])

    def test_unknown_application_alias_fails_cleanly(self):
        with patch("tools.system_tool._spawn_process", side_effect=FileNotFoundError):
            result = open_application("unknown app alias")
        self.assertFalse(result["success"])
        self.assertEqual("open_application", result["action"])
        self.assertIn("not found", result["error"].lower())

    def test_run_shell_command_returns_output(self):
        result = run_shell_command("cmd /c echo hello")
        self.assertTrue(result["success"])
        self.assertEqual("run_shell_command", result["action"])
        self.assertIn("hello", result.get("stdout", "").lower())
        self.assertIn("Command exit code", "\n".join(result["observed"]))

    def test_run_shell_command_without_stdout_reports_missing_output_clearly(self):
        result = run_shell_command("cmd /c exit 0")
        self.assertTrue(result["success"])
        self.assertIn("exited with code 0", result["result"].lower())
        self.assertIn("No stdout was returned.", result["warnings"])
        self.assertNotIn("Command executed.", result["result"])

    def test_dangerous_commands_are_blocked(self):
        result = run_shell_command("rm -rf /")
        self.assertFalse(result["success"])
        self.assertEqual("run_shell_command", result["action"])
        self.assertIn("blocked", result["error"].lower())


if __name__ == "__main__":
    unittest.main()
