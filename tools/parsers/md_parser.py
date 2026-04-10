"""Extract quoted passages and citations from Markdown articles."""

import re
from .html_parser import (
    ExtractedQuote,
    MIN_QUOTE_LEN,
    _STRAIGHT_QUOTE_RE,
    _CURLY_QUOTE_RE,
    _AUTHOR_YEAR_RE,
    _DOI_RE,
    _extract_context,
    _find_paragraph,
    _find_citation_hint,
)

# Blockquote: lines starting with >
_BLOCKQUOTE_RE = re.compile(r"^>\s*(.+)$", re.MULTILINE)

# Pandoc vcite attribute: [text]{.vcite ...}
_PANDOC_VCITE_RE = re.compile(r"\[([^\]]{%d,}?)\]\{\.vcite[^}]*\}" % MIN_QUOTE_LEN)


def extract_quotes_md(md_content: str) -> list[ExtractedQuote]:
    """Extract quoted passages from Markdown.

    Looks for:
    1. Text in quotation marks ("..." or curly quotes)
    2. > blockquote lines (concatenated into single passages)
    3. Existing Pandoc vcite attributes [text]{.vcite ...}
    """
    quotes: list[ExtractedQuote] = []
    seen_texts: set[str] = set()

    def _add_quote(text: str, pos: int, ctx_start: int, ctx_end: int):
        text = text.strip()
        if text in seen_texts or len(text) < MIN_QUOTE_LEN:
            return
        seen_texts.add(text)
        before, after = _extract_context(md_content, ctx_start, ctx_end)
        citation_hint = _find_citation_hint(md_content, ctx_start, ctx_end)
        paragraph = _find_paragraph(md_content, pos)
        quotes.append(
            ExtractedQuote(
                text_exact=text,
                text_before=before,
                text_after=after,
                citation_hint=citation_hint,
                paragraph_context=paragraph,
                position=pos,
            )
        )

    # 1. Inline quoted passages (straight and curly quotes)
    for pattern in (_STRAIGHT_QUOTE_RE, _CURLY_QUOTE_RE):
        for match in pattern.finditer(md_content):
            _add_quote(
                match.group(1), match.start(1), match.start(), match.end()
            )

    # 2. Blockquote passages: concatenate consecutive > lines
    lines = md_content.split("\n")
    bq_parts: list[str] = []
    bq_start: int = -1
    offset = 0
    for line in lines:
        bq_match = _BLOCKQUOTE_RE.match(line)
        if bq_match:
            if bq_start < 0:
                bq_start = offset
            bq_parts.append(bq_match.group(1).strip())
        else:
            if bq_parts:
                bq_text = " ".join(bq_parts)
                bq_end = offset  # end of last blockquote line
                _add_quote(bq_text, bq_start, bq_start, bq_end)
                bq_parts = []
                bq_start = -1
        offset += len(line) + 1  # +1 for the newline
    # Flush trailing blockquote
    if bq_parts:
        bq_text = " ".join(bq_parts)
        _add_quote(bq_text, bq_start, bq_start, offset)

    # 3. Pandoc vcite attributes
    for match in _PANDOC_VCITE_RE.finditer(md_content):
        _add_quote(
            match.group(1), match.start(1), match.start(), match.end()
        )

    # Sort by position
    quotes.sort(key=lambda q: q.position)
    return quotes
