"""Tests for the VCITE data model (spec §4)."""

import json

import pytest

from vcite.hash import compute_hash
from vcite.models import VCiteCitation, VCiteSource, VCiteTarget


def _make_citation(**overrides) -> VCiteCitation:
    """Helper to build a valid VCiteCitation with sensible defaults."""
    defaults = dict(
        vcite="1.0",
        id="test-001",
        source=VCiteSource(
            title="Test Paper",
            authors=["Author, A."],
            year=2025,
            doi="10.1234/test",
            url="https://example.com/paper",
        ),
        target=VCiteTarget(
            text_exact="exactly 42%",
            text_before="The rate is ",
            text_after=" as measured",
        ),
        relation="supports",
        captured_at="2026-04-08T12:00:00Z",
        captured_by="author",
    )
    defaults.update(overrides)
    return VCiteCitation(**defaults)


class TestVCiteTarget:
    """VCiteTarget auto-computes hash on creation."""

    def test_auto_hash(self):
        t = VCiteTarget(
            text_exact="exactly 42%",
            text_before="The rate is ",
            text_after=" as measured",
        )
        expected = compute_hash("exactly 42%", "The rate is ", " as measured")
        assert t.hash == expected

    def test_preserves_explicit_hash(self):
        t = VCiteTarget(
            text_exact="test",
            hash="sha256:explicit",
        )
        assert t.hash == "sha256:explicit"


class TestVCiteCitationCreation:
    """VCiteCitation validates on creation."""

    def test_valid_creation(self):
        c = _make_citation()
        assert c.id == "test-001"
        assert c.relation == "supports"

    def test_invalid_relation_raises(self):
        with pytest.raises(ValueError, match="Invalid relation"):
            _make_citation(relation="approves")

    def test_extension_relation_allowed(self):
        c = _make_citation(relation="x-custom")
        assert c.relation == "x-custom"

    def test_invalid_captured_by_raises(self):
        with pytest.raises(ValueError, match="captured_by must be"):
            _make_citation(captured_by="robot")

    def test_all_valid_relations(self):
        for rel in ("supports", "contradicts", "defines", "quantifies",
                     "contextualizes", "method", "cautions"):
            c = _make_citation(relation=rel)
            assert c.relation == rel


class TestSerialization:
    """Round-trip serialization: to_dict/from_dict, to_json/from_json."""

    def test_to_dict_strips_none(self):
        c = _make_citation(enrichment=None)
        d = c.to_dict()
        assert "enrichment" not in d

    def test_to_dict_preserves_values(self):
        c = _make_citation()
        d = c.to_dict()
        assert d["vcite"] == "1.0"
        assert d["id"] == "test-001"
        assert d["source"]["title"] == "Test Paper"
        assert d["target"]["text_exact"] == "exactly 42%"

    def test_to_json_from_json_roundtrip(self):
        original = _make_citation()
        json_str = original.to_json()
        restored = VCiteCitation.from_json(json_str)
        assert restored.id == original.id
        assert restored.vcite == original.vcite
        assert restored.source.title == original.source.title
        assert restored.target.text_exact == original.target.text_exact
        assert restored.target.hash == original.target.hash
        assert restored.relation == original.relation
        assert restored.captured_at == original.captured_at
        assert restored.captured_by == original.captured_by

    def test_from_dict(self):
        d = {
            "vcite": "1.0",
            "id": "from-dict-001",
            "source": {"title": "Dict Source", "authors": ["B, C."]},
            "target": {
                "text_exact": "test passage",
                "hash": "sha256:abc",
                "text_before": "",
                "text_after": "",
            },
            "relation": "defines",
            "captured_at": "2026-01-01T00:00:00Z",
            "captured_by": "model",
        }
        c = VCiteCitation.from_dict(d)
        assert c.id == "from-dict-001"
        assert c.source.title == "Dict Source"
        assert c.target.hash == "sha256:abc"

    def test_to_json_valid_json(self):
        c = _make_citation()
        parsed = json.loads(c.to_json())
        assert isinstance(parsed, dict)


class TestJsonLD:
    """JSON-LD output includes @context and @type."""

    def test_context_present(self):
        c = _make_citation()
        ld = c.to_jsonld()
        assert ld["@context"] == "https://vcite.pub/ns/v1/"

    def test_type_present(self):
        c = _make_citation()
        ld = c.to_jsonld()
        assert ld["@type"] == "VCiteCitation"

    def test_data_preserved(self):
        c = _make_citation()
        ld = c.to_jsonld()
        assert ld["id"] == "test-001"
        assert ld["source"]["title"] == "Test Paper"


class TestVerify:
    """Hash verification detects valid and tampered citations."""

    def test_valid_hash_verifies(self):
        c = _make_citation()
        assert c.verify() is True

    def test_tampered_text_fails(self):
        c = _make_citation()
        c.target.text_exact = "exactly 43%"  # tamper
        assert c.verify() is False

    def test_tampered_context_fails(self):
        c = _make_citation()
        c.target.text_before = "The rate was "  # tamper
        assert c.verify() is False

    def test_explicit_wrong_hash_fails(self):
        c = _make_citation()
        c.target.hash = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        assert c.verify() is False


class TestConformanceLevel:
    """Conformance level detection (L1, L2, L3)."""

    def test_l1_minimal(self):
        c = _make_citation(
            source=VCiteSource(title="Minimal"),
            target=VCiteTarget(text_exact="test"),
        )
        assert c.conformance_level == 1

    def test_l2_with_context_and_url(self):
        c = _make_citation(
            source=VCiteSource(
                title="Standard",
                url="https://example.com",
            ),
            target=VCiteTarget(
                text_exact="test",
                text_before="before ",
                text_after=" after",
            ),
        )
        assert c.conformance_level == 2

    def test_l2_with_context_and_doi(self):
        c = _make_citation(
            source=VCiteSource(
                title="Standard DOI",
                doi="10.1234/test",
            ),
            target=VCiteTarget(
                text_exact="test",
                text_before="before ",
                text_after=" after",
            ),
        )
        assert c.conformance_level == 2

    def test_l3_with_archive_and_fragment(self):
        c = _make_citation(
            source=VCiteSource(
                title="Enhanced",
                url="https://example.com",
                archive_url="https://web.archive.org/web/2025/https://example.com",
            ),
            target=VCiteTarget(
                text_exact="test",
                text_before="before ",
                text_after=" after",
                fragment_url="https://example.com#:~:text=test",
            ),
        )
        assert c.conformance_level == 3

    def test_l1_without_source_url(self):
        """Context alone without source URL/DOI does not qualify for L2."""
        c = _make_citation(
            source=VCiteSource(title="No URL"),
            target=VCiteTarget(
                text_exact="test",
                text_before="before ",
                text_after=" after",
            ),
        )
        assert c.conformance_level == 1

    def test_l2_without_archive_stays_l2(self):
        """archive_url without fragment_url does not qualify for L3."""
        c = _make_citation(
            source=VCiteSource(
                title="Has Archive",
                url="https://example.com",
                archive_url="https://web.archive.org/web/2025/https://example.com",
            ),
            target=VCiteTarget(
                text_exact="test",
                text_before="before ",
                text_after=" after",
            ),
        )
        assert c.conformance_level == 2
