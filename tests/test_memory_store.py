import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import memory_store


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store_file = Path(self.tempdir.name) / "saved_notes.json"
        self.recent_store_file = Path(self.tempdir.name) / "recent_memory.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_save_get_delete_note(self):
        with patch.object(memory_store, "STORE_FILE", self.store_file), \
             patch.object(memory_store, "MEMORY_DIR", self.store_file.parent):
            save_result = memory_store.save_note("main project", "RogueAI")
            self.assertTrue(save_result["success"])

            get_result = memory_store.get_note("main project")
            self.assertTrue(get_result["success"])
            self.assertIn("RogueAI", get_result["result"])

            delete_result = memory_store.delete_note("main project")
            self.assertTrue(delete_result["success"])

            missing_result = memory_store.get_note("main project")
            self.assertFalse(missing_result["success"])

    def test_memory_persistence(self):
        with patch.object(memory_store, "STORE_FILE", self.store_file), \
             patch.object(memory_store, "MEMORY_DIR", self.store_file.parent):
            memory_store.save_note("main project", "RogueAI")

        with patch.object(memory_store, "STORE_FILE", self.store_file), \
             patch.object(memory_store, "MEMORY_DIR", self.store_file.parent):
            list_result = memory_store.list_notes()
        self.assertTrue(list_result["success"])
        self.assertIn("main project", list_result["result"])

    def test_recent_actions_are_logged_and_retrievable(self):
        with patch.object(memory_store, "STORE_FILE", self.store_file), \
             patch.object(memory_store, "RECENT_STORE_FILE", self.recent_store_file), \
             patch.object(memory_store, "MEMORY_DIR", self.store_file.parent):
            log_result = memory_store.log("scan desktop completed")
            recent_result = memory_store.get_recent_actions()

        self.assertTrue(log_result["success"])
        self.assertTrue(recent_result["success"])
        self.assertIn("scan desktop completed", recent_result["result"])
        self.assertEqual("scan desktop completed", recent_result["actions"][0]["text"])

    def test_recent_commands_are_logged_and_persisted(self):
        with patch.object(memory_store, "STORE_FILE", self.store_file), \
             patch.object(memory_store, "RECENT_STORE_FILE", self.recent_store_file), \
             patch.object(memory_store, "MEMORY_DIR", self.store_file.parent):
            memory_store.log_command("scan desktop")

        with patch.object(memory_store, "STORE_FILE", self.store_file), \
             patch.object(memory_store, "RECENT_STORE_FILE", self.recent_store_file), \
             patch.object(memory_store, "MEMORY_DIR", self.store_file.parent):
            recent_commands = memory_store.get_recent_commands()

        self.assertTrue(recent_commands["success"])
        self.assertEqual("scan desktop", recent_commands["commands"][0]["text"])
        self.assertIn("scan desktop", recent_commands["result"])


if __name__ == "__main__":
    unittest.main()
