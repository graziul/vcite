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
# Name characters: ASCII letters, Latin-1/Extended accents (e.g. \u00e9 \u00f1 \u00e1),
# apostrophe, right single quote (\u2019), hyphen (for hyphenated surnames
# like Monroy-Hern\u00e1ndez, Rodriguez-Lonebear). The \u00c0-\u024f range
# covers Latin-1 Supplement + Latin Extended-A/B.
_NAME_CHAR = r"[A-Za-z\u00c0-\u024f'\u2019\-]"
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

# Inline citation: "Author (Year)" or "Author (Year; Year)" without outer parens
_INLINE_CITE_RE = re.compile(
    rf"(?<!\()"  # not preceded by open paren (avoid matching inside parenthetical cites)
    rf"([A-Z]{_NAME_CHAR}+(?:\s(?:&|and)\s[A-Z]{_NAME_CHAR}+)*"
    rf"(?:\s(?:et\s+al\.?))?)"
    r"\s*\((\d{4}[a-z]?(?:;\s*\d{4}[a-z]?)*)\)"
)

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


def _extract_claim_sentence(text: str, cite_start: int) -> tuple[str, int, int]:
    """Extract the sentence or clause containing a citation marker.

    Walks backward from the citation to find the sentence start (period,
    paragraph boundary, or semicolon), then forward to find the end.
    Returns (sentence_text, start_pos, end_pos).
    """
    # Walk backward to find sentence start
    sent_start = cite_start
    for i in range(cite_start - 1, max(cite_start - 500, -1), -1):
        if i < 0:
            sent_start = 0
            break
        ch = text[i]
        if ch in (".", "!", "?") and i < cite_start - 2:
            sent_start = i + 1
            break
        if ch == "\n" and i < cite_start - 1 and (i == 0 or text[i - 1] == "\n"):
            sent_start = i + 1
            break
    else:
        sent_start = max(cite_start - 500, 0)

    # Walk forward past the citation to find sentence end
    sent_end = cite_start
    paren_depth = 0
    for i in range(cite_start, min(cite_start + 300, len(text))):
        ch = text[i]
        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
            if paren_depth <= 0:
                # Continue past the closing paren to find period
                for j in range(i + 1, min(i + 50, len(text))):
                    if text[j] in (".", "!", "?", "\n"):
                        sent_end = j + 1
                        break
                else:
                    sent_end = i + 1
                break
    else:
        sent_end = min(cite_start + 300, len(text))

    sentence = text[sent_start:sent_end].strip()
    return sentence, sent_start, sent_end


def extract_quotes_html(html_content: str) -> list[ExtractedQuote]:
    """Extract cited passages from HTML.

    Finds TWO types of citable content:
    1. Direct quotes in quotation marks ("..." or curly quotes)
    2. Paraphrased claims attributed via (Author, Year) citations

    Both get VCITE objects. Direct quotes have the exact source text.
    Paraphrased claims have the author's attributed claim as text_exact.
    """
    plain_text = _strip_html(html_content)
    quotes: list[ExtractedQuote] = []
    seen_texts: set[str] = set()
    seen_positions: set[int] = set()  # avoid duplicates at same location

    # --- Pass 1: Direct quotes in quotation marks ---
    for pattern in (_STRAIGHT_QUOTE_RE, _CURLY_QUOTE_RE):
        for match in pattern.finditer(plain_text):
            quote_text = match.group(1).strip()
            if quote_text in seen_texts:
                continue
            seen_texts.add(quote_text)

            pos = match.start(1)
            end = match.end(1)
            seen_positions.add(pos)

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

    # --- Pass 2: Paraphrased claims with (Author, Year) citations ---
    # Collect all positions covered by Pass 1 quotes (with margin)
    covered_ranges = []
    for q in quotes:
        covered_ranges.append((q.position - 50, q.position + len(q.text_exact) + 200))

    def is_covered(pos):
        return any(lo <= pos <= hi for lo, hi in covered_ranges)

    for match in _AUTHOR_YEAR_RE.finditer(plain_text):
        cite_text = match.group(0)  # e.g., "(Savage & Monroy-Hernández, 2018)"
        cite_start = match.start()

        # Skip if this citation is inside a range already covered by a direct quote
        if is_covered(cite_start):
            continue

        # Extract the sentence/clause this citation is attributed to
        sentence, sent_start, sent_end = _extract_claim_sentence(plain_text, cite_start)

        # Remove the citation marker itself from the claim text
        claim_text = sentence.replace(cite_text, "").strip()
        # Clean up trailing/leading punctuation artifacts
        claim_text = re.sub(r"^\s*[,;.]\s*", "", claim_text)
        claim_text = re.sub(r"\s*[,;]\s*$", "", claim_text)
        claim_text = claim_text.strip()

        if not claim_text or len(claim_text) < 15:
            continue
        if claim_text in seen_texts:
            continue
        seen_texts.add(claim_text)

        before, after = _extract_context(plain_text, sent_start, sent_end)
        paragraph = _find_paragraph(plain_text, cite_start)

        quotes.append(
            ExtractedQuote(
                text_exact=claim_text,
                text_before=before,
                text_after=after,
                citation_hint=match.group(1),  # inner text without parens
                paragraph_context=paragraph,
                position=sent_start,
            )
        )

    # --- Pass 3: Inline citations like "Erdos (2016)" or "Lamdan (2022)" ---
    # Rebuild covered ranges to include Pass 2 results
    covered_ranges = []
    for q in quotes:
        covered_ranges.append((q.position - 50, q.position + len(q.text_exact) + 200))

    for match in _INLINE_CITE_RE.finditer(plain_text):
        author_name = match.group(1)
        years = match.group(2)
        cite_start = match.start()

        if is_covered(cite_start):
            continue

        sentence, sent_start, sent_end = _extract_claim_sentence(plain_text, cite_start)
        # Remove the inline citation from the claim text
        cite_full = f"{author_name} ({years})"
        claim_text = sentence.replace(cite_full, "").strip()
        claim_text = re.sub(r"^\s*[,;.]\s*", "", claim_text)
        claim_text = re.sub(r"\s*[,;]\s*$", "", claim_text)
        claim_text = claim_text.strip()

        if not claim_text or len(claim_text) < 15 or claim_text in seen_texts:
            continue
        seen_texts.add(claim_text)

        before, after = _extract_context(plain_text, sent_start, sent_end)
        paragraph = _find_paragraph(plain_text, cite_start)

        quotes.append(
            ExtractedQuote(
                text_exact=claim_text,
                text_before=before,
                text_after=after,
                citation_hint=f"{author_name}, {years}",
                paragraph_context=paragraph,
                position=sent_start,
            )
        )

    # Sort by position in the document
    quotes.sort(key=lambda q: q.position)
    return quotes
