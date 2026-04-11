#!/usr/bin/env python3
"""Build VCITE-enhanced Katina article with proper source linkage.

Reads the real saved HTML, extracts all in-text citations, maps each
to its reference entry (with DOI/URL), computes VCITE hashes, and
outputs HTML with evidence panels that link back to actual sources.
"""

import html as html_mod
import json
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).parent.parent / "tools"
IMPL_DIR = Path(__file__).parent.parent / "implementations" / "python"
sys.path.insert(0, str(IMPL_DIR))
sys.path.insert(0, str(TOOLS_DIR))

from vcite import compute_hash

# ── Reference database: citation key -> {title, url, doi, authors, year} ──

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


def ref_url(ref):
    """Get the verification URL for a reference."""
    if "doi" in ref:
        return f"https://doi.org/{ref['doi']}"
    return ref.get("url", "")


def find_ref(cite_hint):
    """Find the best matching reference for a citation hint."""
    if not cite_hint:
        return None
    # Normalize whitespace in hint
    hint = re.sub(r"\s+", " ", cite_hint).strip()

    # Exact match
    if hint in REFS:
        return REFS[hint]

    # Try partial match: for each ref, check if author surname + year match
    for key, ref in REFS.items():
        if ref.get("authors"):
            surname = ref["authors"][0].split(",")[0].split()[-1]
            # Normalize the key too
            norm_key = re.sub(r"\s+", " ", key).strip()
            # Check if surname appears in hint
            if surname.lower() in hint.lower():
                year_match = re.search(r"\d{4}", hint)
                ref_year = str(ref.get("year", ""))
                if year_match and ref_year == year_match.group():
                    return ref
                if not year_match and not ref_year:
                    return ref

    # Special cases for common mismatches
    if "Mejias" in hint or "Couldry" in hint:
        return REFS.get("Couldry and Mejias, 2021")
    if "O'Brien" in hint or "O\u2019Brien" in hint:
        return REFS.get("O'Brien et al., 2024")

    return None


def main():
    source = Path("/home/cgraziul/Documents/Confronting the Challenges of Sensitive Open Data _ Katina Magazine.html")
    output = Path(__file__).parent / "katina-article.html"

    # Use clean article-only HTML for BOTH extraction and rendering
    clean_article = Path("/tmp/katina-clean-article.html")
    if not clean_article.exists():
        print("ERROR: Run the article extraction first to create /tmp/katina-clean-article.html")
        sys.exit(1)
    content = clean_article.read_text()

    # Extract quotes from the clean article (not the full browser page)
    from parsers.html_parser import extract_quotes_html
    quotes = extract_quotes_html(content)
    print(f"Extracted {len(quotes)} cited passages")

    # Build VCITE objects with proper source linkage
    vcite_objects = []
    for i, q in enumerate(quotes):
        ref = find_ref(q.citation_hint) if q.citation_hint else None
        url = ref_url(ref) if ref else ""

        h = compute_hash(q.text_exact, q.text_before[:50], q.text_after[:50])

        obj = {
            "@context": "https://vcite.pub/ns/v1/",
            "@type": "VCiteCitation",
            "vcite": "1.0",
            "id": f"vcite-{i+1:03d}",
            "source": {
                "title": ref["title"] if ref else "Unknown",
                "authors": ref.get("authors", []) if ref else [],
                "year": ref.get("year") if ref else None,
                "doi": ref.get("doi") if ref else None,
                "url": ref.get("url") if ref else None,
            },
            "target": {
                "text_exact": q.text_exact,
                "text_before": q.text_before[:50],
                "text_after": q.text_after[:50],
                "hash": h,
            },
            "relation": _infer_relation(q),
            "captured_at": "2026-04-11T00:00:00Z",
            "captured_by": "author",
        }
        # Strip None values
        obj["source"] = {k: v for k, v in obj["source"].items() if v is not None}
        vcite_objects.append(obj)

        status = f"-> {ref['title'][:50]}..." if ref else "-> [no ref match]"
        link = f" ({url})" if url else ""
        print(f"  [{i+1:2d}] {q.citation_hint or '(self)':40s} {status}{link}")

    # Now render using the tools renderer
    from renderer import render_enhanced_html

    # Build VCiteCitation objects for the renderer
    from vcite import VCiteCitation, VCiteSource, VCiteTarget

    vc_objs = []
    for obj in vcite_objects:
        src = obj["source"]
        tgt = obj["target"]
        vc = VCiteCitation(
            vcite="1.0",
            id=obj["id"],
            source=VCiteSource(
                title=src.get("title", "Unknown"),
                authors=src.get("authors", []),
                year=src.get("year"),
                doi=src.get("doi"),
                url=src.get("url"),
            ),
            target=VCiteTarget(
                text_exact=tgt["text_exact"],
                text_before=tgt["text_before"],
                text_after=tgt["text_after"],
                hash=tgt["hash"],
            ),
            relation=obj["relation"],
            captured_at=obj["captured_at"],
            captured_by=obj["captured_by"],
        )
        vc_objs.append(vc)

    result = render_enhanced_html(content, quotes, vc_objs)

    # Remove the banner
    result = re.sub(
        r'<div class="vcite-banner">.*?</div>\s*',
        "",
        result,
        flags=re.DOTALL,
    )

    output.write_text(result)
    linked = sum(1 for obj in vcite_objects if ref_url(obj.get("_ref", {})) or obj["source"].get("doi") or obj["source"].get("url"))
    print(f"\nWrote {output} ({len(vcite_objects)} VCITE citations, {linked} linked to sources)")


def _infer_relation(quote):
    text = quote.text_exact.lower()
    if any(w in text for w in ("defined as", "refers to", "means", "is termed", "to describe")):
        return "defines"
    if any(w in text for w in ("disagree", "challenge", "refute", "contrary to")):
        return "contradicts"
    if re.search(r"\d+[.,]?\d*\s*%", text) or any(w in text for w in ("percent", "rate", "number of", "million")):
        return "quantifies"
    if any(w in text for w in ("warn", "caution", "risk", "concern", "difficult", "harm")):
        return "cautions"
    if any(w in text for w in ("method", "approach", "technique", "framework", "model", "protocol")):
        return "method"
    if any(w in text for w in ("history", "tradition", "background", "context", "evolution")):
        return "contextualizes"
    return "supports"


if __name__ == "__main__":
    main()
