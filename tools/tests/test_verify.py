"""Tests for the VCITE reverse-lookup verification pipeline.

Tests cover:
  - Source text extraction (HTML → plain text)
  - Passage search (exact, normalized, fuzzy)
  - Hash recomputation and comparison
  - Citation loading (JSON, JSON array, HTML with JSON-LD)
  - End-to-end offline verification
  - Output formatting
"""

import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add paths
TOOLS_DIR = Path(__file__).parent.parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "implementations" / "python"))
sys.path.insert(0, str(TOOLS_DIR))

from vcite import VCiteCitation, VCiteSource, VCiteTarget, compute_hash
from verify import (
    find_passage,
    verify_citation_offline,
    verify_citation,
    load_citations_from_json,
    load_citations_from_html,
    load_citations,
    format_result_text,
    format_summary,
    PassageMatch,
    VerificationResult,
)
from source_fetch import html_to_text, resolve_source_urls, FetchResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_citation(
    text_exact="over 70% of the URLs did not lead to originally cited information",
    text_before="As documented by Zittrain, ",
    text_after=". This rate of decay accelerates",
    url="https://example.com/paper",
    doi=None,
    archive_url=None,
    title="Test Paper",
    relation="supports",
    captured_by="author",
):
    """Helper to build a VCiteCitation for tests."""
    source = VCiteSource(
        title=title,
        authors=["Test, Author"],
        year=2024,
        doi=doi,
        url=url,
        archive_url=archive_url,
    )
    target = VCiteTarget(
        text_exact=text_exact,
        text_before=text_before,
        text_after=text_after,
    )
    return VCiteCitation(
        vcite="1.0",
        id="vcite-test0001",
        source=source,
        target=target,
        relation=relation,
        captured_at="2026-04-01T00:00:00Z",
        captured_by=captured_by,
    )


# ---------------------------------------------------------------------------
# HTML-to-text extraction
# ---------------------------------------------------------------------------

class TestHtmlToText:
    def test_basic_html(self):
        html = "<html><body><p>Hello world</p><p>Second paragraph</p></body></html>"
        text = html_to_text(html)
        assert "Hello world" in text
        assert "Second paragraph" in text

    def test_strips_script_and_style(self):
        html = "<p>Before</p><script>alert('x')</script><p>After</p>"
        text = html_to_text(html)
        assert "alert" not in text
        assert "Before" in text
        assert "After" in text

    def test_strips_nav_footer_header(self):
        html = "<nav>Navigation</nav><p>Content</p><footer>Footer</footer>"
        text = html_to_text(html)
        assert "Navigation" not in text
        assert "Content" in text
        assert "Footer" not in text

    def test_nested_skippable_tags(self):
        """Nested skip tags must not corrupt state (depth tracking)."""
        html = "<nav><script>var x = 1;</script>Nav text</nav><p>Content</p>"
        text = html_to_text(html)
        assert "var x" not in text
        assert "Nav text" not in text
        assert "Content" in text

    def test_html_entities(self):
        html = "<p>10 &gt; 5 &amp; 3 &lt; 7</p>"
        text = html_to_text(html)
        assert "10 > 5 & 3 < 7" in text

    def test_paragraph_boundaries(self):
        html = "<p>First</p><p>Second</p>"
        text = html_to_text(html)
        # Paragraphs should be separated
        assert "First" in text
        assert "Second" in text
        # They should not run together
        assert "FirstSecond" not in text


# ---------------------------------------------------------------------------
# URL scheme validation
# ---------------------------------------------------------------------------

class TestUrlSchemeValidation:
    def test_rejects_file_scheme(self):
        """file:// URLs must be rejected to prevent local file reads."""
        from source_fetch import _fetch_url
        result = _fetch_url("file:///etc/passwd")
        assert result.error
        assert "non-HTTP" in result.error

    def test_rejects_ftp_scheme(self):
        from source_fetch import _fetch_url
        result = _fetch_url("ftp://example.com/file")
        assert result.error
        assert "non-HTTP" in result.error


# ---------------------------------------------------------------------------
# Passage search
# ---------------------------------------------------------------------------

class TestFindPassage:
    def test_exact_match(self):
        source = "Before text. The exact passage we are looking for. After text."
        citation = _make_citation(
            text_exact="The exact passage we are looking for"
        )
        match = find_passage(source, citation)
        assert match.found
        assert match.match_type == "exact"
        assert match.similarity == 1.0
        assert "The exact passage we are looking for" in match.matched_text

    def test_exact_match_with_whitespace_normalization(self):
        source = "Before.  The   exact   passage   here. After."
        citation = _make_citation(
            text_exact="The exact passage here"
        )
        match = find_passage(source, citation)
        assert match.found
        assert match.match_type == "exact"

    def test_case_insensitive_match(self):
        source = "Before. THE EXACT PASSAGE IN CAPS. After."
        citation = _make_citation(
            text_exact="the exact passage in caps"
        )
        match = find_passage(source, citation)
        assert match.found
        assert match.match_type == "normalized"

    def test_no_match(self):
        source = "This source text contains completely different content."
        citation = _make_citation(
            text_exact="A passage that does not exist in the source at all"
        )
        match = find_passage(source, citation)
        assert not match.found

    def test_context_extraction(self):
        before_ctx = "X" * 60  # more than 50 chars
        after_ctx = "Y" * 60
        source = f"{before_ctx}TARGET PASSAGE{after_ctx}"
        citation = _make_citation(text_exact="TARGET PASSAGE")
        match = find_passage(source, citation)
        assert match.found
        assert len(match.context_before) <= 50
        assert len(match.context_after) <= 50

    def test_empty_text_exact(self):
        citation = _make_citation(text_exact="")
        match = find_passage("some source text", citation)
        assert not match.found

    def test_unicode_passage(self):
        source = "Les donn\u00e9es \u00e0 caract\u00e8re personnel doivent \u00eatre prot\u00e9g\u00e9es."
        citation = _make_citation(
            text_exact="donn\u00e9es \u00e0 caract\u00e8re personnel"
        )
        match = find_passage(source, citation)
        assert match.found
        assert match.match_type == "exact"

    def test_fuzzy_match(self):
        # Source has slight differences from cited text
        source = ("Before context. " +
                  "The research found that approximately seventy percent of "
                  "URLs in academic articles were broken or inaccessible." +
                  " After context.")
        citation = _make_citation(
            text_exact=(
                "The research found that approximately seventy percent of "
                "URLs in academic articles were broken or inaccessble"  # typo
            )
        )
        match = find_passage(source, citation)
        assert match.found
        assert match.match_type == "fuzzy"
        assert match.similarity >= 0.85


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------

class TestResolveSourceUrls:
    def test_url_only(self):
        citation = _make_citation(url="https://example.com/paper")
        urls = resolve_source_urls(citation)
        assert "https://example.com/paper" in urls

    def test_doi_only(self):
        citation = _make_citation(url=None, doi="10.1234/test")
        urls = resolve_source_urls(citation)
        assert "https://doi.org/10.1234/test" in urls

    def test_archive_url_first(self):
        citation = _make_citation(
            url="https://example.com/paper",
            archive_url="https://web.archive.org/web/2024/https://example.com/paper",
        )
        urls = resolve_source_urls(citation)
        assert urls[0] == "https://web.archive.org/web/2024/https://example.com/paper"

    def test_all_urls(self):
        citation = _make_citation(
            url="https://example.com/paper",
            doi="10.1234/test",
            archive_url="https://perma.cc/XXXX-YYYY",
        )
        urls = resolve_source_urls(citation)
        assert len(urls) == 3
        # Archive first
        assert urls[0] == "https://perma.cc/XXXX-YYYY"

    def test_no_urls(self):
        citation = _make_citation(url=None, doi=None, archive_url=None)
        urls = resolve_source_urls(citation)
        assert urls == []

    def test_deduplication(self):
        citation = _make_citation(
            url="https://doi.org/10.1234/test",
            doi="10.1234/test",
        )
        urls = resolve_source_urls(citation)
        # DOI URL should not appear twice
        doi_urls = [u for u in urls if "10.1234/test" in u]
        assert len(doi_urls) == 1


# ---------------------------------------------------------------------------
# Offline verification
# ---------------------------------------------------------------------------

class TestVerifyCitationOffline:
    def test_valid_citation(self):
        citation = _make_citation()
        result = verify_citation_offline(citation)
        assert result.status == "verified"
        assert result.internal_hash_valid is True
        assert result.citation_id == "vcite-test0001"

    def test_tampered_hash(self):
        citation = _make_citation()
        # Tamper with the hash
        citation.target.hash = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        result = verify_citation_offline(citation)
        assert result.status == "hash_mismatch"
        assert result.internal_hash_valid is False

    def test_model_without_archive_url_warns(self):
        citation = _make_citation(captured_by="model", archive_url=None)
        result = verify_citation_offline(citation)
        assert any("archive_url" in w for w in result.warnings)

    def test_l1_citation_warns(self):
        citation = _make_citation(
            text_before="", text_after="", url=None, doi=None
        )
        result = verify_citation_offline(citation)
        assert result.conformance_level == 1
        assert any("L1" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Online verification (mocked)
# ---------------------------------------------------------------------------

class TestVerifyCitation:
    def test_verified_with_matching_source(self):
        """Full verification succeeds when source contains the passage."""
        citation = _make_citation(
            text_exact="the passage we cited",
            text_before="Before context for ",
            text_after=". After the cited passage",
        )

        # Build source text that contains the passage with same context
        source_text = "Before context for the passage we cited. After the cited passage and more."

        with patch("verify.fetch_source") as mock_fetch:
            mock_fetch.return_value = FetchResult(
                text=source_text,
                url="https://example.com/paper",
                content_type="text/html",
            )
            result = verify_citation(citation)

        assert result.status in ("verified", "passage_verified")
        assert result.internal_hash_valid is True
        assert result.passage_match.found is True

    def test_source_unavailable(self):
        citation = _make_citation()
        with patch("verify.fetch_source") as mock_fetch:
            mock_fetch.return_value = FetchResult(
                text="", url="https://example.com",
                content_type="", error="HTTP 404: Not Found"
            )
            result = verify_citation(citation)

        assert result.status == "source_unavailable"
        assert "404" in result.fetch_error

    def test_passage_not_found_in_source(self):
        citation = _make_citation(
            text_exact="A very specific passage that won't be in the source"
        )
        with patch("verify.fetch_source") as mock_fetch:
            mock_fetch.return_value = FetchResult(
                text="Completely different source content with no matching text.",
                url="https://example.com",
                content_type="text/html",
            )
            result = verify_citation(citation)

        assert result.status == "passage_not_found"

    def test_insufficient_metadata(self):
        citation = _make_citation(url=None, doi=None, archive_url=None)
        result = verify_citation(citation)
        assert result.status == "insufficient_metadata"


# ---------------------------------------------------------------------------
# Citation loading
# ---------------------------------------------------------------------------

class TestLoadCitations:
    def test_load_single_json(self, tmp_path):
        citation = _make_citation()
        path = tmp_path / "citation.json"
        path.write_text(citation.to_json())
        loaded = load_citations_from_json(path)
        assert len(loaded) == 1
        assert loaded[0].id == "vcite-test0001"

    def test_load_json_array(self, tmp_path):
        c1 = _make_citation()
        c2 = _make_citation()
        c2.id = "vcite-test0002"
        data = [c1.to_dict(), c2.to_dict()]
        path = tmp_path / "citations.json"
        path.write_text(json.dumps(data))
        loaded = load_citations_from_json(path)
        assert len(loaded) == 2

    def test_load_from_html_jsonld(self, tmp_path):
        citation = _make_citation()
        jsonld = citation.to_jsonld()
        html = f"""
        <html><head>
        <script type="application/ld+json">
        [{json.dumps(jsonld)}]
        </script>
        </head><body><p>Article text</p></body></html>
        """
        path = tmp_path / "article.html"
        path.write_text(html)
        loaded = load_citations_from_html(path)
        assert len(loaded) == 1
        assert loaded[0].id == "vcite-test0001"

    def test_load_auto_detect_json(self, tmp_path):
        citation = _make_citation()
        path = tmp_path / "test.json"
        path.write_text(citation.to_json())
        loaded = load_citations(path)
        assert len(loaded) == 1

    def test_load_auto_detect_html(self, tmp_path):
        citation = _make_citation()
        jsonld = citation.to_jsonld()
        html = f"""
        <html><head>
        <script type="application/ld+json">[{json.dumps(jsonld)}]</script>
        </head><body></body></html>
        """
        path = tmp_path / "test.html"
        path.write_text(html)
        loaded = load_citations(path)
        assert len(loaded) == 1

    def test_load_katina_example(self):
        """Smoke test: load the real Katina article HTML."""
        katina_path = REPO_ROOT / "examples" / "katina-article.html"
        if not katina_path.exists():
            pytest.skip("Katina example not found")
        loaded = load_citations_from_html(katina_path)
        assert len(loaded) == 21  # known count (incl. first-paragraph Savage)
        assert all(c.verify() for c in loaded), "All Katina citations should pass internal hash check"


# ---------------------------------------------------------------------------
# Hash recomputation against source text
# ---------------------------------------------------------------------------

class TestHashRecomputation:
    def test_matching_hash_when_context_identical(self):
        """When source context matches citation context, hashes should match.

        The source text is constructed so the 50-char context windows
        extracted by find_passage exactly match the citation context
        (padded to 50 code points by the hash algorithm).
        """
        text_exact = "this is the cited passage"
        # Pad before/after to exactly 50 chars so extraction matches
        text_before = ("X" * 30) + "some context before "  # 50 chars
        text_after = " some context after" + ("Y" * 31)     # 50 chars

        # Compute the expected hash
        expected_hash = compute_hash(text_exact, text_before, text_after)

        # Create citation with this hash
        source = VCiteSource(title="Test", url="https://example.com")
        target = VCiteTarget(
            text_exact=text_exact,
            text_before=text_before,
            text_after=text_after,
        )
        assert target.hash == expected_hash  # auto-computed

        # Build source text: the 50-char windows around the passage exactly
        # match what the citation recorded, so hashes should be identical.
        source_text = f"{text_before}{text_exact}{text_after}"
        citation = VCiteCitation(
            vcite="1.0", id="vcite-00000001", source=source, target=target,
            relation="supports", captured_at="2026-01-01T00:00:00Z",
            captured_by="author",
        )
        match = find_passage(source_text, citation)
        assert match.found

        # Recompute hash from what was found in source
        recomputed = compute_hash(
            match.matched_text, match.context_before, match.context_after
        )
        assert recomputed == expected_hash

    def test_different_context_different_hash(self):
        """When source context differs from citation context, hashes differ."""
        text_exact = "the cited passage"

        # Citation was created with one context
        citation_hash = compute_hash(text_exact, "author saw this ", " author saw after")

        # Source has different surrounding text
        source_text = "different before the cited passage different after"
        citation = _make_citation(text_exact=text_exact)
        citation.target.hash = citation_hash
        citation.target.text_before = "author saw this "
        citation.target.text_after = " author saw after"

        match = find_passage(source_text, citation)
        assert match.found

        # Recompute from source context
        recomputed = compute_hash(
            match.matched_text, match.context_before, match.context_after
        )
        # Hashes will differ because context differs
        assert recomputed != citation_hash


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

class TestFormatting:
    def test_format_result_text(self):
        result = VerificationResult(
            citation_id="vcite-001",
            source_title="Test Paper",
            status="verified",
            internal_hash_valid=True,
            conformance_level=2,
            relation="supports",
            captured_by="author",
        )
        text = format_result_text(result)
        assert "vcite-001" in text
        assert "VERIFIED" in text
        assert "Test Paper" in text

    def test_format_summary(self):
        results = [
            VerificationResult(
                citation_id="v1", source_title="P1",
                status="verified", internal_hash_valid=True,
            ),
            VerificationResult(
                citation_id="v2", source_title="P2",
                status="passage_not_found", internal_hash_valid=True,
            ),
        ]
        summary = format_summary(results)
        assert "2 citations checked" in summary
        assert "1 fully verified" in summary
        assert "1 passage not found" in summary

    def test_result_to_dict(self):
        result = VerificationResult(
            citation_id="vcite-001",
            source_title="Test",
            status="verified",
            internal_hash_valid=True,
        )
        d = result.to_dict()
        assert d["citation_id"] == "vcite-001"
        assert d["status"] == "verified"
        # Empty strings and None should be stripped
        assert "fetch_error" not in d
        assert "source_hash_recomputed" not in d
