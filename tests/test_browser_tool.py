import unittest
from unittest.mock import patch

from tools.browser_tool import open_search, open_url


class BrowserToolTests(unittest.TestCase):
    def test_open_url_accepts_known_alias(self):
        with patch("tools.browser_tool.webbrowser.open") as web_open:
            result = open_url("google")
        self.assertTrue(result["success"])
        self.assertEqual("open_url", result["action"])
        web_open.assert_called_once()

    def test_open_search_builds_query_url(self):
        with patch("tools.browser_tool.webbrowser.open") as web_open:
            result = open_search("python tkinter docs")
        self.assertTrue(result["success"])
        self.assertEqual("open_search", result["action"])
        self.assertIn("python tkinter docs", result["result"])
        web_open.assert_called_once()

    def test_open_url_fails_gracefully_on_malformed_input(self):
        result = open_url("not a url%%%")
        self.assertFalse(result["success"])
        self.assertEqual("open_url", result["action"])
        self.assertIn("malformed", result["error"].lower())


if __name__ == "__main__":
    unittest.main()
