#!/usr/bin/env python3
"""Run verification (and optionally strain) on VCITE citations and write
the results into each citation object's ``enrichment`` field.

The branch that introduced reverse-lookup + strain added the machinery but
never connected it to the rendered output. This script closes that loop:
run the analysis once, persist the results in-band on the citation object,
and let the renderer surface them as badges without re-running anything.

Enrichment schema (additive; renderer tolerates absence):

    enrichment:
      verification:
        status: verified | source-drift | partial | unreachable |
                internal-mismatch | not-checked
        internal_hash_valid: bool
        source_hash_valid: bool | null
        match_type: exact | normalized | fuzzy | null
        match_similarity: float     # 0.0-1.0
        source_hash_recomputed: str
        source_checked_url: str
        checked_at: ISO-8601 UTC
        warnings: [str]
      strain:
        score: float                # 0.0 (faithful) - 1.0 (distorted)
        band: low | moderate | high | extreme
        method: lexical | embedding | nli | ensemble
        calibrated: bool
        discipline: str
        components: {...}
        claiming_context: str
        assessed_at: ISO-8601 UTC

Usage:
    # Run verification + strain, write back in place
    python tools/enrich.py examples/katina-citations.json --verify --strain

    # Verification only (no network for strain), write to a new file
    python tools/enrich.py examples/katina-citations.json --verify \\
        -o examples/katina-citations.enriched.json

    # Offline run (skip source fetch — only internal hash + strain)
    python tools/enrich.py examples/katina-citations.json --strain --offline

    # HTML input: enriches embedded JSON-LD, rewrites the file
    python tools/enrich.py examples/katina-article.html --verify --strain
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

TOOLS_DIR = Path(__file__).parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "implementations" / "python"))
sys.path.insert(0, str(TOOLS_DIR))

from vcite import VCiteCitation
from verify import (
    load_citations,
    verify_citation,
    verify_citation_offline,
    VerificationResult,
)

# Strain is a research prototype — soft import so enrich works even if
# strain modules are missing or their optional deps unavailable.
try:
    from strain.scorer import (
        compute_local_strain,
        extract_claiming_context,
        classify_strain,
        LocalStrain,
    )
    from strain.calibration import calibrate_score
    _STRAIN_AVAILABLE = True
except Exception as _e:  # pragma: no cover
    _STRAIN_AVAILABLE = False
    _STRAIN_IMPORT_ERROR = str(_e)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Verification → enrichment
# ---------------------------------------------------------------------------


def _verification_status(result: VerificationResult, source_consulted: bool) -> str:
    """Collapse verify.py's status vocabulary into badge-ready buckets.

    ``source_consulted`` reflects whether the runner actually attempted to
    fetch and compare against the source. verify_citation_offline() returns
    status="verified" based on the internal hash alone, which would mislead
    the reader; we re-label that case as "internal-only".
    """
    if not result.internal_hash_valid:
        return "internal-mismatch"

    if not source_consulted:
        return "internal-only"

    s = result.status
    # Source fetched, passage found byte-exact, source hash matches.
    if s == "verified":
        return "verified"
    # Source fetched, passage found, but hash changed since capture.
    if s == "hash_mismatch":
        return "source-drift"
    # Passage found but context differs / fuzzy.
    if s == "passage_verified":
        return "partial"
    # Source reached but passage not present.
    if s == "passage_not_found":
        return "partial"
    # Could not retrieve the source at all.
    if s in ("source_unavailable", "insufficient_metadata"):
        return "unreachable"
    return "unreachable"


def _build_verification_enrichment(
    result: VerificationResult, source_consulted: bool,
) -> dict:
    match = result.passage_match
    out: dict = {
        "status": _verification_status(result, source_consulted),
        "internal_hash_valid": bool(result.internal_hash_valid),
        "checked_at": _now_iso(),
    }
    if result.source_hash_valid is not None:
        out["source_hash_valid"] = bool(result.source_hash_valid)
    if result.source_hash_recomputed:
        out["source_hash_recomputed"] = result.source_hash_recomputed
    if result.source_url:
        out["source_checked_url"] = result.source_url
    if match and match.found:
        out["match_type"] = match.match_type
        out["match_similarity"] = round(float(match.similarity), 4)
    if result.fetch_error:
        out["fetch_error"] = result.fetch_error
    if result.warnings:
        out["warnings"] = list(result.warnings)
    return out


# ---------------------------------------------------------------------------
# Strain → enrichment
# ---------------------------------------------------------------------------


def _discipline_from_source_type(source_type: str | None) -> str:
    return {
        "academic": "social_science",
        "journalism": "journalism",
        "web": "journalism",
        "grey": "social_science",
        "ai_output": "ai_output",
        None: "social_science",
        "": "social_science",
    }.get(source_type or "", "social_science")


def _build_strain_enrichment(
    citation: VCiteCitation,
    article_text: str,
    discipline: str,
    calibrate: bool,
) -> dict | None:
    if not _STRAIN_AVAILABLE:
        return None
    claiming_ctx = extract_claiming_context(article_text, citation)
    ls: LocalStrain = compute_local_strain(citation, claiming_ctx)
    if calibrate:
        ls.score = calibrate_score(ls.score, discipline, ls.relation)
        ls.calibrated = True
        ls.discipline = discipline
    return {
        "score": round(ls.score, 4),
        "band": classify_strain(ls.score),
        "method": ls.method,
        "calibrated": ls.calibrated,
        "discipline": ls.discipline or discipline,
        "components": {k: round(v, 4) if isinstance(v, float) else v
                       for k, v in asdict(ls.components).items()
                       if v is not None},
        "claiming_context": ls.claiming_context,
        "assessed_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _merge_enrichment(citation: VCiteCitation, patch: dict) -> None:
    """Merge ``patch`` (whose keys are 'verification' / 'strain') into
    ``citation.enrichment`` without dropping unrelated pre-existing fields.
    """
    if not patch:
        return
    current = citation.enrichment or {}
    for k, v in patch.items():
        if v is None:
            continue
        current[k] = v
    citation.enrichment = current


def enrich_citations(
    citations: list[VCiteCitation],
    *,
    do_verify: bool,
    do_strain: bool,
    offline: bool,
    article_text: str = "",
    discipline: str = "",
    calibrate: bool = True,
) -> list[VCiteCitation]:
    """Return the (mutated) citations list with enrichment fields populated."""
    # Infer discipline from the bulk of the citations if not forced
    if do_strain and not discipline:
        types = [c.source.source_type for c in citations if c.source.source_type]
        if types:
            most_common = max(set(types), key=types.count)
            discipline = _discipline_from_source_type(most_common)
        else:
            discipline = "social_science"

    for i, citation in enumerate(citations):
        _log(f"  [{i+1}/{len(citations)}] {citation.id}")
        patch: dict = {}

        if do_verify:
            if offline:
                result = verify_citation_offline(citation)
            else:
                result = verify_citation(citation)
            patch["verification"] = _build_verification_enrichment(
                result, source_consulted=not offline,
            )
            _log(f"      verify: {patch['verification']['status']}")

        if do_strain:
            strain_block = _build_strain_enrichment(
                citation, article_text, discipline, calibrate,
            )
            if strain_block is not None:
                patch["strain"] = strain_block
                _log(f"      strain: {strain_block['band']} ({strain_block['score']:.3f})")
            else:
                _log("      strain: skipped (module unavailable)")

        _merge_enrichment(citation, patch)

    return citations


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------


def _write_json_citations(path: Path, citations: list[VCiteCitation]) -> None:
    data = [c.to_dict() for c in citations]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _rewrite_html_with_enriched(
    html_path: Path, citations: list[VCiteCitation],
) -> None:
    """Re-render the HTML so the JSON-LD block and panel markup pick up the
    new enrichment. Imports render_enhanced_html lazily.
    """
    from parsers.html_parser import ExtractedQuote
    from renderer import render_enhanced_html

    original = html_path.read_text(encoding="utf-8")

    quotes = [
        ExtractedQuote(
            text_exact=c.target.text_exact,
            text_before=c.target.text_before,
            text_after=c.target.text_after,
            citation_hint="",
            paragraph_context="",
            position=0,
        )
        for c in citations
    ]

    rendered = render_enhanced_html(original, quotes, citations)
    html_path.write_text(rendered, encoding="utf-8")


def _load_article_text_for_strain(input_path: Path) -> str:
    if input_path.suffix.lower() in (".html", ".htm"):
        from source_fetch import html_to_text
        return html_to_text(input_path.read_text(encoding="utf-8"))
    # JSON input: article text not directly available; strain falls back to
    # the citation object's own text_before/text_after.
    return ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Populate VCITE citations' enrichment fields with "
        "verification + strain results.",
    )
    ap.add_argument("input", help="Citations JSON file or enhanced HTML file")
    ap.add_argument("-o", "--output", help="Output path (default: in-place)")
    ap.add_argument("--verify", action="store_true",
                    help="Run reverse-lookup verification (may fetch network)")
    ap.add_argument("--strain", action="store_true",
                    help="Run strain analysis (lexical, stdlib-only)")
    ap.add_argument("--offline", action="store_true",
                    help="When verifying, skip source fetch (internal hash only)")
    ap.add_argument("--discipline", default="",
                    help="Force discipline for strain calibration")
    ap.add_argument("--no-calibrate", action="store_true",
                    help="Disable discipline calibration for strain")
    args = ap.parse_args()

    if not (args.verify or args.strain):
        _log("Nothing to do: pass --verify and/or --strain.")
        sys.exit(2)

    input_path = Path(args.input)
    if not input_path.exists():
        _log(f"File not found: {input_path}")
        sys.exit(1)

    output_path = Path(args.output) if args.output else input_path

    _log(f"Loading citations from {input_path}")
    citations = load_citations(input_path)
    _log(f"Loaded {len(citations)} citation(s)")

    article_text = (
        _load_article_text_for_strain(input_path) if args.strain else ""
    )

    enrich_citations(
        citations,
        do_verify=args.verify,
        do_strain=args.strain,
        offline=args.offline,
        article_text=article_text,
        discipline=args.discipline,
        calibrate=not args.no_calibrate,
    )

    if output_path.suffix.lower() in (".html", ".htm"):
        _rewrite_html_with_enriched(output_path, citations)
        _log(f"Rewrote {output_path} (enrichment embedded in JSON-LD + panels)")
    else:
        _write_json_citations(output_path, citations)
        _log(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
