import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

import rogue_app


class RogueLauncherTests(unittest.TestCase):
    def test_launch_desktop_prefers_qt_when_available(self):
        with patch("rogue_app._import_qt_launcher", return_value=lambda: "qt"), patch(
            "rogue_app._launch_legacy_tk_app",
            return_value="tk",
        ):
            result = rogue_app.launch_desktop_app(prefer_qt=True)

        self.assertEqual("qt", result)

    def test_launch_desktop_falls_back_to_tk_when_pyside6_missing(self):
        missing = ModuleNotFoundError("No module named 'PySide6'")
        missing.name = "PySide6"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with patch("rogue_app._import_qt_launcher", side_effect=missing), patch(
                "rogue_app._launch_legacy_tk_app",
                return_value="tk",
            ):
                result = rogue_app.launch_desktop_app(prefer_qt=True)

        self.assertEqual("tk", result)
        self.assertIn("PySide6 import failed", stdout.getvalue())
        self.assertIn("Falling back to the legacy Tkinter desktop", stdout.getvalue())

    def test_launch_desktop_does_not_mask_non_pyside_module_errors(self):
        missing = ModuleNotFoundError("No module named 'brain.llm_bridge'")
        missing.name = "brain.llm_bridge"

        with patch("rogue_app._import_qt_launcher", side_effect=missing):
            with self.assertRaises(ModuleNotFoundError):
                rogue_app.launch_desktop_app(prefer_qt=True)

    def test_launch_desktop_surfaces_qt_startup_errors(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with patch(
                "rogue_app._import_qt_launcher",
                return_value=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            ):
                with self.assertRaises(RuntimeError):
                    rogue_app.launch_desktop_app(prefer_qt=True)

        self.assertIn("PySide6 startup failed: RuntimeError: boom", stdout.getvalue())

    def test_start_batch_prefers_interpreter_that_can_import_qt_launcher(self):
        text = Path("start_rogue.bat").read_text(encoding="utf-8")

        self.assertIn("from ui_qt.main_window import launch_qt_app", text)
        self.assertIn("Using active Python because .venv cannot import the PySide6 launcher.", text)


if __name__ == "__main__":
    unittest.main()
