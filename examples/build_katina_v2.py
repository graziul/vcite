#!/usr/bin/env python3
"""Build clean VCITE citations JSON from Katina article.

Two modes:
  1. Extract from enhanced HTML (default): reads the curated citations
     already embedded as JSON-LD in katina-article.html
  2. Build from scratch (--from-raw): extracts passages from raw article
     HTML, resolves metadata via REFS dict + CrossRef API, flags failures

Mode 1 is the normal workflow — produce a clean JSON export from an
already-enhanced article. Mode 2 is for bootstrapping new articles.

Usage:
    python examples/build_katina_v2.py                     # mode 1
    python examples/build_katina_v2.py --from-raw RAW.html # mode 2
"""

import json
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).parent.parent / "tools"
IMPL_DIR = Path(__file__).parent.parent / "implementations" / "python"
sys.path.insert(0, str(IMPL_DIR))
sys.path.insert(0, str(TOOLS_DIR))

from vcite import VCiteCitation, VCiteSource, VCiteTarget, compute_hash

# Article metadata for self-citation detection
ARTICLE_META = {
    "title": "Confronting the Challenges of Sensitive Open Data",
    "authors": ["Danton, Cheryl M.", "Graziul, Christopher"],
    "year": 2026,
    "venue": "Katina Magazine",
    "source_type": "academic",
}

# ── Reference database (from build_katina_real.py, verified correct) ──

REFS = {
    "Savage & Monroy-Hernández, 2018": {
        "title": "Participatory militias: An analysis of an armed movement to protect communities in Mexico",
        "doi": "10.1145/3287560.3287577", "year": 2018,
        "authors": ["Savage, S.", "Monroy-Hernandez, A."],
    },
    "Breitenbach, 2015": {
        "title": "States grapple with public disclosure of police body-camera footage",
        "url": "https://stateline.org/2015/09/22/states-grapple-with-public-disclosure-of-police-body-camera-footage",
        "year": 2015, "authors": ["Breitenbach, S."],
    },
    "Reporters Committee for Freedom of the Press, 2023": {
        "title": "Police body-worn cameras: A primer for newsrooms",
        "url": "https://www.rcfp.org/resources/bodycams/",
        "year": 2023, "authors": ["Reporters Committee for Freedom of the Press"],
    },
    "Lin, 2015": {
        "title": "Police body worn cameras and privacy",
        "url": "https://scholarship.law.duke.edu/dltr/vol14/iss1/15/",
        "year": 2015, "authors": ["Lin, R."],
    },
    "Newell, 2021": {
        "title": "Body cameras help monitor police but can invade people's privacy",
        "url": "https://theconversation.com/body-cameras-help-monitor-police-but-can-invade-peoples-privacy-160846",
        "year": 2021, "authors": ["Newell, B."],
    },
    "Erdos, 2016": {
        "title": "European Union data protection law and media expression: Fundamentally off balance",
        "doi": "10.1017/S0020589315000512", "year": 2016, "authors": ["Erdos, D."],
    },
    "Dwork, 2009": {
        "title": "The differential privacy frontier",
        "doi": "10.1145/1557019.1557079", "year": 2009, "authors": ["Dwork, C."],
    },
    "Hardinges et al., 2021": {
        "title": "Data trusts in 2021",
        "url": "https://www.adalovelaceinstitute.org/report/legal-mechanisms-data-stewardship/",
        "year": 2021, "authors": ["Hardinges, J.", "Tennison, J.", "Shore, H.", "Scott, A."],
    },
    "Wilkinson et al., 2016": {
        "title": "The FAIR guiding principles for scientific data management and stewardship",
        "doi": "10.1038/sdata.2016.18", "year": 2016, "authors": ["Wilkinson, M. D.", "et al."],
    },
    "Carroll et al., 2020": {
        "title": "The CARE Principles for Indigenous Data Governance",
        "url": "https://openscholarshippress.pubpub.org/pub/xx3kj9rv",
        "year": 2020, "authors": ["Carroll, S. R.", "Garba, I.", "et al."],
    },
    "Carroll et al., 2019": {
        "title": "Indigenous data governance: Strategies from United States Native nations",
        "doi": "10.5334/dsj-2019-031", "year": 2019, "authors": ["Carroll, S. R.", "Rodriguez-Lonebear, D.", "Martinez, A."],
    },
    "Kukutai and Taylor, 2016": {
        "title": "Indigenous data sovereignty: Toward an agenda",
        "url": "https://www.jstor.org/stable/j.ctt1q1crgf",
        "year": 2016, "authors": ["Kukutai, T.", "Taylor, J."],
    },
    "Couldry and Mejias, 2021": {
        "title": "The decolonial turn in data and technology research",
        "doi": "10.1080/1369118X.2021.1986102", "year": 2021,
        "authors": ["Couldry, N.", "Mejias, U. A."],
    },
    "Jennings et al., 2023": {
        "title": "Applying the CARE Principles for Indigenous Data Governance to ecology and biodiversity research",
        "doi": "10.1038/s41559-023-02161-2", "year": 2023, "authors": ["Jennings, L.", "et al."],
    },
    "Gupta et al., 2023": {
        "title": "The CARE Principles and the reuse, sharing, and curation of Indigenous data in Canadian archaeology",
        "doi": "10.1017/aap.2022.33", "year": 2023, "authors": ["Gupta, N.", "et al."],
    },
    "O'Brien et al., 2024": {
        "title": "Earth science data repositories: Implementing the CARE principles",
        "doi": "10.5334/dsj-2024-037", "year": 2024, "authors": ["O'Brien, M.", "et al."],
    },
}


# ---------------------------------------------------------------------------
# Mode 1: Extract from enhanced HTML
# ---------------------------------------------------------------------------

def extract_from_html(html_path: Path) -> list[dict]:
    """Extract VCITE citations from JSON-LD in enhanced HTML.

    Returns list of citation dicts with _resolution metadata.
    """
    from verify import load_citations_from_html

    citations = load_citations_from_html(html_path)
    if not citations:
        print(f"No VCITE citations found in {html_path}", file=sys.stderr)
        sys.exit(1)

    results = []
    for cit in citations:
        d = cit.to_dict()
        # Add resolution metadata
        if cit.source.title and cit.source.title != "Unknown":
            d["_resolution"] = "curated"
        else:
            d["_resolution"] = "unresolved"
        results.append(d)

    return results


# ---------------------------------------------------------------------------
# Mode 2: Build from scratch with metadata resolution
# ---------------------------------------------------------------------------

def _find_ref(hint: str) -> dict | None:
    """Match a citation hint against the REFS dictionary."""
    if not hint:
        return None
    hint = re.sub(r"\s+", " ", hint).strip()

    # Exact match
    if hint in REFS:
        return REFS[hint]

    # Fuzzy: surname + year
    for key, ref in REFS.items():
        if ref.get("authors"):
            surname = ref["authors"][0].split(",")[0].split()[-1]
            if surname.lower() in hint.lower():
                year_match = re.search(r"\d{4}", hint)
                ref_year = str(ref.get("year", ""))
                if year_match and ref_year == year_match.group():
                    return ref

    # Handle common mismatches
    if "Mejias" in hint or "Couldry" in hint:
        return REFS.get("Couldry and Mejias, 2021")
    if "O'Brien" in hint or "O\u2019Brien" in hint:
        return REFS.get("O'Brien et al., 2024")

    return None


def _crossref_with_context(hint: str, paragraph: str) -> dict | None:
    """Search CrossRef with paragraph context for disambiguation.

    Adds distinctive words from the paragraph to narrow the search,
    preventing false matches (e.g., wrong "Carroll 2020").
    """
    try:
        from metadata import search_crossref, _CITE_HINT_RE
    except ImportError:
        return None

    cite_match = _CITE_HINT_RE.search(hint.strip("()"))
    if not cite_match:
        return None

    author_str = cite_match.group(1)
    year = int(cite_match.group(2))
    first_author = author_str.split("&")[0].split(" and ")[0].strip()
    first_author = re.sub(r"\s+et\s+al\.?", "", first_author).strip()

    # Extract distinctive capitalized words from paragraph for disambiguation
    stop = {"The", "This", "That", "These", "Their", "They", "Data", "For",
            "And", "With", "From", "Into", "Have", "Been", "Were", "Also",
            "Such", "Which", "Both", "More", "Most", "Some", "Other"}
    words = re.findall(r'\b[A-Z][a-z]{3,}\b', paragraph)
    keywords = [w for w in words if w not in stop
                and w.lower() != first_author.lower()][:3]

    query = f"{first_author} {year} {' '.join(keywords)}"
    meta = search_crossref(query=query, author=first_author, year=year)
    if not meta:
        return None

    return {
        "title": meta.title,
        "authors": meta.authors,
        "year": meta.year,
        "doi": meta.doi,
        "url": f"https://doi.org/{meta.doi}" if meta.doi else meta.url,
    }


def build_from_raw(raw_path: Path) -> list[dict]:
    """Extract passages from raw HTML and resolve metadata.

    Three-tier resolution:
    1. REFS dictionary (hardcoded, verified)
    2. CrossRef API with paragraph context disambiguation
    3. Self-citation detection (passages without citation hints)
    """
    from parsers.html_parser import extract_quotes_html
    from source_fetch import html_to_text

    content = raw_path.read_text(encoding="utf-8")
    quotes = extract_quotes_html(content)
    article_text = html_to_text(content)

    print(f"Extracted {len(quotes)} passages", file=sys.stderr)

    results = []
    stats = {"matched": 0, "crossref": 0, "self": 0, "unresolved": 0}

    for i, q in enumerate(quotes):
        resolution = "unresolved"
        ref = None

        # Tier 1: REFS dict
        if q.citation_hint:
            ref = _find_ref(q.citation_hint)
            if ref:
                resolution = "matched"

        # Tier 2: CrossRef with context
        if not ref and q.citation_hint:
            # Get paragraph context around the passage
            idx = article_text.find(q.text_exact[:30])
            para = article_text[max(0, idx - 200):idx + len(q.text_exact) + 200] if idx >= 0 else ""
            ref = _crossref_with_context(q.citation_hint, para)
            if ref:
                resolution = "crossref"

        # Tier 3: Self-citation (no hint = passage is from this article)
        if not ref and not q.citation_hint:
            ref = {
                "title": ARTICLE_META["title"],
                "authors": ARTICLE_META["authors"],
                "year": ARTICLE_META["year"],
                "venue": ARTICLE_META["venue"],
            }
            resolution = "self"

        # Build source metadata
        if ref:
            source = {
                "title": ref["title"],
                "authors": ref.get("authors", []),
            }
            if ref.get("year"):
                source["year"] = ref["year"]
            if ref.get("doi"):
                source["doi"] = ref["doi"]
            if ref.get("url"):
                source["url"] = ref["url"]
            if ref.get("venue"):
                source["venue"] = ref["venue"]
            source["source_type"] = "academic"
        else:
            hint_label = q.citation_hint or "unknown passage"
            source = {
                "title": f"[UNRESOLVED: {hint_label}]",
                "authors": [],
                "source_type": "academic",
            }

        h = compute_hash(q.text_exact, q.text_before[:50], q.text_after[:50])

        obj = {
            "vcite": "1.0",
            "id": f"vcite-{i + 1:03d}",
            "source": source,
            "target": {
                "text_exact": q.text_exact,
                "text_before": q.text_before[:50],
                "text_after": q.text_after[:50],
                "hash": h,
            },
            "relation": _infer_relation(q.text_exact),
            "captured_at": "2026-04-11T00:00:00Z",
            "captured_by": "model",
            "_resolution": resolution,
        }
        results.append(obj)
        stats[resolution] += 1

        label = source["title"][:55]
        print(f"  [{i + 1:2d}] {resolution:>10}  {label}", file=sys.stderr)

    print(f"\nResolution: {stats}", file=sys.stderr)
    return results


def _infer_relation(text: str) -> str:
    """Infer VCITE relation type from passage content."""
    t = text.lower()
    if any(w in t for w in ("defined as", "refers to", "means", "is termed")):
        return "defines"
    if any(w in t for w in ("disagree", "challenge", "refute", "contrary")):
        return "contradicts"
    if re.search(r"\d+[.,]?\d*\s*%", t) or any(w in t for w in ("percent", "rate")):
        return "quantifies"
    if any(w in t for w in ("warn", "caution", "risk", "concern", "harm")):
        return "cautions"
    if any(w in t for w in ("method", "approach", "framework", "protocol")):
        return "method"
    if any(w in t for w in ("history", "tradition", "background", "context")):
        return "contextualizes"
    return "supports"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build clean VCITE citations JSON from Katina article",
    )
    parser.add_argument(
        "--from-raw",
        type=Path,
        help="Build from raw HTML (mode 2). Default: extract from katina-article.html",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path(__file__).parent / "katina-citations.json",
        help="Output JSON file (default: examples/katina-citations.json)",
    )
    args = parser.parse_args()

    if args.from_raw:
        if not args.from_raw.exists():
            print(f"File not found: {args.from_raw}", file=sys.stderr)
            sys.exit(1)
        citations = build_from_raw(args.from_raw)
    else:
        html_path = Path(__file__).parent / "katina-article.html"
        if not html_path.exists():
            print(f"File not found: {html_path}", file=sys.stderr)
            sys.exit(1)
        citations = extract_from_html(html_path)

    # Write output
    output_json = json.dumps(citations, indent=2, ensure_ascii=False)
    args.output.write_text(output_json + "\n", encoding="utf-8")

    # Summary
    total = len(citations)
    resolved = sum(1 for c in citations if c.get("_resolution") != "unresolved")
    print(f"\nWrote {total} citations to {args.output} ({resolved}/{total} resolved)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
