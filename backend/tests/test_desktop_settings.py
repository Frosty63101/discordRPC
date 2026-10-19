"""Regression tests for the desktop dashboard's local API and settings."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as backend


class DesktopSettingsTests(unittest.TestCase):
    def testAppearanceAndTraySettingsAreValidated(self):
        original = backend.clampConfigValues({
            "theme": "DARK",
            "platform": "goodreads",
            "minimizeToTray": False,
            "minimizeOnMinimize": True,
            "startOnStartup": True,
            "startByDefault": False,
        })
        self.assertEqual(original["theme"], "dark")
        self.assertTrue(original["minimizeOnMinimize"])
        self.assertFalse(original["minimizeToTray"])
        self.assertEqual(
            backend.clampConfigValues({"theme": "invalid"})["theme"],
            "system",
        )

    def testRecentLogsReturnsLatestFiftyLines(self):
        with tempfile.TemporaryDirectory() as tempDir:
            filePath = Path(tempDir) / "gr_rpc_log.txt"
            filePath.write_text(
                "".join(f"2026-10-19 00:00:00 - INFO - line {lineNumber}\n"
                        for lineNumber in range(1, 71)),
                encoding="utf-8",
            )
            with patch.object(backend, "logPath", str(filePath)):
                client = backend.app.test_client()
                response = client.get("/api/logs?limit=50")
                self.assertEqual(response.status_code, 200)
                lines = response.get_json()["lines"]
                self.assertEqual(len(lines), 50)
                self.assertTrue(lines[0].endswith("line 21"))
                self.assertTrue(lines[-1].endswith("line 70"))

    def testLogTailRespectsBoundsAndMissingFile(self):
        with tempfile.TemporaryDirectory() as tempDir:
            with patch.object(backend, "logPath", str(Path(tempDir) / "missing.txt")):
                client = backend.app.test_client()
                self.assertEqual(client.get("/api/logs").get_json()["lines"], [])
                self.assertEqual(client.get("/api/logs?limit=9999").get_json()["limit"], 200)


if __name__ == "__main__":
    unittest.main()
