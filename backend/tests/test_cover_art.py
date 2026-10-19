import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cover_art import (
    BookCoverResolver, DEFAULT_COVER_ASSET, matchBook,
    safePublicImageUrl, bookIsbn,
)


class FakeResponse:
    def __init__(self, statusCode=200, contentType="image/jpeg", headers=None, body=None):
        self.status_code = statusCode
        self.headers = {"Content-Type": contentType, **(headers or {})}
        self.body = body
        self.closed = False

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ValueError(f"HTTP {self.status_code}")

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, imageResponses=None, searchResults=None):
        self.imageResponses = imageResponses or {}
        self.searchResults = searchResults or []
        self.calls = []
        self.searches = 0

    def head(self, url, timeout=None, allow_redirects=None):
        self.calls.append(("HEAD", url))
        return self.imageResponses.get(url, FakeResponse(404))

    def get(self, url, timeout=None, allow_redirects=None, stream=False, params=None):
        self.calls.append(("GET", url))
        if url == "https://openlibrary.org/search.json":
            self.searches += 1
            return FakeResponse(contentType="application/json", body={"docs": self.searchResults})
        return self.imageResponses.get(url, FakeResponse(404))


class BookCoverTests(unittest.TestCase):
    def testSourceCoverIsUsed(self):
        url = "https://images.gr-assets.com/books/12345.jpg"
        session = FakeSession(imageResponses={url: FakeResponse()})
        resolver = BookCoverResolver(session)
        self.assertEqual(
            resolver.resolve({"platform": "goodreads", "coverArt": url,
                              "title": "Example", "author": "A Writer"}),
            url,
        )
        self.assertEqual(session.searches, 0)

    def testPrivateAudiobookshelfCoverUsesPublicIsbn(self):
        publicCover = "https://covers.openlibrary.org/b/isbn/9780385533225-L.jpg?default=false"
        session = FakeSession(imageResponses={
            "https://books.example.com/api/items/123/cover": FakeResponse(401),
            publicCover: FakeResponse(),
        })
        resolver = BookCoverResolver(session)
        result = resolver.resolve({
            "platform": "audiobookshelf", "title": "Example", "author": "A Writer",
            "coverArt": "https://books.example.com/api/items/123/cover",
            "coverIsbn": "9780385533225",
        })
        self.assertEqual(result, publicCover)
        self.assertEqual(session.searches, 0)

    def testSearchForCoverWhenNoneProvided(self):
        publicCover = "https://covers.openlibrary.org/b/id/98765-L.jpg"
        session = FakeSession(
            imageResponses={publicCover: FakeResponse()},
            searchResults=[
                {"title": "Another Book", "author_name": ["Other Author"], "cover_i": 123},
                {"title": "The Test Book", "author_name": ["A. Writer"], "cover_i": 98765},
            ],
        )
        resolver = BookCoverResolver(session)
        book = {"platform": "audiobookshelf", "title": "The Test Book", "author": "A Writer"}
        self.assertEqual(resolver.resolve(book), publicCover)
        self.assertEqual(resolver.resolve(book), publicCover)
        self.assertEqual(session.searches, 1)

    def testFallbackIfUnavailable(self):
        resolver = BookCoverResolver(FakeSession())
        self.assertEqual(resolver.resolve({"title": "Unknown Title"}), DEFAULT_COVER_ASSET)

    def testRejectCredentialsAndInternalUrls(self):
        self.assertIsNone(safePublicImageUrl("https://example.com/cover.jpg?api_key=SECRET"))
        self.assertIsNone(safePublicImageUrl("http://127.0.0.1:13378/api/items/1/cover"))
        self.assertIsNone(safePublicImageUrl("https://192.168.1.20/cover.png"))
        self.assertIsNone(safePublicImageUrl("https://user:password@example.com/image.jpg"))
        self.assertIsNone(safePublicImageUrl("https://books.local/cover.jpg"))

    def testSecureRedirectValidation(self):
        firstUrl = "https://cover-provider.example/cover.jpg"
        session = FakeSession(imageResponses={
            firstUrl: FakeResponse(302, headers={"Location": "http://127.0.0.1/secret"}),
        })
        resolver = BookCoverResolver(session)
        self.assertIsNone(resolver._availableImage(firstUrl))
        self.assertEqual(len(session.calls), 1)

    def testIsbnValidation(self):
        self.assertEqual(bookIsbn({"isbn": "978-0-385-53322-5"}), "9780385533225")
        self.assertIsNone(bookIsbn({"isbn": "sg-a-book-id"}))

    def testAuthorAndTitleMatchingPreventsWrongCover(self):
        self.assertTrue(matchBook(
            {"title": "The Test Book", "author_name": ["A. Writer"]},
            "The Test Book", "A Writer",
        ))
        self.assertFalse(matchBook(
            {"title": "The Test Book", "author_name": ["Unrelated Person"]},
            "The Test Book", "A Writer",
        ))
        self.assertFalse(matchBook(
            {"title": "Completely Different Book", "author_name": ["A Writer"]},
            "The Test Book", "A Writer",
        ))

    def testRejectNonImageResponse(self):
        url = "https://public.example.com/cover.png"
        resolver = BookCoverResolver(FakeSession(imageResponses={
            url: FakeResponse(200, "text/html"),
        }))
        self.assertIsNone(resolver._availableImage(url))


if __name__ == "__main__":
    unittest.main()
