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
        "authors": ["Savage, S.", "Monroy-Hernández, A."],
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
    "Houston Police Department, 2021": {
        "title": "Critical Incident Video Public Release",
        "url": "https://www.houstontx.gov/police/general_orders/800/800-03%20Critical%20Incident%20Video%20Public%20Release.pdf",
        "year": 2021, "authors": ["Houston Police Department"],
    },
    "New Orleans Police Department, 2023": {
        "title": "Records Release and Security",
        "url": "https://nopdconsent.azurewebsites.net/Media/Default/Documents/Policies/Chapter%2082.1.1",
        "year": 2023, "authors": ["New Orleans Police Department"],
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
    "Illinois Attorney General, 2024": {
        "title": "2024 FOIA webinar on law enforcement videos",
        "url": "https://illinoisattorneygeneral.gov/Page-Attachments/2024%20FOIA%20Webinar%20on%20Law%20Enforcement%20Videos.pdf",
        "year": 2024, "authors": ["Illinois Attorney General"],
    },
    "California Department of Justice, 2020": {
        "title": "Confidentiality of information from CLETS",
        "url": "https://oag.ca.gov/sites/all/files/agweb/pdfs/info_bulletins/20-09-cjis.pdf",
        "year": 2020, "authors": ["California Department of Justice"],
    },
    "US Department of Justice, n.d.": {
        "title": "FOIA.gov FAQ",
        "url": "https://www.foia.gov/faq.html",
        "authors": ["US Department of Justice"],
    },
    "Erdos, 2019": {
        "title": "European data protection regulation, journalism, and traditional publishers",
        "year": 2019, "authors": ["Erdos, D."],
    },
    "Erdos, 2016": {
        "title": "European Union data protection law and media expression: Fundamentally off balance",
        "doi": "10.1017/S0020589315000512", "year": 2016, "authors": ["Erdos, D."],
    },
    "Dwork, 2009": {
        "title": "The differential privacy frontier",
        "doi": "10.1145/1557019.1557079", "year": 2009, "authors": ["Dwork, C."],
    },
    "Dickert et al., 2021": {
        "title": "Meeting unique requirements: Community consultation and public disclosure for EFIC research",
        "doi": "10.1111/acem.14264", "year": 2021,
        "authors": ["Dickert, N. W.", "Metz, K.", "Fetters, M. D.", "Haggins, A. N.", "Harney, D. K.", "Speight, C. D.", "Silbergleit, R."],
    },
    "Fehr et al., 2015": {
        "title": "Learning from experience: A systematic review of community consultation acceptance data",
        "year": 2015, "authors": ["Fehr, A. E.", "Pentz, R. D.", "Dickert, N. W."],
    },
    "Hardinges et al., 2021": {
        "title": "Data trusts in 2021",
        "url": "https://www.adalovelaceinstitute.org/report/legal-mechanisms-data-stewardship/",
        "year": 2021, "authors": ["Hardinges, J.", "Tennison, J.", "Shore, H.", "Scott, A."],
    },
    "Micheli et al., 2021": {
        "title": "The datafication of the public sector",
        "doi": "10.1145/3442188.3445923", "year": 2021,
        "authors": ["Micheli, M.", "Jarke, J.", "Heiberg, M."],
    },
    "Chouldechova et al., 2023": {
        "title": "A case for rejection",
        "doi": "10.1145/3593013.3594093", "year": 2023,
        "authors": ["Chouldechova, A.", "Black, E.", "Wolf, C. T.", "Opoku-Agyemang, K."],
    },
    "Irani et al., 2023": {
        "title": "The last mile: Where language, culture, and technology meet in data work",
        "doi": "10.1145/3617694.3623261", "year": 2023,
        "authors": ["Irani, L.", "Vertesi, J.", "Dourish, P."],
    },
    "Sambasivan et al., 2023": {
        "title": "Re-imagining algorithmic fairness in India and beyond",
        "doi": "10.1145/3593013.3593989", "year": 2023,
        "authors": ["Sambasivan, N.", "Arnesen, E.", "Hutchinson, B.", "Prabhakaran, V."],
    },
    "Kukutai and Taylor, 2016": {
        "title": "Indigenous data sovereignty: Toward an agenda",
        "url": "https://www.jstor.org/stable/j.ctt1q1crgf",
        "year": 2016, "authors": ["Kukutai, T.", "Taylor, J."],
    },
    "Lovett et al., 2020": {
        "title": "The intersection of indigenous data sovereignty and closing the gap policy in Australia",
        "year": 2020, "authors": ["Lovett, R.", "Jones, R.", "Maher, B."],
    },
    "Wilkinson et al., 2016": {
        "title": "The FAIR guiding principles for scientific data management and stewardship",
        "doi": "10.1038/sdata.2016.18", "year": 2016,
        "authors": ["Wilkinson, M. D.", "et al."],
    },
    "Carroll et al., 2020": {
        "title": "The CARE Principles for Indigenous Data Governance",
        "url": "https://openscholarshippress.pubpub.org/pub/xx3kj9rv",
        "year": 2020,
        "authors": ["Carroll, S. R.", "Garba, I.", "et al."],
    },
    "Carroll et al., 2019": {
        "title": "Indigenous data governance: Strategies from United States Native nations",
        "doi": "10.5334/dsj-2019-031", "year": 2019,
        "authors": ["Carroll, S. R.", "Rodriguez-Lonebear, D.", "Martinez, A."],
    },
    "Rodriguez-Lonebear, 2016": {
        "title": "Building a data revolution in Indian country",
        "doi": "10.22459/CAEPR38.11.2016.1", "year": 2016,
        "authors": ["Rodriguez-Lonebear, D."],
    },
    "Rainie et al., 2017": {
        "title": "Data as strategic resource: Self-determination and the data challenge for US Indigenous nations",
        "doi": "10.18584/iipj.2017.8.2.1", "year": 2017,
        "authors": ["Rainie, S. C.", "et al."],
    },
    "NCAIPRC, 2017": {
        "title": "Recommendations from tribal experiences with tribal censuses and surveys",
        "year": 2017, "authors": ["NCAIPRC"],
    },
    "NCAI, 2018": {
        "title": "Resolution KAN-18-011: Support of US Indigenous data sovereignty",
        "year": 2018, "authors": ["NCAI"],
    },
    "Navajo Nation Human Research Review Board, n.d.": {
        "title": "About NNHRRB",
        "url": "https://nnhrrb.navajo-nsn.gov/aboutNNHRRB.html",
        "authors": ["Navajo Nation HRRB"],
    },
    "Indian Health Service, n.d.": {
        "title": "Institutional Review Boards (IRBs)",
        "url": "https://www.ihs.gov/dper/research/hsrp/instreviewboards/",
        "authors": ["Indian Health Service"],
    },
    "O'Brien et al., 2024": {
        "title": "Earth science data repositories: Implementing the CARE principles",
        "doi": "10.5334/dsj-2024-037", "year": 2024,
        "authors": ["O'Brien, M.", "et al."],
    },
    "Jennings et al., 2023": {
        "title": "Applying the CARE Principles for Indigenous Data Governance to ecology and biodiversity research",
        "doi": "10.1038/s41559-023-02161-2", "year": 2023,
        "authors": ["Jennings, L.", "et al."],
    },
    "Gupta et al., 2023": {
        "title": "The CARE Principles and the reuse, sharing, and curation of Indigenous data in Canadian archaeology",
        "doi": "10.1017/aap.2022.33", "year": 2023,
        "authors": ["Gupta, N.", "et al."],
    },
    "Costantine, 2022": {
        "title": "The Swakopmund protocol for the protection of expressions of folklore",
        "doi": "10.1093/jiplp/jpac088", "year": 2022,
        "authors": ["Costantine, J."],
    },
    "da Silva and de Oliveira, 2018": {
        "title": "The new Brazilian legislation on access to the biodiversity",
        "doi": "10.1016/j.bjm.2017.12.001", "year": 2018,
        "authors": ["da Silva, M.", "de Oliveira, D. R."],
    },
    "Couldry and Mejias, 2021": {
        "title": "The decolonial turn in data and technology research",
        "doi": "10.1080/1369118X.2021.1986102", "year": 2021,
        "authors": ["Couldry, N.", "Mejias, U. A."],
    },
    "FDA, 2013": {
        "title": "Exception from informed consent requirements for emergency research",
        "url": "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/exception-informed-consent-requirements-emergency-research",
        "year": 2013, "authors": ["US FDA"],
    },
    "EFIC, 1996": {
        "title": "Exception from Informed Consent Requirements for Emergency Research, 21 CFR § 50.24",
        "url": "https://www.ecfr.gov/current/title-21/section-50.24",
        "year": 1996,
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
