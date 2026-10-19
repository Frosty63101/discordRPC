"""Source adapters for Goodreads, StoryGraph and Audiobookshelf.

Parsers prefer stable book links and metadata over CSS class names. Websites can
still change or block automated requests; failures are reported, not invented.
"""
import json
import re
import time
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


def cleanText(value):
    return " ".join(str(value or "").split()).strip()


def firstText(node, selectors):
    for selector in selectors:
        child = node.select_one(selector)
        if child:
            value = cleanText(child.get_text(" ", strip=True))
            if value:
                return value
    return None


def imageUrl(node, baseUrl):
    image = node.select_one("img")
    if not image:
        return None
    value = image.get("data-src") or image.get("src") or image.get("data-original")
    if not value:
        return None
    if value.startswith("data:"):
        return None
    return urljoin(baseUrl, value)


def findContainer(anchor):
    for parent in list(anchor.parents)[:6]:
        if getattr(parent, "name", None) in ("article", "tr", "li"):
            return parent
        if parent.get("data-book-id") or parent.get("data-testid") in ("book-card", "book"):
            return parent
        classes = " ".join(parent.get("class", []))
        if any(fragment in classes.lower() for fragment in ("book-pane", "book-card", "book_row", "bookrow")):
            return parent
    return anchor.parent or anchor


def stableKey(prefix, href, title, author):
    match = re.search(r"/(?:books|book/show)/(?:[^/?#]*/)?([0-9a-f-]{6,}|\d+)(?:[/?#]|$)", href or "", re.I)
    if match:
        return f"{prefix}-{match.group(1).lower()}"
    normalized = re.sub(r"[^a-z0-9]+", "-", f"{title}-{author}".lower()).strip("-")
    return f"{prefix}-{normalized[:128]}"


def getJsonLdBooks(soup):
    result = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        queue = data if isinstance(data, list) else [data]
        while queue:
            item = queue.pop(0)
            if not isinstance(item, dict):
                continue
            kind = item.get("@type", "")
            kinds = kind if isinstance(kind, list) else [kind]
            if "Book" in kinds:
                result.append(item)
            for field in ("@graph", "itemListElement"):
                nested = item.get(field) or []
                queue.extend(nested if isinstance(nested, list) else [nested])
            if isinstance(item.get("item"), dict):
                queue.append(item["item"])
    return result


def parseGoodreadsBooks(htmlText, pageUrl):
    soup = BeautifulSoup(htmlText, "html.parser")
    found = {}
    anchors = soup.select('a[href*="/book/show/"]')
    for anchor in anchors:
        href = urljoin(pageUrl, anchor.get("href") or "")
        if urlsplit(href).hostname not in ("goodreads.com", "www.goodreads.com"):
            continue
        container = findContainer(anchor)
        title = (firstText(container, ['td.field.title a', '[data-testid="bookTitle"]', 'a.bookTitle', 'h3 a[href*="/book/show/"]'])
                 or cleanText(anchor.get("title"))
                 or cleanText(anchor.get_text(" ", strip=True)))
        if not title or title.lower() in ("view book", "book details"):
            continue
        author = firstText(container, ['td.field.author a', 'a[href*="/author/show/"]', '[itemprop="author"]'])
        isbn = firstText(container, ['td.field.isbn .value', '[itemprop="isbn"]'])
        date = firstText(container, ['td.field.date_started .date_started_value', 'time[datetime]'])
        key = isbn if isbn and re.fullmatch(r"[0-9Xx-]{10,20}", isbn) else stableKey("gr", href, title, author or "")
        found[key] = {
            "isbn": key, "title": title, "author": author or "Unknown Author",
            "coverArt": imageUrl(container, pageUrl), "startDate": date,
            "platform": "goodreads", "bookUrl": href
        }
    if found:
        return found

    # Structured book metadata is a fallback if a provider changes its DOM.
    for book in getJsonLdBooks(soup):
        title = cleanText(book.get("name"))
        if not title:
            continue
        authorData = book.get("author") or {}
        if isinstance(authorData, list):
            authorData = authorData[0] if authorData else {}
        author = authorData.get("name", "") if isinstance(authorData, dict) else str(authorData)
        href = urljoin(pageUrl, str(book.get("url") or pageUrl))
        key = stableKey("gr", href, title, author)
        found[key] = {"isbn": key, "title": title, "author": author or "Unknown Author",
                      "coverArt": book.get("image"), "startDate": None,
                      "platform": "goodreads", "bookUrl": href}
    return found


def parseStoryGraphBooks(htmlText, pageUrl):
    soup = BeautifulSoup(htmlText, "html.parser")
    found = {}
    anchors = soup.select('a[href^="/books/"], a[href*="thestorygraph.com/books/"]')
    for anchor in anchors:
        href = urljoin(pageUrl, anchor.get("href") or "")
        if urlsplit(href).hostname not in ("app.thestorygraph.com", "thestorygraph.com", "www.thestorygraph.com"):
            continue
        container = findContainer(anchor)
        title = (firstText(container, ['h3 a[href*="/books/"]', 'h2 a[href*="/books/"]', '[itemprop="name"]'])
                 or cleanText(anchor.get_text(" ", strip=True)))
        if not title:
            continue
        author = firstText(container, ['a[href*="/authors/"]', '[itemprop="author"]'])
        series = firstText(container, ['a[href*="/series/"]'])
        date = None
        for tag in container.select("p, time, span"):
            value = cleanText(tag.get_text(" ", strip=True))
            match = re.search(r"\bStarted\s+(.+)", value, re.I)
            if match and len(match.group(1)) < 70:
                date = match.group(1)
                break
        key = stableKey("sg", href, title, author or "")
        found[key] = {
            "isbn": key, "title": title, "author": author or "Unknown Author",
            "coverArt": imageUrl(container, pageUrl), "startDate": date,
            "platform": "storygraph", "bookUrl": href, "series": series
        }
    if found:
        return found

    for book in getJsonLdBooks(soup):
        title = cleanText(book.get("name"))
        if not title:
            continue
        authorData = book.get("author") or {}
        if isinstance(authorData, list):
            authorData = authorData[0] if authorData else {}
        author = authorData.get("name", "") if isinstance(authorData, dict) else str(authorData)
        href = urljoin(pageUrl, str(book.get("url") or pageUrl))
        key = stableKey("sg", href, title, author)
        found[key] = {"isbn": key, "title": title, "author": author or "Unknown Author",
                      "coverArt": book.get("image"), "startDate": None,
                      "platform": "storygraph", "bookUrl": href}
    return found


def normalizeServerUrl(url):
    value = cleanText(url).rstrip("/")
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Audiobookshelf server URL must be an http(s) URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Audiobookshelf server URL must not contain credentials, query or fragment")
    return value


def timestampSeconds(value):
    try:
        stamp = float(value)
        return stamp / 1000 if stamp > 100000000000 else stamp
    except (TypeError, ValueError):
        return 0.0


def fetchAudiobookshelfBooks(httpSession, serverUrl, apiKey, userId, freshnessSeconds=120):
    """Return (library book choices, active key).

    Online sessions take precedence. Recent history is only a fallback signal:
    an updated session younger than freshnessSeconds may have just stopped.
    Older history is never labelled as actively playing.
    """
    serverUrl = normalizeServerUrl(serverUrl)
    if not apiKey or not userId:
        raise ValueError("Audiobookshelf API key and user UUID are required")
    headers = {"Authorization": f"Bearer {apiKey}", "Accept": "application/json"}

    def apiGet(path, params=None):
        response = httpSession.get(f"{serverUrl}{path}", headers=headers, params=params, timeout=12)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as error:
            raise ValueError(f"Audiobookshelf returned non-JSON content for {path}; check the server URL") from error

    def apiPost(path):
        response = httpSession.post(f"{serverUrl}{path}", headers=headers, timeout=12)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as error:
            raise ValueError(f"Audiobookshelf returned non-JSON content for {path}; check the server URL") from error

    sessions = []
    onlineSessions = []
    try:
        online = apiGet("/api/users/online")
        for entry in online.get("openSessions", []):
            owner = entry.get("userId") or (entry.get("user") or {}).get("id")
            if str(owner) == str(userId):
                onlineSessions.append(entry)
    except Exception:
        # This API is admin-only. A user-scoped key can still inspect its own history.
        pass

    try:
        response = apiGet(f"/api/users/{userId}/listening-sessions", {"itemsPerPage": 10})
        sessions = response.get("sessions", [])
    except Exception as historyError:
        # Non-admin keys can access their own sessions via /api/me. The
        # authorize endpoint is POST, not GET, and tells us which user owns
        # the key before we fall back to this self-scoped route.
        try:
            authorizedUser = apiPost("/api/authorize").get("user") or {}
        except Exception as authError:
            raise ValueError(
                "Cannot access listening sessions. Check the server URL, API key and its permissions"
            ) from authError
        if str(authorizedUser.get("id")) != str(userId):
            raise ValueError("API key owner differs from the configured Audiobookshelf user UUID") from historyError
        response = apiGet("/api/me/listening-sessions", {"itemsPerPage": 10})
        sessions = response.get("sessions", [])

    now = time.time()
    byId = {}
    activeKey = None

    # For user-scoped tokens without access to /api/users/online, probe a
    # recently updated session. /api/session/<id> is limited to open sessions
    # and accessible to the owner; history alone never proves activity.
    if not onlineSessions:
        for candidate in sorted(sessions, key=lambda item: timestampSeconds(item.get("updatedAt")), reverse=True)[:3]:
            sessionId = candidate.get("id")
            lastUpdated = timestampSeconds(candidate.get("updatedAt"))
            if not sessionId or not lastUpdated or not 0 <= now - lastUpdated <= freshnessSeconds:
                continue
            try:
                openSession = apiGet(f"/api/session/{sessionId}")
                if openSession and str(openSession.get("id")) == str(sessionId):
                    onlineSessions.append(openSession)
                    break
            except Exception:
                continue

    # Most recent first, while open sessions win selection.
    ordered = sorted(sessions, key=lambda item: timestampSeconds(item.get("updatedAt")), reverse=True)
    ordered = sorted(ordered + onlineSessions, key=lambda item: item in onlineSessions, reverse=True)

    for item in ordered:
        libraryId = item.get("libraryItemId") or item.get("libraryItem", {}).get("id")
        if not libraryId:
            continue
        key = f"abs-{libraryId}"
        updateTime = timestampSeconds(item.get("updatedAt"))
        isOnline = item in onlineSessions
        isRecent = bool(updateTime and 0 <= now - updateTime <= freshnessSeconds)
        isActive = isOnline and (isRecent or not updateTime)
        # Historical sessions are selectable, but not declared live. A recently
        # updated history record alone cannot prove a player is still running.
        metadata = item.get("mediaMetadata") or item.get("media", {}).get("metadata") or {}
        title = item.get("displayTitle") or metadata.get("title")
        author = item.get("displayAuthor") or metadata.get("authorName")
        coverPath = item.get("coverPath")
        if not title:
            try:
                libraryItem = apiGet(f"/api/items/{libraryId}")
                libraryMedia = libraryItem.get("media") or {}
                moreMetadata = libraryMedia.get("metadata") or {}
                title = moreMetadata.get("title")
                author = author or moreMetadata.get("authorName")
                coverPath = coverPath or libraryItem.get("coverPath")
            except Exception:
                title = "Unknown Title"
        if not coverPath:
            coverPath = f"/api/items/{libraryId}/cover"
        coverUrl = urljoin(f"{serverUrl}/", coverPath.lstrip("/"))
        if key not in byId or isOnline:
            byId[key] = {
                "isbn": key, "title": cleanText(title) or "Unknown Title",
                "author": cleanText(author) or "Unknown Author",
                "coverArt": coverUrl, "startDate": None,
                "platform": "audiobookshelf", "bookUrl": f"{serverUrl}/item/{libraryId}",
                "libraryItemId": libraryId, "currentlyListening": bool(isActive),
                "positionSeconds": item.get("currentTime"), "durationSeconds": item.get("duration")
            }
        if isActive and activeKey is None:
            activeKey = key

    return byId, activeKey
