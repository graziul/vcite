"""Smoke tests for tools/enrich.py — the orchestrator that runs
verification (and optionally strain) on VCITE citations and writes the
results into each citation's ``enrichment`` field.

These tests cover the offline / internal-only path end-to-end. Online
verification is exercised by ``test_verify.py`` and is not re-tested
here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "implementations" / "python"))
sys.path.insert(0, str(ROOT / "tools"))

from vcite import VCiteCitation, VCiteSource, VCiteTarget  # noqa: E402
from enrich import (  # noqa: E402
    enrich_citations,
    _build_verification_enrichment,
    _verification_status,
)
from verify import verify_citation_offline  # noqa: E402


def _make_citation(**kwargs):
    defaults = dict(
        vcite="1.0",
        id="vcite-test",
        source=VCiteSource(title="Test", authors=["Doe"], year=2024,
                           url="https://example.org/x"),
        target=VCiteTarget(text_exact="Hello world passage text."),
        relation="supports",
        captured_at="2026-04-22T00:00:00Z",
        captured_by="author",
    )
    defaults.update(kwargs)
    return VCiteCitation(**defaults)


# ---------------------------------------------------------------------------
# _verification_status mapping
# ---------------------------------------------------------------------------


class TestVerificationStatusMapping:
    def test_offline_valid_hash_is_internal_only(self):
        c = _make_citation()
        r = verify_citation_offline(c)
        assert r.internal_hash_valid is True
        assert _verification_status(r, source_consulted=False) == "internal-only"

    def test_offline_broken_hash_is_internal_mismatch(self):
        c = _make_citation()
        c.target.hash = "sha256:deadbeef"
        r = verify_citation_offline(c)
        assert _verification_status(r, source_consulted=False) == "internal-mismatch"

    def test_source_consulted_with_online_verified_status(self):
        # Synthesize a VerificationResult-shape object since we can't hit the
        # network in a unit test. The mapping is a pure function of the fields.
        from verify import VerificationResult
        r = VerificationResult(
            citation_id="x", source_title="x",
            status="verified", internal_hash_valid=True,
            source_hash_valid=True,
        )
        assert _verification_status(r, source_consulted=True) == "verified"

    def test_source_consulted_passage_not_found_is_partial(self):
        from verify import VerificationResult
        r = VerificationResult(
            citation_id="x", source_title="x",
            status="passage_not_found", internal_hash_valid=True,
        )
        assert _verification_status(r, source_consulted=True) == "partial"

    def test_source_unavailable_is_unreachable(self):
        from verify import VerificationResult
        r = VerificationResult(
            citation_id="x", source_title="x",
            status="source_unavailable", internal_hash_valid=True,
        )
        assert _verification_status(r, source_consulted=True) == "unreachable"


# ---------------------------------------------------------------------------
# _build_verification_enrichment shape
# ---------------------------------------------------------------------------


class TestEnrichmentShape:
    def test_offline_enrichment_minimal_shape(self):
        c = _make_citation()
        r = verify_citation_offline(c)
        enr = _build_verification_enrichment(r, source_consulted=False)
        assert enr["status"] == "internal-only"
        assert enr["internal_hash_valid"] is True
        assert "checked_at" in enr
        # No source fields when we didn't consult the source.
        assert "source_checked_url" not in enr
        assert "match_type" not in enr


# ---------------------------------------------------------------------------
# enrich_citations orchestrator
# ---------------------------------------------------------------------------


class TestEnrichCitations:
    def test_offline_verify_writes_enrichment(self):
        citations = [_make_citation(id=f"vcite-{i:03d}") for i in range(3)]
        enrich_citations(
            citations, do_verify=True, do_strain=False, offline=True,
        )
        for c in citations:
            assert c.enrichment is not None
            assert "verification" in c.enrichment
            assert c.enrichment["verification"]["status"] == "internal-only"

    def test_enrich_preserves_existing_enrichment(self):
        c = _make_citation(enrichment={"x-custom": "keep-me"})
        enrich_citations([c], do_verify=True, do_strain=False, offline=True)
        assert c.enrichment.get("x-custom") == "keep-me"
        assert "verification" in c.enrichment


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


class TestCli:
    def test_cli_offline_verify_roundtrip(self, tmp_path):
        src = [{
            "vcite": "1.0",
            "id": "vcite-001",
            "source": {"title": "S", "authors": ["Doe"], "year": 2024,
                       "url": "https://example.org/x"},
            "target": {
                "text_exact": "A passage to hash.",
                "text_before": "",
                "text_after": "",
                "hash": VCiteTarget(text_exact="A passage to hash.").hash,
            },
            "relation": "supports",
            "captured_at": "2026-04-22T00:00:00Z",
            "captured_by": "author",
        }]
        input_path = tmp_path / "cites.json"
        output_path = tmp_path / "cites.enriched.json"
        input_path.write_text(json.dumps(src), encoding="utf-8")

        cli = ROOT / "tools" / "enrich.py"
        result = subprocess.run(
            [sys.executable, str(cli),
             str(input_path), "--verify", "--offline",
             "-o", str(output_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert output_path.exists()

        out = json.loads(output_path.read_text())
        assert len(out) == 1
        assert out[0]["enrichment"]["verification"]["status"] == "internal-only"
        assert out[0]["enrichment"]["verification"]["internal_hash_valid"] is True

    def test_cli_errors_without_any_action_flag(self, tmp_path):
        input_path = tmp_path / "x.json"
        input_path.write_text("[]", encoding="utf-8")
        cli = ROOT / "tools" / "enrich.py"
        result = subprocess.run(
            [sys.executable, str(cli), str(input_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        assert "Nothing to do" in result.stderr
