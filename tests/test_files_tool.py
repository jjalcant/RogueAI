import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.files_tool import (
    apply_download_organization,
    apply_home_workspace_organization,
    copy_path,
    create_folder,
    delete_path,
    list_path,
    move_path,
    preview_download_organization,
    preview_home_workspace_organization,
    scan_duplicates,
)


class FilesToolTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_create_and_list_folder(self):
        target = self.base / "sample"
        create_response = create_folder(str(target))
        self.assertTrue(create_response["success"])
        self.assertIn("Verified folder exists after create request", create_response["observed"][0])
        self.assertTrue(create_response["artifacts"][0]["exists"])
        list_response = list_path(str(self.base))
        self.assertTrue(list_response["success"])
        self.assertIn("sample", list_response["result"])

    def test_copy_move_and_delete_file(self):
        source = self.base / "a.txt"
        source.write_text("hello", encoding="utf-8")

        copied = self.base / "copy.txt"
        copy_response = copy_path(str(source), str(copied))
        self.assertTrue(copy_response["success"])
        self.assertIn("Verified copied file exists", "\n".join(copy_response["observed"]))
        self.assertTrue(copied.exists())

        moved = self.base / "moved.txt"
        move_response = move_path(str(copied), str(moved))
        self.assertTrue(move_response["success"])
        self.assertIn("Verified target exists after move", "\n".join(move_response["observed"]))
        self.assertTrue(moved.exists())
        self.assertFalse(copied.exists())

        delete_response = delete_path(str(moved))
        self.assertTrue(delete_response["success"])
        self.assertIn("Verified file no longer exists", delete_response["observed"][0])
        self.assertFalse(moved.exists())

    def test_download_scan_preview_reports_categories_and_confirmation(self):
        downloads = self.base / "Downloads"
        downloads.mkdir()
        (downloads / "photo.jpg").write_text("img", encoding="utf-8")
        (downloads / "archive.zip").write_text("zip", encoding="utf-8")
        (downloads / "notes.txt").write_text("doc", encoding="utf-8")

        result = preview_download_organization(str(downloads))
        self.assertTrue(result["success"])
        self.assertEqual("preview_download_organization", result["action"])
        self.assertEqual(3, len(result["items"]))
        self.assertEqual("confirm organize downloads", result["confirmation_phrase"])
        self.assertIn("No files were moved yet.", result["result"])
        self.assertIn("Pictures", result["summary"])
        self.assertIn("Archives", result["summary"])
        self.assertIn("Documents", result["summary"])

    def test_download_apply_moves_into_local_organized_subfolders(self):
        downloads = self.base / "Downloads"
        downloads.mkdir()
        source = downloads / "song.mp3"
        source.write_text("music", encoding="utf-8")

        result = apply_download_organization(str(downloads))
        self.assertTrue(result["success"])
        self.assertFalse(source.exists())
        self.assertEqual(1, len(result["moved"]))
        moved_target = Path(result["moved"][0]["target"])
        self.assertTrue(moved_target.exists())
        self.assertEqual(downloads / "Organized" / "Music", moved_target.parent)
        self.assertIn("Downloads\\Organized", result["result"])

    def test_home_workspace_preview_skips_protected_directories(self):
        home = self.base / "Home"
        home.mkdir()
        (home / "Desktop").mkdir()
        (home / "Documents").mkdir()
        (home / "model.onnx").write_text("weights", encoding="utf-8")
        (home / "notes.txt").write_text("notes", encoding="utf-8")

        result = preview_home_workspace_organization(str(home))
        self.assertTrue(result["success"])
        self.assertEqual("confirm organize home workspace", result["confirmation_phrase"])
        self.assertIn("Desktop", result["skipped_protected"])
        self.assertIn("Documents", result["skipped_protected"])
        self.assertEqual(2, len(result["items"]))
        self.assertIn("Models", result["summary"])
        self.assertIn("Notes", result["summary"])

    def test_home_workspace_apply_moves_only_loose_files(self):
        home = self.base / "Home"
        home.mkdir()
        (home / "Downloads").mkdir()
        config_file = home / ".gitconfig"
        config_file.write_text("[user]", encoding="utf-8")
        loose = home / "scratch.tmp"
        loose.write_text("tmp", encoding="utf-8")

        result = apply_home_workspace_organization(str(home))
        self.assertTrue(result["success"])
        moved_targets = [Path(item["target"]) for item in result["moved"]]
        self.assertEqual(2, len(moved_targets))
        self.assertTrue(any(target.parent == home / "OrganizedWorkspace" / "Configs" for target in moved_targets))
        self.assertTrue(any(target.parent == home / "OrganizedWorkspace" / "Temp" for target in moved_targets))
        self.assertTrue((home / "Downloads").exists())

    def test_scan_duplicates_is_bounded_and_reports_truncation(self):
        duplicates_dir = self.base / "dupes"
        duplicates_dir.mkdir()
        for index in range(5):
            (duplicates_dir / f"file_{index}.txt").write_text("same", encoding="utf-8")

        result = scan_duplicates(str(duplicates_dir), max_files=3)

        self.assertTrue(result["success"])
        self.assertIn("Duplicate scan stopped after 3 files", result["warnings"][0])
        self.assertIn("Scan limit reached after 3 files.", result["result"])


if __name__ == "__main__":
    unittest.main()
