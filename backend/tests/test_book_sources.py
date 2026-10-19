import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from book_sources import parseGoodreadsBooks, parseStoryGraphBooks, fetchAudiobookshelfBooks, normalizeServerUrl


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.urls.append(url)
        return FakeResponse(self.responses[url.split("/api/")[-1]])


class BookSourceTests(unittest.TestCase):
    def testGoodreadsChangedClasses(self):
        html = '<article class="redesigned"><a href="/book/show/12345-something">Novel</a><a href="/author/show/52">Author</a></article>'
        books = parseGoodreadsBooks(html, "https://www.goodreads.com/review/list/100?shelf=currently-reading")
        self.assertEqual(len(books), 1)
        book = next(iter(books.values()))
        self.assertEqual(book["title"], "Novel")
        self.assertEqual(book["author"], "Author")

    def testStoryGraphChangedClasses(self):
        html = '<article class="new-card"><h3><a href="/books/12345678-abcd">A Book</a></h3><a href="/authors/12">Writer</a></article>'
        books = parseStoryGraphBooks(html, "https://app.thestorygraph.com/currently-reading/user")
        self.assertEqual(len(books), 1)
        self.assertEqual(next(iter(books.values()))["title"], "A Book")

    def testBadServerUrl(self):
        with self.assertRaises(ValueError):
            normalizeServerUrl("file:///private/config")
        with self.assertRaises(ValueError):
            normalizeServerUrl("https://user:password@example.com")

    def testAudiobookshelfActiveSession(self):
        now = int(time.time() * 1000)
        item = {"libraryItemId": "li_123", "userId": "usr_2", "updatedAt": now,
                "displayTitle": "My Audiobook", "displayAuthor": "Book Author"}
        session = FakeSession({
            "users/online": {"openSessions": [item]},
            "users/usr_2/listening-sessions": {"sessions": [item]},
        })
        books, active = fetchAudiobookshelfBooks(session, "https://books.example.org", "apiKey", "usr_2")
        self.assertEqual(active, "abs-li_123")
        self.assertEqual(books[active]["title"], "My Audiobook")

    def testAudiobookshelfHistoryNotLive(self):
        item = {"libraryItemId": "li_old", "userId": "usr_2",
                "updatedAt": int((time.time() - 3600) * 1000),
                "displayTitle": "Past Listening"}
        session = FakeSession({
            "users/online": {"openSessions": []},
            "users/usr_2/listening-sessions": {"sessions": [item]},
        })
        books, active = fetchAudiobookshelfBooks(session, "https://books.example.org", "apiKey", "usr_2")
        self.assertIsNone(active)
        self.assertIn("abs-li_old", books)


if __name__ == "__main__":
    unittest.main()
