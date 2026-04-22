"""Tests for the HTML citation extractor.

Regression coverage for the citation-hint regex — particularly edge
cases that were silently dropped in earlier versions (accented chars,
hyphenated surnames).
"""

import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(TOOLS_DIR))

from parsers.html_parser import _AUTHOR_YEAR_RE, _INLINE_CITE_RE, extract_quotes_html


class TestAuthorYearRegex:
    """The parenthetical (Author, Year) pattern."""

    def test_simple_ascii(self):
        text = "A claim (Smith, 2020) supports this."
        m = _AUTHOR_YEAR_RE.search(text)
        assert m is not None
        assert m.group(1) == "Smith, 2020"

    def test_two_authors(self):
        text = "They argue this (Jones & Lee, 2021)."
        m = _AUTHOR_YEAR_RE.search(text)
        assert m is not None
        assert m.group(1) == "Jones & Lee, 2021"

    def test_et_al(self):
        text = "Found that (Carroll et al., 2020)."
        m = _AUTHOR_YEAR_RE.search(text)
        assert m is not None
        assert "Carroll et al." in m.group(1)

    def test_accented_surname(self):
        """Regression: Hernández (é) was silently dropped."""
        text = "As noted (García-López, 2022)."
        m = _AUTHOR_YEAR_RE.search(text)
        assert m is not None
        assert "García-López" in m.group(1)

    def test_hyphenated_surname(self):
        """Regression: Rodriguez-Lonebear had the hyphen but no match."""
        text = "Work by (Rodriguez-Lonebear, 2016) shows."
        m = _AUTHOR_YEAR_RE.search(text)
        assert m is not None
        assert "Rodriguez-Lonebear" in m.group(1)

    def test_accented_hyphenated_surname(self):
        """Regression: the actual Katina first-citation case."""
        text = "privacy concerns (Savage & Monroy-Hernández, 2018) remain."
        m = _AUTHOR_YEAR_RE.search(text)
        assert m is not None
        assert "Monroy-Hernández" in m.group(1)

    def test_apostrophe_surname(self):
        text = "cf. (O'Brien et al., 2024) for detail."
        m = _AUTHOR_YEAR_RE.search(text)
        assert m is not None
        assert "O'Brien" in m.group(1)

    def test_multiple_citations_semicolon(self):
        text = "Various sources (Lin, 2015; Newell, 2021) agree."
        m = _AUTHOR_YEAR_RE.search(text)
        assert m is not None
        # The full multi-cite is captured
        assert "Lin" in m.group(1)

    def test_multi_space_between_authors(self):
        """Regression: 'Couldry  and Mejias' (double space) was failing."""
        text = "what Couldry  and Mejias (2021) call"
        m = _INLINE_CITE_RE.search(text)
        assert m is not None
        # Must capture BOTH authors, not just Mejias
        assert "Couldry" in m.group(1) and "Mejias" in m.group(1)


class TestMultiCiteSplitting:
    """Multi-cite groups must produce one citation per source."""

    def test_extract_splits_multicite(self):
        from parsers.html_parser import extract_quotes_html
        html = "<p>A valid claim here (Smith, 2020; Jones, 2021; Lee, 2022).</p>"
        quotes = extract_quotes_html(html)
        hints = [q.citation_hint for q in quotes]
        assert "Smith, 2020" in hints
        assert "Jones, 2021" in hints
        assert "Lee, 2022" in hints

    def test_extract_preserves_single_cite(self):
        from parsers.html_parser import extract_quotes_html
        html = "<p>A claim here (Smith, 2020) is good.</p>"
        quotes = extract_quotes_html(html)
        hints = [q.citation_hint for q in quotes]
        assert hints == ["Smith, 2020"]


class TestKatinaExtraction:
    """End-to-end test on the Katina article."""

    def test_savage_citation_extracted(self):
        """The first-paragraph (Savage & Monroy-Hernández, 2018) must match."""
        article_path = TOOLS_DIR.parent / "examples" / "katina-article.html"
        if not article_path.exists():
            import pytest
            pytest.skip("Katina article not available")

        html = article_path.read_text()
        quotes = extract_quotes_html(html)

        # The claim attributed to Savage should be extracted
        savage_quotes = [q for q in quotes if "Savage" in q.citation_hint]
        assert len(savage_quotes) >= 1, \
            "The first citation (Savage & Monroy-Hernández, 2018) was not extracted"
