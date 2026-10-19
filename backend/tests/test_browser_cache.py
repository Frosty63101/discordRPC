"""Playwright bundled-browser cache regression tests."""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import ensurePlaywrightBrowserCache


class BrowserCacheTests(unittest.TestCase):
    def testCacheRefreshOnDifferentBrowserArchive(self):
        with tempfile.TemporaryDirectory() as root:
            cacheRoot = Path(root) / "cache"
            archive = Path(root) / "browser.zip"
            binaryPath = "chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe"

            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr(binaryPath, "version1")
            browserDir = Path(ensurePlaywrightBrowserCache(str(archive), str(cacheRoot)))
            self.assertEqual((browserDir / binaryPath).read_text(), "version1")

            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr(binaryPath, "version2")
            ensurePlaywrightBrowserCache(str(archive), str(cacheRoot))
            self.assertEqual((browserDir / binaryPath).read_text(), "version2")

            (browserDir / binaryPath).unlink()
            ensurePlaywrightBrowserCache(str(archive), str(cacheRoot))
            self.assertEqual((browserDir / binaryPath).read_text(), "version2")

    def testArchiveMissingBrowserIsRejected(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / "empty.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("readme.txt", "missing executable")
            with self.assertRaisesRegex(RuntimeError, "no Chromium"):
                ensurePlaywrightBrowserCache(str(archive), str(Path(root) / "cache"))


if __name__ == "__main__":
    unittest.main()
