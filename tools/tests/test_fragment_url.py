"""Tests for ``tools/fragment_url.py`` — W3C Text Fragment URL generation
and the integration into ``tools/enhance.py``."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

TOOLS_DIR = Path(__file__).parent.parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(REPO_ROOT / "implementations" / "python"))

from fragment_url import build_text_fragment_url, strip_fragment  # noqa: E402


# ---------------------------------------------------------------------------
# Basic generation
# ---------------------------------------------------------------------------


def test_basic_long_passage_uses_text_start_and_end():
    """A > 6-word passage uses textStart,textEnd and omits middle words."""
    url = build_text_fragment_url(
        "https://example.org/doc",
        "The quick brown fox jumped over the lazy dog.",
    )
    assert url is not None
    assert url.startswith("https://example.org/doc#:~:text=")
    decoded = unquote(url)
    # textStart,textEnd form: first 3 + last 3 words
    assert "text=The quick brown,the lazy dog." in decoded


def test_short_passage_uses_full_text_as_text_start():
    """A <= 6-word passage puts the whole passage in textStart, no textEnd."""
    url = build_text_fragment_url(
        "https://example.org/doc", "Quick brown fox jumps today"
    )
    assert url is not None
    decoded = unquote(url)
    # No comma inside ``text=`` body -> just textStart, no textEnd
    body = decoded.split("text=", 1)[1]
    assert "," not in body
    assert "Quick brown fox jumps today" in body


def test_exactly_six_words_treated_as_short():
    """Boundary: six words should use the full passage (not head/tail)."""
    url = build_text_fragment_url(
        "https://example.org/doc", "One two three four five six"
    )
    assert url is not None
    decoded = unquote(url)
    body = decoded.split("text=", 1)[1]
    assert body == "One two three four five six"


# ---------------------------------------------------------------------------
# Percent-encoding
# ---------------------------------------------------------------------------


def test_comma_is_percent_encoded_in_payload():
    """Commas within payload must be %2C so they aren't read as separators."""
    url = build_text_fragment_url(
        "https://example.org/doc",
        "Apples, oranges, bananas, and pears are fruit today.",
    )
    assert url is not None
    # textStart = 'Apples, oranges, bananas'
    # The literal comma must be encoded as %2C; the separator between
    # textStart and textEnd remains a literal comma.
    body = url.split("#:~:text=", 1)[1]
    # Split on literal ',' which the spec uses as a separator.
    segments = body.split(",")
    # 2 segments => textStart,textEnd; each MUST encode its internal commas
    assert all("," not in seg for seg in segments)
    assert "%2C" in body


def test_ampersand_plus_and_hyphen_are_percent_encoded():
    """``&`` (directive sep), ``+``, and ``-`` (affix marker) are encoded."""
    url = build_text_fragment_url(
        "https://example.org/doc",
        "alpha & beta + gamma - delta epsilon zeta eta",
    )
    assert url is not None
    body = url.split("#:~:text=", 1)[1]
    # No raw ``&`` or ``+`` should survive. A literal ``-`` in the payload
    # is dangerous (it's the prefix/suffix marker) -> must be encoded too.
    assert "&" not in body
    assert "+" not in body
    # The literal comma between textStart and textEnd is a separator, so
    # we look at each segment instead of the whole body.
    for seg in body.split(","):
        # Each segment may have the ``-`` marker only as its first or
        # last unencoded character (prefix-, or ,-suffix). We are not
        # using those here, so no literal ``-`` should appear.
        assert "-" not in seg


def test_spaces_encoded_as_percent_twenty():
    """Spaces MUST be %20 (not '+') to avoid ambiguity with urlencoded forms."""
    url = build_text_fragment_url(
        "https://example.org/doc", "two words here and there please"
    )
    assert url is not None
    body = url.split("#:~:text=", 1)[1]
    assert "%20" in body
    assert "+" not in body


# ---------------------------------------------------------------------------
# Prefix / suffix disambiguation
# ---------------------------------------------------------------------------


def test_text_before_produces_prefix_marker():
    """Non-empty text_before yields a ``prefix-,`` segment."""
    url = build_text_fragment_url(
        "https://example.org/doc",
        "the main cited passage here is longer than six words now",
        text_before="previously the author wrote that",
    )
    assert url is not None
    body = url.split("#:~:text=", 1)[1]
    # First segment should end with the affix marker ``-`` (unencoded).
    first = body.split(",", 1)[0]
    assert first.endswith("-")
    # And the prefix content should decode to last 3 words of text_before.
    decoded_prefix = unquote(first[:-1])
    assert decoded_prefix == "author wrote that"


def test_text_after_produces_suffix_marker():
    """Non-empty text_after yields a ``,-suffix`` segment at the end."""
    url = build_text_fragment_url(
        "https://example.org/doc",
        "the main cited passage here is longer than six words now",
        text_after=" and then the author continued",
    )
    assert url is not None
    body = url.split("#:~:text=", 1)[1]
    segments = body.split(",")
    # Last segment should start with affix marker ``-``.
    last = segments[-1]
    assert last.startswith("-")
    decoded_suffix = unquote(last[1:])
    assert decoded_suffix == "and then the"


def test_prefix_and_suffix_combined():
    """Both prefix and suffix populate together in the right positions."""
    url = build_text_fragment_url(
        "https://example.org/doc",
        "the main cited passage here is longer than six words now",
        text_before="the author wrote",
        text_after="and then continued",
    )
    assert url is not None
    body = url.split("#:~:text=", 1)[1]
    parts = body.split(",")
    # prefix-, textStart, textEnd, -suffix
    assert len(parts) == 4
    assert parts[0].endswith("-")
    assert parts[-1].startswith("-")


# ---------------------------------------------------------------------------
# None cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source_url",
    ["", None, "ftp://example.org/x", "file:///tmp/x", "mailto:a@b.c"],
)
def test_returns_none_for_bad_source_url(source_url):
    result = build_text_fragment_url(source_url, "a perfectly fine passage of words")
    assert result is None


def test_returns_none_for_empty_passage():
    assert build_text_fragment_url("https://example.org/doc", "") is None
    assert build_text_fragment_url("https://example.org/doc", "   ") is None


def test_returns_none_for_stopwords_only():
    """A passage that is all stopwords (< 3 meaningful words) returns None."""
    assert (
        build_text_fragment_url("https://example.org/doc", "the and of it is a an")
        is None
    )


def test_returns_none_for_too_few_meaningful_words():
    """Fewer than 3 non-stopword words -> None."""
    assert (
        build_text_fragment_url("https://example.org/doc", "the cat is") is None
    )  # only 'cat' is meaningful


# ---------------------------------------------------------------------------
# strip_fragment
# ---------------------------------------------------------------------------


def test_strip_fragment_removes_text_directive_bare():
    assert (
        strip_fragment("https://example.org/doc#:~:text=hello%20world")
        == "https://example.org/doc"
    )


def test_strip_fragment_preserves_existing_anchor():
    """Existing #anchor must survive when ``:~:`` follows it."""
    assert (
        strip_fragment("https://example.org/doc#section-3:~:text=hello")
        == "https://example.org/doc#section-3"
    )


def test_strip_fragment_passthrough_without_directive():
    assert (
        strip_fragment("https://example.org/doc#section-3")
        == "https://example.org/doc#section-3"
    )
    assert strip_fragment("https://example.org/doc") == "https://example.org/doc"
    assert strip_fragment("") == ""


def test_strip_fragment_is_idempotent():
    first = strip_fragment("https://example.org/doc#:~:text=foo")
    assert strip_fragment(first) == first


def test_build_preserves_existing_anchor():
    """Generation over a URL that already has an anchor keeps it and appends
    the ``:~:`` directive after the anchor (per spec)."""
    url = build_text_fragment_url(
        "https://example.org/doc#section-3",
        "The quick brown fox jumped over the lazy dog.",
    )
    assert url is not None
    assert url.startswith("https://example.org/doc#section-3:~:text=")


def test_build_strips_preexisting_text_directive():
    """Generation over a URL that already has a ``:~:text=`` directive
    replaces it rather than appending a second one."""
    url = build_text_fragment_url(
        "https://example.org/doc#:~:text=stale",
        "The quick brown fox jumped over the lazy dog.",
    )
    assert url is not None
    # Only one ``:~:`` occurrence survives.
    assert url.count(":~:") == 1
    assert "stale" not in url


# ---------------------------------------------------------------------------
# Integration with enhance.py
# ---------------------------------------------------------------------------


def test_enhance_integration_populates_fragment_url():
    """Running enhance.py on a small HTML fixture should populate
    ``target.fragment_url`` on the resulting VCITE objects, and the URL
    should decode to the expected head/tail words.
    """
    from enhance import _build_vcite_object
    from metadata import SourceMetadata
    from parsers.html_parser import ExtractedQuote

    quote = ExtractedQuote(
        text_exact=(
            "The network significantly improved retention of information "
            "across long documents in our study cohort."
        ),
        text_before="Prior work suggested otherwise; see also ",
        text_after=" (Smith 2021) and later replication studies.",
        citation_hint="Smith 2021",
        paragraph_context="",
        position=0,
    )
    meta = SourceMetadata(
        title="A Paper",
        authors=["Smith, J."],
        year=2021,
        doi="10.1234/abcd",
        url="https://journal.example.org/papers/abcd",
        venue="Journal",
        source_type="academic",
    )

    citation = _build_vcite_object(0, quote, meta)
    assert citation.target.fragment_url is not None
    url = citation.target.fragment_url
    assert url.startswith("https://journal.example.org/papers/abcd#:~:text=")
    decoded = unquote(url)
    # Head: first 3 words of text_exact
    assert "The network significantly" in decoded
    # Tail: last 3 words of text_exact (with punctuation)
    assert "our study cohort." in decoded


def test_enhance_integration_no_fragment_url_flag():
    """Passing generate_fragment_url=False leaves fragment_url unset."""
    from enhance import _build_vcite_object
    from metadata import SourceMetadata
    from parsers.html_parser import ExtractedQuote

    quote = ExtractedQuote(
        text_exact="A sufficiently long passage with several meaningful words.",
        text_before="",
        text_after="",
        citation_hint="",
        paragraph_context="",
        position=0,
    )
    meta = SourceMetadata(
        title="A Paper",
        authors=[],
        year=None,
        doi=None,
        url="https://example.org/a",
        venue=None,
        source_type="web",
    )

    citation = _build_vcite_object(0, quote, meta, generate_fragment_url=False)
    assert citation.target.fragment_url is None


def test_enhance_integration_doi_fallback():
    """When metadata.url is absent but DOI is, the fragment URL is built
    against https://doi.org/{doi}."""
    from enhance import _build_vcite_object
    from metadata import SourceMetadata
    from parsers.html_parser import ExtractedQuote

    quote = ExtractedQuote(
        text_exact="A sufficiently long passage with several meaningful words.",
        text_before="",
        text_after="",
        citation_hint="",
        paragraph_context="",
        position=0,
    )
    meta = SourceMetadata(
        title="A Paper",
        authors=[],
        year=None,
        doi="10.1234/xyz",
        url=None,
        venue=None,
        source_type="academic",
    )

    citation = _build_vcite_object(0, quote, meta)
    assert citation.target.fragment_url is not None
    assert citation.target.fragment_url.startswith(
        "https://doi.org/10.1234/xyz#:~:text="
    )
