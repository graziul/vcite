"""Smoke tests for the renderer's handling of enrichment badges.

These cover the Phase 1 work that wires ``enrichment.verification`` (and,
when present, ``enrichment.strain``) into the rendered panel. Panels
without enrichment must still render (backward compat); panels with
enrichment must show the appropriate badge copy and detail rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "implementations" / "python"))
sys.path.insert(0, str(ROOT / "tools"))

from vcite import VCiteCitation, VCiteSource, VCiteTarget  # noqa: E402
from renderer import build_evidence_panel  # noqa: E402


def _make_citation(enrichment=None) -> VCiteCitation:
    return VCiteCitation(
        vcite="1.0",
        id="vcite-test",
        source=VCiteSource(
            title="Test Source",
            authors=["Doe, J."],
            year=2024,
            url="https://example.org/src",
            source_type="academic",
        ),
        target=VCiteTarget(
            text_exact="The passage we are citing.",
            text_before="Before. ",
            text_after=" After.",
        ),
        relation="supports",
        captured_at="2026-04-22T00:00:00Z",
        captured_by="author",
        enrichment=enrichment,
    )


class _Quote:
    def __init__(self, text_exact):
        self.text_exact = text_exact
        self.text_before = ""
        self.text_after = ""
        self.citation_hint = ""
        self.paragraph_context = ""
        self.position = 0


def _render(citation: VCiteCitation) -> str:
    return build_evidence_panel(citation, _Quote(citation.target.text_exact))


def test_panel_renders_without_enrichment():
    html = _render(_make_citation())
    # Backward compat: no enrichment fields, no badges, no details block.
    assert "vcite-verify" not in html
    assert "vcite-strain" not in html
    assert "vcite-enrichment" not in html
    # Core panel content still present.
    assert "vcite-fingerprint-label" in html
    assert "vcite-source-title" in html


def test_panel_shows_source_verified_badge():
    enrichment = {
        "verification": {
            "status": "verified",
            "internal_hash_valid": True,
            "source_hash_valid": True,
            "match_type": "exact",
            "match_similarity": 1.0,
            "checked_at": "2026-04-22T10:15:00Z",
            "source_checked_url": "https://example.org/src",
        }
    }
    html = _render(_make_citation(enrichment=enrichment))
    assert "vcite-verify--ok" in html
    assert "Source-verified" in html
    assert "2026-04-22" in html
    # Details block lists the source URL and match type.
    assert "vcite-enrichment" in html
    assert "https://example.org/src" in html
    assert ">exact<" in html or "exact" in html


def test_panel_distinguishes_offline_internal_only():
    """Offline verify uses internal-only status so we never claim "source-verified"
    when the source was never consulted."""
    enrichment = {
        "verification": {
            "status": "internal-only",
            "internal_hash_valid": True,
            "checked_at": "2026-04-22T10:15:00Z",
        }
    }
    html = _render(_make_citation(enrichment=enrichment))
    assert "vcite-verify--info" in html
    assert "Internal hash OK" in html
    assert "Source-verified" not in html


def test_panel_flags_source_drift():
    enrichment = {
        "verification": {
            "status": "source-drift",
            "internal_hash_valid": True,
            "source_hash_valid": False,
            "match_type": "fuzzy",
            "match_similarity": 0.87,
            "source_hash_recomputed": "sha256:abcd",
            "checked_at": "2026-04-22T10:15:00Z",
            "source_checked_url": "https://example.org/src",
        }
    }
    html = _render(_make_citation(enrichment=enrichment))
    assert "vcite-verify--drift" in html
    assert "Source drift" in html
    # Detail block must call out the differing recomputed hash.
    assert "differs" in html.lower()
    assert "sha256:abcd" in html


def test_panel_flags_unreachable_source():
    enrichment = {
        "verification": {
            "status": "unreachable",
            "internal_hash_valid": True,
            "fetch_error": "HTTP 403",
            "checked_at": "2026-04-22T10:15:00Z",
        }
    }
    html = _render(_make_citation(enrichment=enrichment))
    assert "vcite-verify--muted" in html
    assert "Source unreachable" in html


def test_panel_shows_strain_badge_when_present():
    enrichment = {
        "strain": {
            "score": 0.18,
            "band": "low",
            "method": "lexical",
            "calibrated": True,
            "discipline": "social_science",
            "components": {
                "jaccard_overlap": 0.92,
                "rouge_l": 0.88,
                "idf_overlap": 0.85,
                "bigram_divergence": 0.05,
            },
            "claiming_context": "Surrounding article sentence here.",
            "assessed_at": "2026-04-22T10:15:00Z",
        }
    }
    html = _render(_make_citation(enrichment=enrichment))
    assert "vcite-strain--ok" in html
    assert "Low claim distance" in html
    assert "0.18" in html
    # Detail block lists the claiming context.
    assert "Surrounding article sentence here." in html


def test_panel_handles_both_verification_and_strain():
    enrichment = {
        "verification": {
            "status": "verified",
            "internal_hash_valid": True,
            "source_hash_valid": True,
            "checked_at": "2026-04-22",
        },
        "strain": {
            "score": 0.42,
            "band": "moderate",
            "method": "lexical",
        },
    }
    html = _render(_make_citation(enrichment=enrichment))
    assert "Source-verified" in html
    assert "Moderate claim distance" in html
    # Both details rendered in the collapsible block.
    assert html.count("vcite-enrichment-dl") == 1


def test_strain_tooltip_notes_lexical_only_caveat():
    enrichment = {
        "strain": {
            "score": 0.5,
            "band": "moderate",
            "method": "lexical",
        }
    }
    html = _render(_make_citation(enrichment=enrichment))
    assert "does not certify claim validity" in html


# ---------------------------------------------------------------------------
# Re-enhancement: stripping old VCITE markup must handle bundled IIFE bodies
# ---------------------------------------------------------------------------


def test_re_enhancement_strips_script_bodies_containing_angle_brackets():
    """Regression: _strip_existing_vcite previously used a [^<]* regex that
    failed to match script blocks whose body contains '<' characters (e.g.,
    bundled IIFEs with comparisons, arrow fns, or embedded JSON). Multiple
    runs of the renderer accumulated duplicate toggleVcite definitions in
    the rendered HTML.
    """
    from renderer import render_enhanced_html
    fragment = (
        "<html><head></head><body>"
        "<script>\n"
        "function toggleVcite(el) {\n"
        "  if (el.idx < 10) return;  // angle bracket in body\n"
        "  var s = '<!-- comment -->';\n"
        "}\n"
        "</script>"
        "<p>A passage to verify here.</p>"
        "</body></html>"
    )
    c = _make_citation()
    quote = _Quote("A passage to verify here.")
    out = render_enhanced_html(fragment, [quote], [c])
    # Exactly one definition of toggleVcite must remain (the freshly injected one).
    assert out.count("function toggleVcite") == 1


def test_re_enhancement_strips_bundled_iife():
    """attachVerifyButtons IIFE must also be stripped on re-render."""
    from renderer import render_enhanced_html
    fragment = (
        "<html><head></head><body>"
        "<script>\n"
        "(function () {\n"
        "  function attachVerifyButtons(doc) { /* old version */ }\n"
        "  for (var i = 0; i < 5; i++) {}\n"
        "})();\n"
        "</script>"
        "<p>A passage to verify here.</p>"
        "</body></html>"
    )
    c = _make_citation()
    quote = _Quote("A passage to verify here.")
    out = render_enhanced_html(fragment, [quote], [c])
    # Exactly one attachVerifyButtons definition (from the freshly-injected IIFE).
    assert out.count("function attachVerifyButtons") == 1
