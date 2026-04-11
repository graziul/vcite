"""Fetch source documents and extract plain text for VCITE verification.

Given a VCiteCitation object, resolves the best URL (archive_url > url > DOI),
fetches the document, and extracts plain text suitable for passage matching.

Zero external dependencies — stdlib only.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Optional

USER_AGENT = (
    "VCITE-verify/0.1 (https://github.com/graziul/vcite; mailto:vcite@idep.pub)"
)
REQUEST_TIMEOUT = 15  # seconds


@dataclass
class FetchResult:
    """Result of fetching a source document."""

    text: str  # plain text content
    url: str  # the URL that was successfully fetched
    content_type: str  # MIME type from response
    error: str = ""  # non-empty on failure


class _HTMLToText(HTMLParser):
    """Strip HTML tags and collect plain text, skipping script/style blocks."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = True
        elif tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
                      "li", "tr", "blockquote", "section", "article"):
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = False
        elif tag in ("blockquote", "p", "div", "li"):
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def handle_entityref(self, name):
        from html import unescape
        if not self._skip:
            self.parts.append(unescape(f"&{name};"))

    def handle_charref(self, name):
        from html import unescape
        if not self._skip:
            self.parts.append(unescape(f"&#{name};"))

    def get_text(self) -> str:
        return "".join(self.parts)


def html_to_text(html_content: str) -> str:
    """Convert HTML to plain text, preserving paragraph boundaries."""
    parser = _HTMLToText()
    parser.feed(html_content)
    text = parser.get_text()
    # Collapse runs of blank lines to double newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Replace single newlines with spaces (line wraps, not paragraphs)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    # Collapse runs of spaces
    text = re.sub(r"  +", " ", text)
    return text.strip()


def _resolve_doi_url(doi: str) -> str:
    """Convert a DOI to a resolvable HTTPS URL."""
    clean = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    return f"https://doi.org/{clean}"


def _fetch_url(url: str) -> FetchResult:
    """Fetch a single URL and return its content as plain text."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "text/html, application/xhtml+xml, text/plain, */*")

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()

            # Determine encoding
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()
            try:
                body = raw.decode(charset)
            except (UnicodeDecodeError, LookupError):
                body = raw.decode("utf-8", errors="replace")

            # Extract plain text from HTML
            if "html" in content_type or body.lstrip().startswith(("<!DOCTYPE", "<html", "<HTML")):
                text = html_to_text(body)
            else:
                text = body

            return FetchResult(text=text, url=url, content_type=content_type)

    except urllib.error.HTTPError as e:
        return FetchResult(text="", url=url, content_type="",
                           error=f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        return FetchResult(text="", url=url, content_type="",
                           error=f"URL error: {e.reason}")
    except (TimeoutError, OSError) as e:
        return FetchResult(text="", url=url, content_type="",
                           error=f"Connection error: {e}")


def resolve_source_urls(citation) -> list[str]:
    """Determine URLs to try for fetching source, in priority order.

    Priority: archive_url > fragment_url > url > DOI-resolved URL.
    """
    urls: list[str] = []

    source = citation.source
    target = citation.target

    # Archive URL is most stable (Perma.cc, Wayback Machine)
    if source.archive_url:
        urls.append(source.archive_url)

    # Fragment URL may contain the full source URL with text fragment
    if hasattr(target, "fragment_url") and target.fragment_url:
        # Strip the text fragment for fetching (servers don't handle it)
        base = target.fragment_url.split("#:~:")[0]
        if base and base not in urls:
            urls.append(base)

    # Direct URL
    if source.url:
        url = source.url
        # If it's a DOI URL, we'll also add it — but keep direct URL priority
        if url not in urls:
            urls.append(url)

    # DOI → URL
    if source.doi:
        doi_url = _resolve_doi_url(source.doi)
        if doi_url not in urls:
            urls.append(doi_url)

    return urls


def fetch_source(citation) -> FetchResult:
    """Fetch the source document for a VCITE citation.

    Tries URLs in priority order (archive > direct > DOI).
    Returns the first successful fetch.
    """
    urls = resolve_source_urls(citation)
    if not urls:
        return FetchResult(
            text="", url="", content_type="",
            error="No fetchable URL: citation has no url, doi, or archive_url"
        )

    errors: list[str] = []
    for url in urls:
        result = _fetch_url(url)
        if not result.error and result.text:
            return result
        if result.error:
            errors.append(f"  {url}: {result.error}")

    return FetchResult(
        text="", url=urls[0], content_type="",
        error="All source URLs failed:\n" + "\n".join(errors)
    )
