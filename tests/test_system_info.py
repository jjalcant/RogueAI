import unittest

from tools.system_info import get_system_info, system_info


class SystemInfoTests(unittest.TestCase):
    def test_system_info_returns_verified_machine_fields(self):
        result = system_info()

        self.assertTrue(result["success"])
        self.assertEqual("system_info", result["action"])
        self.assertIn("info", result)
        self.assertIn("Operating System", result["info"])
        self.assertIn("CPU", result["info"])
        self.assertIn("RAM", result["info"])
        self.assertIn("Disk summary", result["info"])
        self.assertTrue(result["info"]["Operating System"])
        self.assertTrue(result["info"]["CPU"])
        self.assertTrue(result["info"]["Disk summary"])

    def test_legacy_get_system_info_alias_remains_available(self):
        result = get_system_info()

        self.assertTrue(result["success"])
        self.assertEqual("get_system_info", result["action"])
        self.assertIn("platform", result["info"])
        self.assertIn("python_version", result["info"])
        self.assertIn("cwd", result["info"])


if __name__ == "__main__":
    unittest.main()
