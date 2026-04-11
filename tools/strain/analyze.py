#!/usr/bin/env python3
"""Analyze citation strain in a VCITE-enhanced document.

RESEARCH PROTOTYPE — not production code. See DESIGN.md for context.

Usage:
    python tools/strain/analyze.py examples/katina-article.html
    python tools/strain/analyze.py citations.json --discipline social_science
    python tools/strain/analyze.py article.html --format json
"""

import argparse
import json
import sys
from pathlib import Path
from statistics import median

# Add paths
TOOLS_DIR = Path(__file__).parent.parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "implementations" / "python"))
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(Path(__file__).parent))

from vcite import VCiteCitation
from verify import load_citations
from source_fetch import html_to_text
from scorer import (
    compute_local_strain,
    extract_claiming_context,
    classify_strain,
    LocalStrain,
    GlobalStrain,
)
from sheaf import analyze_consistency
from calibration import calibrate_score, get_profile, classify_calibrated, PROFILES


def _log(msg: str):
    print(msg, file=sys.stderr)


def _extract_article_text(input_path: Path) -> str:
    """Extract plain text from the article for claiming context analysis."""
    content = input_path.read_text(encoding="utf-8")
    if input_path.suffix.lower() in (".html", ".htm"):
        return html_to_text(content)
    return content


def analyze_document(
    input_path: Path,
    discipline: str = "",
    calibrate: bool = True,
) -> GlobalStrain:
    """Full strain analysis for a document.

    1. Load VCITE citations
    2. Extract article text for claiming context
    3. Compute local strain for each citation
    4. Run sheaf consistency analysis
    5. Compute global strain
    """
    # Load citations
    citations = load_citations(input_path)
    if not citations:
        _log("No VCITE citations found")
        sys.exit(1)

    _log(f"Loaded {len(citations)} citation(s)")

    # Extract article text
    article_text = _extract_article_text(input_path)
    _log(f"Extracted {len(article_text)} chars of article text")

    # Infer discipline from source_type if not specified
    if not discipline:
        types = [c.source.source_type for c in citations if c.source.source_type]
        if types:
            most_common = max(set(types), key=types.count)
            discipline = {
                "academic": "social_science",
                "journalism": "journalism",
                "web": "journalism",
                "grey": "social_science",
                "ai_output": "ai_output",
            }.get(most_common, "social_science")
        else:
            discipline = "social_science"
    _log(f"Discipline: {discipline}")

    # Compute local strain for each citation
    local_strains: list[LocalStrain] = []
    for i, citation in enumerate(citations):
        claiming_ctx = extract_claiming_context(article_text, citation)
        ls = compute_local_strain(citation, claiming_ctx)

        # Apply discipline calibration
        if calibrate:
            ls.score = calibrate_score(
                ls.score, discipline, ls.relation
            )
            ls.calibrated = True
            ls.discipline = discipline

        local_strains.append(ls)
        _log(f"  [{i+1}/{len(citations)}] {citation.id}: "
             f"strain={ls.score:.3f} ({classify_strain(ls.score)})")

    # Sheaf consistency analysis
    consistency = analyze_consistency(local_strains, citations)
    _log(f"\nConsistency score: {consistency.consistency_score:.2f}")
    if consistency.obstructions:
        _log(f"Sheaf obstructions: {len(consistency.obstructions)}")
        for obs in consistency.obstructions:
            _log(f"  - {obs.description}")

    # Aggregate into global strain
    scores = [ls.score for ls in local_strains]
    global_score = sum(scores) / len(scores) if scores else 0.0
    distribution = {
        "low": sum(1 for s in scores if classify_strain(s) == "low"),
        "moderate": sum(1 for s in scores if classify_strain(s) == "moderate"),
        "high": sum(1 for s in scores if classify_strain(s) == "high"),
        "extreme": sum(1 for s in scores if classify_strain(s) == "extreme"),
    }

    return GlobalStrain(
        global_score=global_score,
        consistency_score=consistency.consistency_score,
        citation_count=len(citations),
        max_local_strain=max(scores) if scores else 0.0,
        mean_local_strain=global_score,
        median_local_strain=median(scores) if scores else 0.0,
        strain_distribution=distribution,
        local_strains=local_strains,
        sheaf_obstructions=[
            {
                "source": o.source_title,
                "citations": [o.citation_a, o.citation_b],
                "gap": o.strain_gap,
                "description": o.description,
            }
            for o in consistency.obstructions
        ],
    )


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_text(result: GlobalStrain) -> str:
    """Format strain analysis as human-readable text."""
    lines = []
    lines.append("=" * 70)
    lines.append("VCITE CITATION STRAIN ANALYSIS")
    lines.append("=" * 70)
    lines.append("")

    # Global summary
    lines.append(f"  Citations analyzed:    {result.citation_count}")
    lines.append(f"  Global strain:         {result.global_score:.3f} "
                 f"({classify_strain(result.global_score)})")
    lines.append(f"  Median strain:         {result.median_local_strain:.3f}")
    lines.append(f"  Max strain:            {result.max_local_strain:.3f}")
    lines.append(f"  Consistency:           {result.consistency_score:.2f}")
    lines.append("")

    # Distribution
    d = result.strain_distribution
    total = result.citation_count
    lines.append("  Distribution:")
    for cat in ("low", "moderate", "high", "extreme"):
        count = d.get(cat, 0)
        bar = "#" * count
        lines.append(f"    {cat:>10}: {count:>2}/{total}  {bar}")
    lines.append("")

    # Individual citations
    lines.append("-" * 70)
    lines.append("  Per-citation strain:")
    lines.append("-" * 70)

    for ls in result.local_strains:
        cat = classify_strain(ls.score)
        bar_width = int(ls.score * 30)
        bar = "|" + "#" * bar_width + " " * (30 - bar_width) + "|"
        lines.append(f"  {ls.citation_id:>12}  {bar}  {ls.score:.3f}  {cat}")

        # Show what was compared
        src_snippet = ls.text_exact[:60]
        if len(ls.text_exact) > 60:
            src_snippet += "..."
        claim_snippet = ls.claiming_context[:60]
        if len(ls.claiming_context) > 60:
            claim_snippet += "..."
        lines.append(f"    Source:  \"{src_snippet}\"")
        lines.append(f"    Claim:   \"{claim_snippet}\"")
        lines.append(f"    Relation: {ls.relation}  |  "
                     f"Jaccard: {ls.components.jaccard_overlap:.2f}  "
                     f"ROUGE-L: {ls.components.rouge_l:.2f}  "
                     f"Bigram-JSD: {ls.components.bigram_divergence:.2f}")
        lines.append("")

    # Sheaf obstructions
    if result.sheaf_obstructions:
        lines.append("-" * 70)
        lines.append("  Sheaf obstructions (inconsistent source usage):")
        lines.append("-" * 70)
        for obs in result.sheaf_obstructions:
            lines.append(f"  - {obs['description']}")
        lines.append("")

    return "\n".join(lines)


def format_json(result: GlobalStrain) -> str:
    """Format strain analysis as JSON."""
    d = {
        "global_score": round(result.global_score, 4),
        "consistency_score": round(result.consistency_score, 4),
        "citation_count": result.citation_count,
        "max_local_strain": round(result.max_local_strain, 4),
        "mean_local_strain": round(result.mean_local_strain, 4),
        "median_local_strain": round(result.median_local_strain, 4),
        "strain_distribution": result.strain_distribution,
        "local_strains": [
            {
                "citation_id": ls.citation_id,
                "score": round(ls.score, 4),
                "classification": classify_strain(ls.score),
                "relation": ls.relation,
                "method": ls.method,
                "calibrated": ls.calibrated,
                "discipline": ls.discipline,
                "components": {
                    "jaccard_overlap": round(ls.components.jaccard_overlap, 4),
                    "rouge_l": round(ls.components.rouge_l, 4),
                    "idf_overlap": round(ls.components.idf_overlap, 4),
                    "bigram_divergence": round(ls.components.bigram_divergence, 4),
                },
                "text_exact_snippet": ls.text_exact[:100],
                "claiming_context_snippet": ls.claiming_context[:100],
            }
            for ls in result.local_strains
        ],
        "sheaf_obstructions": result.sheaf_obstructions,
    }
    return json.dumps(d, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Analyze citation strain in a VCITE-enhanced document"
    )
    parser.add_argument(
        "input",
        help="Input file: VCITE-enhanced HTML or JSON citations",
    )
    parser.add_argument(
        "--discipline",
        choices=list(PROFILES.keys()),
        default="",
        help="Discipline for calibration (default: infer from source_type)",
    )
    parser.add_argument(
        "--no-calibrate",
        action="store_true",
        help="Skip discipline calibration (report raw scores)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        _log(f"File not found: {input_path}")
        sys.exit(1)

    result = analyze_document(
        input_path,
        discipline=args.discipline,
        calibrate=not args.no_calibrate,
    )

    if args.format == "json":
        print(format_json(result))
    else:
        print(format_text(result))


if __name__ == "__main__":
    main()
