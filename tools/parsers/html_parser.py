"""Extract quoted passages and citations from HTML articles."""

from dataclasses import dataclass
from html.parser import HTMLParser
import re


@dataclass
class ExtractedQuote:
    """A quoted passage found in an article."""

    text_exact: str  # The quoted text
    text_before: str  # ~50 chars before the quote in the article
    text_after: str  # ~50 chars after the quote in the article
    citation_hint: str  # Nearby citation like "(Author, Year)" or DOI
    paragraph_context: str  # The full paragraph containing the quote
    position: int  # Character position in the plain text


# Minimum quote length to extract (avoids grabbing scare-quoted single words)
MIN_QUOTE_LEN = 20

# Citation hint patterns
# Matches (Author, Year), (Author & Author, Year), (Author et al., Year),
# (ACRONYM, Year), (O'Brien et al., Year), multi-cite with ; separators
_NAME_CHAR = r"[A-Za-z'\u2019]"  # letters, apostrophe, right single quote
_AUTHOR_YEAR_RE = re.compile(
    r"\(("
    rf"[A-Z]{_NAME_CHAR}+(?:\s(?:&|and)\s[A-Z]{_NAME_CHAR}+)*"
    r"(?:\s(?:et\s+al\.?))?"
    r",?\s*\d{4}[a-z]?"
    rf"(?:;\s*(?:[A-Z]{_NAME_CHAR}+(?:\s(?:&|and)\s[A-Z]{_NAME_CHAR}+)*"
    r"(?:\s(?:et\s+al\.?))?"
    r",?\s*)?\d{4}[a-z]?)*"
    r")\)"
)
_DOI_RE = re.compile(r"10\.\d{4,}/[^\s,;)\"'\u201d]+")

# Quote patterns: straight doubles, curly doubles
# After newline normalization, single \n is gone; \n\n marks paragraph boundaries.
# Exclude \n from matches to prevent cross-paragraph grabs.
_STRAIGHT_QUOTE_RE = re.compile(r'"([^"\n]{%d,}?)"' % MIN_QUOTE_LEN)
_CURLY_QUOTE_RE = re.compile(r"\u201c([^\u201d\n]{%d,}?)\u201d" % MIN_QUOTE_LEN)

# Regex patterns for VCITE annotation elements to remove before parsing.
_VCITE_BADGE_RE = re.compile(
    r'<sup\s+class="vcite-badge"[^>]*>.*?</sup>', re.DOTALL
)

# Classes whose enclosing div (including nested divs) should be removed
_VCITE_DIV_CLASSES = ("vcite-panel", "vcite-banner")


def _remove_vcite_divs(html: str) -> str:
    """Remove div elements with vcite annotation classes, handling nesting.

    Simple regex can't handle nested divs, so we find the opening tag
    and then count div open/close to find the matching end tag.
    """
    for cls in _VCITE_DIV_CLASSES:
        pattern = re.compile(rf'<div\s+[^>]*class="[^"]*{cls}[^"]*"[^>]*>')
        while True:
            m = pattern.search(html)
            if not m:
                break
            # Find the matching </div> by counting nesting
            start = m.start()
            pos = m.end()
            depth = 1
            while pos < len(html) and depth > 0:
                open_m = re.search(r"<div[\s>]", html[pos:])
                close_m = re.search(r"</div>", html[pos:])
                if close_m is None:
                    break
                if open_m and open_m.start() < close_m.start():
                    depth += 1
                    pos += open_m.end()
                else:
                    depth -= 1
                    if depth == 0:
                        end = pos + close_m.end()
                        html = html[:start] + html[end:]
                        break
                    pos += close_m.end()
    return html


class _HTMLStripper(HTMLParser):
    """Strip HTML tags and collect plain text, skipping script/style blocks."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True
        elif tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.parts.append("\n\n")
        elif tag == "blockquote":
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        elif tag == "blockquote":
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


def _strip_html(html_content: str) -> str:
    """Convert HTML to plain text, preserving paragraph boundaries.

    Pre-strips VCITE annotation elements (panels, badges, banners) so
    their duplicated content doesn't pollute the plain text.
    """
    # Remove VCITE annotation elements before parsing
    cleaned = _remove_vcite_divs(html_content)
    cleaned = _VCITE_BADGE_RE.sub("", cleaned)

    stripper = _HTMLStripper()
    stripper.feed(cleaned)
    text = stripper.get_text()
    # Collapse runs of blank lines to double newlines (paragraph boundaries)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Replace single newlines with spaces (they're just line wraps, not paragraphs)
    # but preserve double newlines as paragraph boundaries
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    return text


def _extract_context(text: str, start: int, end: int, window: int = 50):
    """Extract before/after context windows around a span."""
    before_start = max(0, start - window)
    before = text[before_start:start]
    after = text[end : end + window]
    return before, after


def _find_paragraph(text: str, position: int) -> str:
    """Find the paragraph containing the given position."""
    # Split on double newlines
    paras = re.split(r"\n\n+", text)
    offset = 0
    for para in paras:
        para_end = offset + len(para)
        if offset <= position < para_end:
            return para.strip()
        # Account for the separator
        offset = para_end
        # Skip past the separator in the original text
        while offset < len(text) and text[offset] == "\n":
            offset += 1
    return ""


def _find_citation_hint(text: str, quote_start: int, quote_end: int) -> str:
    """Look for a citation hint near a quote (within 200 chars after)."""
    search_region = text[quote_end : quote_end + 200]

    # Check for DOI first (more specific)
    doi_match = _DOI_RE.search(search_region)
    if doi_match:
        return doi_match.group(0)

    # Check for (Author, Year) pattern
    cite_match = _AUTHOR_YEAR_RE.search(search_region)
    if cite_match:
        return cite_match.group(0)

    # Also check a small window before the quote
    before_region = text[max(0, quote_start - 100) : quote_start]
    cite_match = _AUTHOR_YEAR_RE.search(before_region)
    if cite_match:
        return cite_match.group(0)

    return ""


def extract_quotes_html(html_content: str) -> list[ExtractedQuote]:
    """Extract quoted passages from HTML.

    Looks for:
    1. Text in quotation marks ("..." or \u201c...\u201d)
    2. <blockquote> elements (treated as quotes)

    For each quote, extracts ~50 chars of surrounding context and
    looks for nearby citation hints like (Author, Year) or DOI patterns.
    """
    plain_text = _strip_html(html_content)
    quotes: list[ExtractedQuote] = []
    seen_texts: set[str] = set()

    # Find all quoted passages using both straight and curly quotes
    for pattern in (_STRAIGHT_QUOTE_RE, _CURLY_QUOTE_RE):
        for match in pattern.finditer(plain_text):
            quote_text = match.group(1).strip()
            if quote_text in seen_texts:
                continue
            seen_texts.add(quote_text)

            # Position of the quoted text itself (inside the quote marks)
            pos = match.start(1)
            end = match.end(1)

            before, after = _extract_context(plain_text, match.start(), match.end())
            citation_hint = _find_citation_hint(plain_text, match.start(), match.end())
            paragraph = _find_paragraph(plain_text, pos)

            quotes.append(
                ExtractedQuote(
                    text_exact=quote_text,
                    text_before=before,
                    text_after=after,
                    citation_hint=citation_hint,
                    paragraph_context=paragraph,
                    position=pos,
                )
            )

    # Sort by position in the document
    quotes.sort(key=lambda q: q.position)
    return quotes
