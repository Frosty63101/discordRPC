"""Resolve publicly accessible cover images for Discord Rich Presence.

Discord fetches external art without the user's browser cookies or API token.
Never send authenticated, local-network, or credential-bearing URLs to Discord.
"""
import ipaddress
import re
import threading
import time
import unicodedata
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

import requests


DEFAULT_COVER_ASSET = "book"
COVER_CACHE_SECONDS = 6 * 60 * 60
MAX_IMAGE_BYTES = 15 * 1024 * 1024
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif", "image/avif")
SENSITIVE_QUERY_KEYS = (
    "token", "apikey", "api_key", "api-key", "key", "auth", "secret",
    "password", "signature", "sig", "session", "jwt", "credential",
)
HTTPS_UPGRADE_HOSTS = (
    "images.gr-assets.com", "i.gr-assets.com",
    "covers.openlibrary.org", "cdn.thestorygraph.com",
)


def safePublicImageUrl(candidate):
    """Only return a remote HTTPS URL free of secret-looking parameters."""
    if not isinstance(candidate, str) or not candidate.strip() or len(candidate) > 1800:
        return None
    url = candidate.strip()
    try:
        parts = urlsplit(url)
        if parts.scheme == "http" and (parts.hostname or "").lower() in HTTPS_UPGRADE_HOSTS:
            parts = parts._replace(scheme="https")
            url = urlunsplit(parts)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            return None
        hostname = parts.hostname.rstrip(".").lower()
        if (hostname == "localhost" or hostname.endswith((".localhost", ".local", ".lan", ".internal"))
                or "." not in hostname):
            return None
        try:
            ipValue = ipaddress.ip_address(hostname)
            if not ipValue.is_global:
                return None
        except ValueError:
            pass
        if any(any(secret in key.lower() for secret in SENSITIVE_QUERY_KEYS)
               for key, _ in parse_qsl(parts.query, keep_blank_values=True)):
            return None
        if parts.fragment:
            parts = parts._replace(fragment="")
            url = urlunsplit(parts)
        return url
    except ValueError:
        return None


def normalizedText(value):
    plain = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", plain.lower()))


def matchBook(doc, title, author):
    resultTitle = normalizedText(doc.get("title"))
    searchTitle = normalizedText(title)
    if not resultTitle or not searchTitle:
        return False
    # Allow edition/subtitle differences, not unrelated keyword matches.
    if resultTitle != searchTitle:
        shorter, longer = sorted((resultTitle, searchTitle), key=len)
        if len(shorter) < 8 or len(shorter) / max(len(longer), 1) < 0.60:
            return False
        if not longer.startswith(shorter + " "):
            return False

    authorName = normalizedText(author)
    if authorName and authorName != "unknown author":
        foundAuthors = doc.get("author_name") or []
        if not isinstance(foundAuthors, list):
            foundAuthors = [foundAuthors]
        # At minimum the last name should agree before presenting a cover.
        surname = authorName.split()[-1]
        if not any(surname in normalizedText(name).split() for name in foundAuthors):
            return False
    return True


def bookIsbn(book):
    for key in ("coverIsbn", "isbn13", "isbn10", "isbn"):
        raw = re.sub(r"[-\s]", "", str(book.get(key) or ""))
        if re.fullmatch(r"(?:[0-9]{13}|[0-9]{9}[0-9Xx])", raw):
            return raw.upper()
    return None


class BookCoverResolver:
    def __init__(self, httpSession=None):
        self.httpSession = httpSession if httpSession is not None else requests.Session()
        self._cache = {}
        self._cacheLock = threading.Lock()

    def _availableImage(self, candidate):
        url = safePublicImageUrl(candidate)
        if not url:
            return None

        # A manual redirect chain checks *every* destination; never hand an
        # auth redirect or a private-network URL to Discord.
        method = "HEAD"
        for _ in range(5):
            response = None
            try:
                if method == "HEAD":
                    response = self.httpSession.head(url, timeout=6, allow_redirects=False)
                else:
                    response = self.httpSession.get(url, timeout=6, allow_redirects=False, stream=True)

                status = response.status_code
                if status in (301, 302, 303, 307, 308):
                    nextUrl = safePublicImageUrl(urljoin(url, response.headers.get("Location", "")))
                    if not nextUrl:
                        return None
                    url = nextUrl
                    continue

                if method == "HEAD" and status in (403, 405, 501):
                    method = "GET"
                    continue

                if status != 200:
                    return None

                contentType = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if contentType not in IMAGE_TYPES:
                    return None
                try:
                    contentLength = int(response.headers.get("Content-Length", "0"))
                except (ValueError, TypeError):
                    contentLength = 0
                if contentLength > MAX_IMAGE_BYTES:
                    return None
                return url
            except (requests.RequestException, OSError, ValueError):
                return None
            finally:
                if response is not None:
                    response.close()
        return None

    def _searchOpenLibrary(self, book):
        title = str(book.get("title") or "").strip()
        author = str(book.get("author") or "").strip()
        if not title or title.lower() == "unknown title":
            return None

        try:
            response = self.httpSession.get(
                "https://openlibrary.org/search.json",
                params={
                    "title": title, "author": author if author.lower() != "unknown author" else "",
                    "fields": "title,author_name,cover_i",
                    "limit": 5,
                },
                timeout=8,
            )
            response.raise_for_status()
            docs = response.json().get("docs", [])
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            return None
        finally:
            if "response" in locals():
                response.close()

        for doc in docs:
            if not isinstance(doc, dict) or not matchBook(doc, title, author):
                continue
            coverId = doc.get("cover_i")
            if isinstance(coverId, int) and coverId > 0:
                coverUrl = f"https://covers.openlibrary.org/b/id/{coverId}-L.jpg"
                found = self._availableImage(coverUrl)
                if found:
                    return found
        return None

    def resolve(self, book):
        """Get a verified public cover URL, otherwise the existing asset key."""
        if not isinstance(book, dict):
            return DEFAULT_COVER_ASSET

        cacheKey = (
            str(book.get("platform") or ""),
            str(book.get("coverArt") or ""),
            str(book.get("coverIsbn") or book.get("isbn") or ""),
            str(book.get("title") or ""),
            str(book.get("author") or ""),
        )
        now = time.time()
        with self._cacheLock:
            cached = self._cache.get(cacheKey)
            if cached and now - cached[0] < COVER_CACHE_SECONDS:
                return cached[1]

        coverUrl = self._availableImage(book.get("coverArt"))
        if not coverUrl:
            isbn = bookIsbn(book)
            if isbn:
                coverUrl = self._availableImage(
                    f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"
                )
        if not coverUrl:
            coverUrl = self._searchOpenLibrary(book)

        result = coverUrl or DEFAULT_COVER_ASSET
        with self._cacheLock:
            if len(self._cache) >= 256:
                self._cache.clear()
            self._cache[cacheKey] = (now, result)
        return result
