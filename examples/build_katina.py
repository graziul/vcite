#!/usr/bin/env python3
"""Generate the VCITE-enhanced Katina article HTML from article text + VCITE objects."""

import json
import sys
from pathlib import Path

# Add python implementation to path
sys.path.insert(0, str(Path(__file__).parent.parent / "implementations" / "python"))
from vcite import compute_hash

ARTICLE_URL = "https://katinamagazine.org/content/article/open-knowledge/2026/confronting-the-challenges-of-sensitive-open-data"
ARTICLE_DOI = "10.1146/katina-010626-1"

# ── Article paragraphs with VCITE markup ─────────────────────────
# {v:ID} marks where a VCITE span opens, {/v} closes it
# Paragraphs are grouped by section

SECTIONS = [
    ("", [  # intro, no heading
        'Government agencies collect substantial amounts of data about members of the public, often including sensitive information. When this information becomes accessible to third parties, {v:vcite-savage-2018}tensions emerge between personal privacy and government transparency{/v} (Savage &amp; Monroy-Hern&aacute;ndez, 2018).',
        'The authors define "sensitive open data" as "{v:vcite-sod-def}data containing private information about individuals that becomes available to the public through a range of mechanisms, from court orders to statutory mandates{/v}." This concept illuminates how open data can both help and harm individuals, serving as an important edge case in examining the tensions between personal privacy and government transparency in an increasingly data-intensive world.',
    ]),
    ("The Unusually Open Nature (and Risks) of Policing Data", [
        'While data ownership presents challenges in the private sector, it appears more straightforward in government contexts. One might reasonably assume a crime victim owns the resulting data. Yet in reality, "{v:vcite-access}anyone can access such data given a relevant legal statute enabling access and approval of an access request, all without the victim\'s knowledge{/v}."',
        'The authors have spent three years examining how publicly available data can pose invisible risks to individuals whose personal information is included. Their focus has been policing data in the United States &mdash; information collected or generated through policing activities, much of which is accessible via laws like the Freedom of Information Act.',
        'While television often dramatizes policing, "{v:vcite-boring}policing is often boring: officers patrol streets, do paperwork, assist motorists{/v}." Media coverage tends to focus on dramatic events, creating calls for transparency without clarifying whether these events are rare or represent patterns.',
        'Statutes in the United States and other countries make policing data publicly accessible for transparency purposes. "{v:vcite-normal}Access to sensitive open data about policing is now normal, even if technology complicates the status quo{/v}."',
        'While such transparency serves clear purposes in legal proceedings, "{v:vcite-reactive}reactive transparency does not support scientific research about police systems as organizations, let alone provide an accurate picture of how policing operates in practice or the data rights at stake{/v}."',
        'Officer interactions involve individuals who may be victims, those never arrested, or those arrested but not convicted. Such data includes information about individual officers, creating "{v:vcite-confluence}a special confluence of identifiers and interested parties. When that data becomes open, victims, suspects, bystanders, and officers collectively experience a loss of privacy that may be mandated by law, whose potential harms can only be mitigated{/v}."',
        'Different jurisdictions balance openness and privacy protections differently. Illinois provides body-worn camera access to those involved. California prioritizes privacy by encouraging police scanner communication encryption. This variation "{v:vcite-ca-encrypt}reflects significant disagreement in how to responsibly provide access to sensitive data{/v}."',
        'These challenges are not unique to policing. "{v:vcite-any-govt}Almost any government service &mdash; from public housing, to child welfare services, to public health initiatives &mdash; involves members of the public, government employees, and record keeping that may be subject to future public scrutiny{/v}."',
        'In the European Union, the GDPR provides more robust privacy protections than the United States but still requires weighing interests. "{v:vcite-eu-privacy}For at least the last fifteen years, European jurisprudence has favored the protection of personal privacy{/v}," though this has created concerns about journalistic access and inconsistency across member states (Erdos, 2016; 2019).',
    ]),
    ("The Challenge of Sensitive Open Data", [
        'Risks associated with sensitive open data require identifying justified strategies for negotiating privacy/utility tradeoffs. For information subject to open records laws, privacy-preserving strategies cannot prevent the release of sensitive information.',
        '"{v:vcite-metadata}If organizations must provide access to sensitive information, then just knowing what information is accessible (i.e., the names of data elements) can place individuals at risk, as it identifies data that must be made available on request. This means access to metadata can be just as harmful as access to the data{/v}."',
        'Data providers must ensure clarity about why sensitive data must be openly available, what protections are needed to prevent foreseeable harms, and who benefits.',
    ]),
    ("Addressing the Lack of Informed Consent", [
        'Addressing consent in sensitive open data cannot be overstated, and effective models exist. Many lifesaving emergency research studies in the United States require exception from informed consent (EFIC) because individuals are incapacitated.',
        'US Food and Drug Administration regulations require that all emergency research utilizing EFIC include community consultation and public disclosure of research outcomes. "{v:vcite-efic}Public research presentations are the most common method of community consultation and are associated with high acceptance rates of EFIC studies by community members{/v}." Surveys, focus groups, and interviews have also been employed (Dickert et al., 2021; Fehr et al., 2015).',
        'Similar community engagement mechanisms could ensure that benefits of sensitive open data outweigh harms and enable communal data ownership. While data trusts have gained traction as vehicles for responsible data stewardship, "{v:vcite-buyin}securing community buy-in to these solutions is difficult, especially in light of the potential for exploitation{/v}" (Hardinges et al., 2021).',
    ]),
    ("Learning from Indigenous Communities", [
        'Data sovereignty concerns indigenous communities wary of extractive practices, a conversation predating current debates.',
        'The FAIR principles (Wilkinson et al., 2016) promote scientific data-sharing best practices, designed to make data "{v:vcite-fair}Findable, Accessible, Interoperable, and Reusable{/v}." The CARE Principles &mdash; "{v:vcite-care}Collective Benefit, Authority to Control, Responsibility, and Ethics{/v}" &mdash; were developed by the International Indigenous Data Sovereignty Interest Group (Carroll et al., 2020).',
        'These principles "{v:vcite-care-purpose}integrate Indigenous worldviews that center \'people\' and \'purpose\' to address critical gaps in conventional data frameworks by ensuring that Indigenous Peoples benefit from data activities and maintain control over their data{/v}."',
        'In 2014, the NCAIPRC organized five tribes to pilot unique community-based data projects. The Pueblo of Laguna developed proprietary census software in partnership with the University of New Mexico. This demonstrates that "{v:vcite-laguna}tribes can independently manage data and utilize external expertise to develop technology that reflects their priorities{/v}" (NCAIPRC, 2017).',
        'The Navajo Nation Human Research Review Board, established in 1996, exercises sovereignty over all human research activities in the Navajo Nation. "{v:vcite-navajo}Notably, all research data conducted under this IRB\'s authority belongs to the Navajo Nation{/v}." Today, 11 Indian Health Service IRBs exist alongside growing numbers of independent tribal IRBs.',
        '"{v:vcite-care-integration}Initiatives to integrate these principles into research infrastructure not only highlight the importance of Indigenous community governance in enhancing the quality and reproducibility of research and data; they also align research with community values and facilitate responsible data stewardship{/v}" (Jennings et al., 2023; O\'Brien et al., 2024).',
        'While CARE and FAIR principles were formally articulated through networks with significant US participation, similar frameworks have been developed independently across the Global South. These developments "{v:vcite-global-south}reflect ongoing global efforts to balance the ethical tensions identified in CARE principles between open data ideals and Indigenous data sovereignty{/v}."',
    ]),
    ("Data Sovereignty as a Mechanism for Communal Self-Determination", [
        'Applying these approaches to sensitive open data respects the autonomy of individuals who rarely gave consent for private information access.',
        'The authors acknowledge that making these changes will be difficult. However, failing to act would perpetuate "{v:vcite-colonialism}a system that centralizes sensitive open data in ways that parallel what Couldry and Mejias (2021) call \'data colonialism\' in corporate contexts, extracting value from peoples\' information while withholding its benefits from data rights holders{/v}." Given the unique public value of sensitive open data, these are challenges worth overcoming.',
    ]),
]

# ── VCITE objects ────────────────────────────────────────────────

def make_vcite(id, text_exact, text_before, text_after, relation, title, authors=None, year=None, doi=None, url=None, source_type="academic", venue=None):
    h = compute_hash(text_exact, text_before, text_after)
    obj = {
        "@context": "https://vcite.pub/ns/v1/",
        "@type": "VCiteCitation",
        "vcite": "1.0",
        "id": id,
        "source": {"title": title, "source_type": source_type},
        "target": {
            "text_before": text_before,
            "text_exact": text_exact,
            "text_after": text_after,
            "hash": h,
        },
        "relation": relation,
        "captured_at": "2026-04-10T00:00:00Z",
        "captured_by": "author",
    }
    if authors: obj["source"]["authors"] = authors
    if year: obj["source"]["year"] = year
    if doi: obj["source"]["doi"] = doi
    if url: obj["source"]["url"] = url
    if venue: obj["source"]["venue"] = venue
    return obj

VCITES = [
    make_vcite("vcite-savage-2018", "tensions emerge between personal privacy and government transparency", "When this information becomes accessible to third parties, ", " (Savage & Monroy-Hernández, 2018).", "contextualizes", "Participatory militias", ["Savage, S.", "Monroy-Hernández, A."], 2018, doi="10.1145/3287560.3287577"),
    make_vcite("vcite-sod-def", "data containing private information about individuals that becomes available to the public through a range of mechanisms, from court orders to statutory mandates", 'The authors define "sensitive open data" as "', '." This concept illuminates how open', "defines", "Confronting the Challenges of Sensitive Open Data", ["Danton, Cheryl M.", "Graziul, Christopher"], 2026, doi=ARTICLE_DOI, venue="Katina Magazine"),
    make_vcite("vcite-access", "anyone can access such data given a relevant legal statute enabling access and approval of an access request, all without the victim's knowledge", 'Yet in reality, "', '."', "supports", "Confronting the Challenges of Sensitive Open Data", ["Danton, Cheryl M.", "Graziul, Christopher"], 2026, doi=ARTICLE_DOI),
    make_vcite("vcite-boring", "policing is often boring: officers patrol streets, do paperwork, assist motorists", 'television often dramatizes policing, "', '." Media coverage tends to focus', "contextualizes", "Confronting the Challenges of Sensitive Open Data", ["Danton, Cheryl M.", "Graziul, Christopher"], 2026, doi=ARTICLE_DOI),
    make_vcite("vcite-normal", "Access to sensitive open data about policing is now normal, even if technology complicates the status quo", 'Some jurisdictions require or enable the release of specific data types. "', '."', "supports", "Confronting the Challenges of Sensitive Open Data", ["Danton, Cheryl M.", "Graziul, Christopher"], 2026, doi=ARTICLE_DOI),
    make_vcite("vcite-reactive", "reactive transparency does not support scientific research about police systems as organizations, let alone provide an accurate picture of how policing operates in practice or the data rights at stake", 'such transparency serves clear purposes in legal proceedings, "', '." Some argue this approach', "supports", "Confronting the Challenges of Sensitive Open Data", ["Danton, Cheryl M.", "Graziul, Christopher"], 2026, doi=ARTICLE_DOI),
    make_vcite("vcite-confluence", "a special confluence of identifiers and interested parties. When that data becomes open, victims, suspects, bystanders, and officers collectively experience a loss of privacy that may be mandated by law, whose potential harms can only be mitigated", 'Such data includes information about individual officers, creating "', '."', "supports", "Confronting the Challenges of Sensitive Open Data", ["Danton, Cheryl M.", "Graziul, Christopher"], 2026, doi=ARTICLE_DOI),
    make_vcite("vcite-ca-encrypt", "reflects significant disagreement in how to responsibly provide access to sensitive data", 'This variation "', '."', "contextualizes", "Confidentiality of information from CLETS", year=2020, url="https://oag.ca.gov/sites/all/files/agweb/pdfs/info_bulletins/20-09-cjis.pdf", source_type="grey", venue="California DOJ"),
    make_vcite("vcite-any-govt", "Almost any government service -- from public housing, to child welfare services, to public health initiatives -- involves members of the public, government employees, and record keeping that may be subject to future public scrutiny", '"', '."', "contextualizes", "Confronting the Challenges of Sensitive Open Data", ["Danton, Cheryl M.", "Graziul, Christopher"], 2026, doi=ARTICLE_DOI),
    make_vcite("vcite-eu-privacy", "For at least the last fifteen years, European jurisprudence has favored the protection of personal privacy", '"', '," though this has created concerns', "contextualizes", "European Union data protection law and media expression", ["Erdos, D."], 2016, doi="10.1017/S0020589315000512", venue="Int'l & Comparative Law Quarterly"),
    make_vcite("vcite-metadata", "If organizations must provide access to sensitive information, then just knowing what information is accessible (i.e., the names of data elements) can place individuals at risk, as it identifies data that must be made available on request. This means access to metadata can be just as harmful as access to the data", 'The second challenge follows: "', '."', "supports", "Confronting the Challenges of Sensitive Open Data", ["Danton, Cheryl M.", "Graziul, Christopher"], 2026, doi=ARTICLE_DOI),
    make_vcite("vcite-efic", "Public research presentations are the most common method of community consultation and are associated with high acceptance rates of EFIC studies by community members", '"', '." Surveys, focus groups, and interviews', "quantifies", "Meeting unique requirements: Community consultation and public disclosure for EFIC research", ["Dickert, N. W.", "et al."], 2021, doi="10.1111/acem.14264", venue="Academic Emergency Medicine"),
    make_vcite("vcite-buyin", "securing community buy-in to these solutions is difficult, especially in light of the potential for exploitation", 'While data trusts have gained traction, "', '." Proven community consultation models', "cautions", "Data trusts in 2021", ["Hardinges, J.", "et al."], 2021, url="https://www.adalovelaceinstitute.org/report/legal-mechanisms-data-stewardship/", venue="Ada Lovelace Institute"),
    make_vcite("vcite-fair", "Findable, Accessible, Interoperable, and Reusable", 'designed to make data "', '."', "defines", "The FAIR guiding principles for scientific data management and stewardship", ["Wilkinson, M. D.", "et al."], 2016, doi="10.1038/sdata.2016.18", venue="Scientific Data"),
    make_vcite("vcite-care", "Collective Benefit, Authority to Control, Responsibility, and Ethics", 'The CARE Principles -- "', '" -- were developed by the International', "defines", "The CARE Principles for Indigenous Data Governance", ["Carroll, S. R.", "et al."], 2020, url="https://openscholarshippress.pubpub.org/pub/xx3kj9rv"),
    make_vcite("vcite-care-purpose", "integrate Indigenous worldviews that center 'people' and 'purpose' to address critical gaps in conventional data frameworks by ensuring that Indigenous Peoples benefit from data activities and maintain control over their data", 'The CARE Principles "', '."', "defines", "The CARE Principles for Indigenous Data Governance", ["Carroll, S. R.", "et al."], 2020, url="https://openscholarshippress.pubpub.org/pub/xx3kj9rv"),
    make_vcite("vcite-laguna", "tribes can independently manage data and utilize external expertise to develop technology that reflects their priorities", 'This demonstrates that "', '."', "supports", "Recommendations from tribal experiences with tribal censuses and surveys", ["NCAIPRC"], 2017, source_type="grey"),
    make_vcite("vcite-navajo", "Notably, all research data conducted under this IRB's authority belongs to the Navajo Nation", 'the Navajo Area Indian Health Service. "', '." Today, 11 Indian Health Service IRBs', "supports", "About NNHRRB", url="https://nnhrrb.navajo-nsn.gov/aboutNNHRRB.html", source_type="grey", venue="Navajo Nation HRRB"),
    make_vcite("vcite-care-integration", "Initiatives to integrate these principles into research infrastructure not only highlight the importance of Indigenous community governance in enhancing the quality and reproducibility of research and data; they also align research with community values and facilitate responsible data stewardship", '"', '."', "supports", "Applying the CARE Principles to ecology and biodiversity research", ["Jennings, L.", "et al."], 2023, doi="10.1038/s41559-023-02161-2", venue="Nature Ecology & Evolution"),
    make_vcite("vcite-global-south", "reflect ongoing global efforts to balance the ethical tensions identified in CARE principles between open data ideals and Indigenous data sovereignty", 'These developments "', '."', "contextualizes", "Confronting the Challenges of Sensitive Open Data", ["Danton, Cheryl M.", "Graziul, Christopher"], 2026, doi=ARTICLE_DOI),
    make_vcite("vcite-colonialism", "a system that centralizes sensitive open data in ways that parallel what Couldry and Mejias (2021) call 'data colonialism' in corporate contexts, extracting value from peoples' information while withholding its benefits from data rights holders", 'failing to act would perpetuate "', '." Given the unique public value', "cautions", "The decolonial turn in data and technology research", ["Couldry, N.", "Mejias, U. A."], 2021, doi="10.1080/1369118X.2021.1986102", venue="Information, Communication & Society"),
]

vc_map = {v["id"]: v for v in VCITES}

# ── HTML generation ──────────────────────────────────────────────

import re

def render_paragraph(text):
    """Convert {v:ID}...{/v} markup to VCITE HTML spans + panels."""
    parts = []
    i = 0
    for m in re.finditer(r'\{v:([^}]+)\}(.*?)\{/v\}', text, re.DOTALL):
        parts.append(text[i:m.start()])
        vc_id = m.group(1)
        display = m.group(2)
        v = vc_map.get(vc_id)
        if v:
            h = v["target"]["hash"]
            short_h = h[:19] + "..." + h[-4:]
            rel = v["relation"]
            src = v["source"]["title"][:70]
            before = v["target"].get("text_before", "")
            after = v["target"].get("text_after", "")
            doi = v["source"].get("doi", "")
            url_val = v["source"].get("url", "")
            link = f"https://doi.org/{doi}" if doi else url_val
            authors = v["source"].get("authors", [])
            year = v["source"].get("year", "")
            if authors:
                first = authors[0].split(",")[0] if "," in authors[0] else authors[0]
                ay = f"{first} et al. ({year})" if len(authors) > 2 else f"{first} ({year})" if len(authors) == 1 else f"{first} &amp; {authors[1].split(',')[0]} ({year})"
            else:
                ay = f"({year})" if year else ""

            parts.append(
                f'<span class="vcite-mark" data-vcite="{vc_id}" onclick="toggleVcite(this)">{display}</span>'
                f'<sup class="vcite-badge" onclick="toggleVcite(this.previousElementSibling)">v</sup>'
            )
            parts.append(
                f'\n<div class="vcite-panel" id="panel-{vc_id}">'
                f'\n  <div class="vcite-panel-label">Verified citation &mdash; {ay}</div>'
                f'\n  <div class="vcite-passage"><span class="ctx">{before}</span>{v["target"]["text_exact"]}<span class="ctx">{after}</span></div>'
                f'\n  <div class="vcite-meta-row">'
                f'\n    <span><span class="vcite-relation">{rel}</span></span>'
                f'\n    <span class="vcite-hash">{short_h}</span>'
                f'\n  </div>'
                + (f'\n  <a class="vcite-link" href="{link}" target="_blank" rel="noopener">Verify in source &#x2197;</a>' if link else "")
                + f'\n</div>'
            )
        else:
            parts.append(display)
        i = m.end()
    parts.append(text[i:])
    return "".join(parts)

def build_html():
    jsonld = json.dumps(VCITES, indent=2, ensure_ascii=False)

    body_html = []
    for heading, paragraphs in SECTIONS:
        if heading:
            body_html.append(f"\n<h2>{heading}</h2>\n")
        for p in paragraphs:
            body_html.append(f"<p>{render_paragraph(p)}</p>\n")

    article_body = "\n".join(body_html)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Confronting the Challenges of Sensitive Open Data &mdash; VCITE Enhanced</title>
<script type="application/ld+json">
{jsonld}
</script>
<style>
*,*::before,*::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg: #fafaf8; --text: #1a1a1a; --muted: #666; --accent: #2563eb;
  --vcite-bg: #f0f4ff; --vcite-border: #2563eb; --vcite-hover: #e8eeff;
}}
body {{ font-family: Georgia, 'Times New Roman', serif; background: var(--bg); color: var(--text); line-height: 1.75; max-width: 720px; margin: 0 auto; padding: 40px 24px 80px; }}
header {{ margin-bottom: 40px; border-bottom: 1px solid #ddd; padding-bottom: 24px; }}
header h1 {{ font-size: 28px; line-height: 1.3; margin-bottom: 12px; }}
.meta {{ font-size: 14px; color: var(--muted); line-height: 1.6; }}
.meta a {{ color: var(--accent); text-decoration: none; }}
h2 {{ font-size: 20px; margin: 36px 0 16px; }}
p {{ margin-bottom: 16px; }}
.vcite-mark {{ background: var(--vcite-bg); border-bottom: 2px solid var(--vcite-border); padding: 1px 3px; cursor: pointer; transition: background 0.15s; }}
.vcite-mark:hover {{ background: var(--vcite-hover); }}
.vcite-badge {{ font-size: 10px; font-weight: 700; color: var(--vcite-border); vertical-align: super; margin-left: 2px; cursor: pointer; font-family: -apple-system, system-ui, sans-serif; }}
.vcite-panel {{ display: none; background: #f8fafc; border: 1px solid #d0d8e8; border-left: 3px solid var(--vcite-border); border-radius: 0 6px 6px 0; padding: 14px 16px; margin: 8px 0 16px; font-family: -apple-system, system-ui, sans-serif; font-size: 13px; line-height: 1.5; }}
.vcite-panel.open {{ display: block; }}
.vcite-panel-label {{ font-size: 9px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: var(--vcite-border); margin-bottom: 6px; }}
.vcite-passage {{ background: #fff; border-radius: 4px; padding: 10px 12px; margin-bottom: 8px; font-style: italic; color: #333; }}
.vcite-passage .ctx {{ color: #aaa; font-style: normal; }}
.vcite-meta-row {{ display: flex; gap: 16px; flex-wrap: wrap; font-size: 11px; color: var(--muted); }}
.vcite-hash {{ font-family: 'SF Mono', 'Fira Code', monospace; font-size: 10px; color: #888; }}
.vcite-relation {{ font-size: 9px; font-weight: 600; text-transform: uppercase; padding: 2px 6px; border-radius: 3px; background: #e8eeff; color: var(--vcite-border); }}
.vcite-link {{ display: inline-block; margin-top: 6px; font-size: 11px; color: var(--vcite-border); text-decoration: none; }}
.vcite-banner {{ background: linear-gradient(135deg, #f0f4ff 0%, #e8eeff 100%); border: 1px solid #d0d8e8; border-radius: 8px; padding: 16px 20px; margin-bottom: 32px; font-family: -apple-system, system-ui, sans-serif; font-size: 13px; color: #444; line-height: 1.5; }}
.vcite-banner strong {{ color: var(--vcite-border); }}
footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid #ddd; font-family: -apple-system, system-ui, sans-serif; font-size: 12px; color: var(--muted); }}
footer a {{ color: var(--accent); text-decoration: none; }}
</style>
</head>
<body>
<header>
  <h1>Confronting the Challenges of Sensitive Open Data</h1>
  <div class="meta">
    <strong>Cheryl M. Danton</strong> and <strong>Christopher Graziul</strong><br>
    <a href="{ARTICLE_URL}">Katina Magazine</a> (Annual Reviews) | 01.06.2026<br>
    DOI: <a href="https://doi.org/{ARTICLE_DOI}">{ARTICLE_DOI}</a>
  </div>
</header>

<div class="vcite-banner">
  <strong>VCITE-enhanced article.</strong> This version carries {len(VCITES)} passage-level
  cryptographic fingerprints. Click any
  <span style="background:var(--vcite-bg);border-bottom:2px solid var(--vcite-border);padding:1px 3px">highlighted passage</span>
  to see its evidence chain. <a href="https://github.com/graziul/vcite">What is VCITE?</a>
</div>

{article_body}

<footer>
  <p>
    VCITE-enhanced reproduction of
    <a href="{ARTICLE_URL}">Danton &amp; Graziul (2026)</a>,
    Katina Magazine (Annual Reviews). {len(VCITES)} passages carry
    <a href="https://github.com/graziul/vcite">VCITE</a> fingerprints (SHA-256).
  </p>
  <p style="margin-top:8px">VCITE v0.1.0 | CC-BY 4.0 (spec) / MIT (code) | Chris Graziul, IDEP</p>
</footer>

<script>
function toggleVcite(el) {{
  const id = el.dataset.vcite;
  const panel = document.getElementById('panel-' + id);
  if (!panel) return;
  document.querySelectorAll('.vcite-panel.open').forEach(p => {{
    if (p !== panel) p.classList.remove('open');
  }});
  panel.classList.toggle('open');
}}
</script>
</body>
</html>'''

if __name__ == "__main__":
    html = build_html()
    out = Path(__file__).parent / "katina-article.html"
    out.write_text(html)
    print(f"Wrote {out} ({len(html):,} bytes, {len(VCITES)} VCITE citations)")
