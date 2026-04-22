"""Render VCITE-enhanced articles in HTML or Markdown.

Takes original article HTML (or Markdown), a list of ExtractedQuotes, and
their matching VCiteCitation objects, then produces output with:
  - highlighted passages (clickable)
  - expandable evidence panels
  - JSON-LD structured data in <head>
  - VCITE CSS/JS injected from templates/

Zero external dependencies — stdlib only.
"""

import html
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from parsers.html_parser import ExtractedQuote

TEMPLATE_DIR = Path(__file__).parent / "templates"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_enhanced_html(
    original_html: str,
    quotes: list,  # list[ExtractedQuote]
    vcite_objects: list,  # list[VCiteCitation]
) -> str:
    """Inject VCITE markup into *original_html*.

    For each (quote, vcite_obj) pair:
      1. Find the quoted text in the HTML body
      2. Wrap it in a clickable <span class="vcite-mark">
      3. Append a <sup class="vcite-badge">v</sup>
      4. Insert the evidence panel <div> immediately after

    Then inject VCITE CSS, JS, JSON-LD, and the explanation banner.
    """
    if len(quotes) != len(vcite_objects):
        raise ValueError(
            f"quotes ({len(quotes)}) and vcite_objects ({len(vcite_objects)}) "
            "must have equal length"
        )

    has_head = bool(re.search(r"<head[\s>]", original_html, re.IGNORECASE))
    has_body = bool(re.search(r"<body[\s>]", original_html, re.IGNORECASE))

    # If the source is a fragment (no <html>/<head>/<body>), wrap it.
    if not has_head and not has_body:
        original_html = _wrap_fragment(original_html)

    # Strip any existing VCITE markup from the input (allows re-enhancement)
    body_html = _strip_existing_vcite(original_html)

    # Group quotes by their text_exact — multi-cite splits share claim text
    # and must share a single wrapper with multiple badges (one per source).
    groups: dict[str, list] = {}
    for q, obj in zip(quotes, vcite_objects):
        groups.setdefault(q.text_exact, []).append((q, obj))

    # Work backwards (by earliest position in each group) so earlier
    # positions remain stable after insertion.
    group_items = sorted(
        groups.items(),
        key=lambda g: min(q.position for q, _ in g[1]),
        reverse=True,
    )

    # Step 1: Insert inline marks (span + N badges) — no panels yet.
    for text_exact, members in group_items:
        body_html = _inject_group(body_html, members)

    # Step 2: Collect all panels into a single container placed before </body>.
    # This avoids invalid <div> inside <p> nesting entirely.
    panels_html = '\n<div class="vcite-panels-container" style="display:contents">\n'
    for quote, vcite_obj in zip(quotes, vcite_objects):
        panels_html += build_evidence_panel(vcite_obj, quote) + "\n"
    panels_html += "</div>\n"
    body_html = _inject_before_close_body(body_html, panels_html)

    # Inject banner after <body> (or first <main>/<article>).
    body_html = _inject_banner(body_html, len(vcite_objects))

    # Inject CSS into <head>.
    css_block = "<style>\n" + _load_template("vcite.css") + "\n</style>"
    body_html = _inject_into_head(body_html, css_block)

    # Inject JSON-LD into <head>.
    jsonld = [obj.to_jsonld() for obj in vcite_objects]
    jsonld_block = (
        '<script type="application/ld+json">\n'
        + json.dumps(jsonld, indent=2, ensure_ascii=False)
        + "\n</script>"
    )
    body_html = _inject_into_head(body_html, jsonld_block)

    # Inject JS before </body>.
    js_block = "<script>\n" + _load_template("vcite.js") + "\n</script>"
    body_html = _inject_before_close_body(body_html, js_block)

    return body_html


def render_enhanced_md(
    original_md: str,
    quotes: list,  # list[ExtractedQuote]
    vcite_objects: list,  # list[VCiteCitation]
) -> str:
    """Add Pandoc VCITE span attributes to Markdown source.

    For each (quote, vcite_obj) pair, wraps the quoted text in
    ``[text]{.vcite vcite-id="..." vcite-hash="..." vcite-relation="..."}``.
    Works backwards to preserve positions.
    """
    if len(quotes) != len(vcite_objects):
        raise ValueError(
            f"quotes ({len(quotes)}) and vcite_objects ({len(vcite_objects)}) "
            "must have equal length"
        )

    pairs = list(zip(quotes, vcite_objects))
    pairs.sort(key=lambda pair: pair[0].position, reverse=True)

    result = original_md
    for quote, vcite_obj in pairs:
        escaped = quote.text_exact.replace("]", "\\]")
        attrs = (
            f'.vcite vcite-id="{vcite_obj.id}" '
            f'vcite-hash="{vcite_obj.target.hash}" '
            f'vcite-relation="{vcite_obj.relation}"'
        )
        replacement = f"[{escaped}]{{{attrs}}}"
        # Replace first occurrence of the exact text.
        idx = result.find(quote.text_exact)
        if idx >= 0:
            result = (
                result[:idx]
                + replacement
                + result[idx + len(quote.text_exact) :]
            )

    return result


# ---------------------------------------------------------------------------
# Panel / template builders
# ---------------------------------------------------------------------------


def build_evidence_panel(vcite_obj, quote) -> str:
    """Build the HTML for one evidence panel using the panel.html template."""
    template = _load_template("panel.html")
    return template.format(
        id=vcite_obj.id,
        author_label=_author_label(vcite_obj),
        source_title=_source_title(vcite_obj),
        source_meta=_source_meta(vcite_obj),
        locator_html=_locator_html(vcite_obj),
        relation=html.escape(vcite_obj.relation),
        conformance_level=vcite_obj.conformance_level,
        hash_full=html.escape(vcite_obj.target.hash),
        verification_badge=_verification_badge(vcite_obj),
        strain_badge=_strain_badge(vcite_obj),
        enrichment_detail=_enrichment_detail_block(vcite_obj),
    )


def build_vcite_css() -> str:
    """Return the VCITE CSS (read from templates/vcite.css)."""
    return _load_template("vcite.css")


def build_vcite_js() -> str:
    """Return the VCITE JS (read from templates/vcite.js)."""
    return _load_template("vcite.js")


def build_vcite_banner(count: int) -> str:
    """Return the VCITE explanation banner HTML."""
    swatch = (
        '<span style="background:var(--vcite-bg);border-bottom:2px solid '
        'var(--vcite-border);padding:1px 3px">highlighted passage</span>'
    )
    return (
        '<div class="vcite-banner">\n'
        f"  <strong>VCITE-enhanced article.</strong> Each {swatch} carries a\n"
        f"  SHA-256 fingerprint ({count} in this article) linking its exact wording to a\n"
        "  cited source. Click a passage to open its evidence chain &mdash; source, relation,\n"
        "  and the full hash. Anyone can fetch the source, locate the passage, and recompute\n"
        "  the hash to prove the wording hasn&rsquo;t been altered. Hash integrity is not\n"
        "  claim validity: that the source actually substantiates the claim remains the\n"
        "  reader&rsquo;s judgment. "
        '<a href="https://github.com/graziul/vcite">What is VCITE?</a>\n'
        "</div>"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_template_cache: dict[str, str] = {}


def _load_template(name: str) -> str:
    """Read a template file from TEMPLATE_DIR, caching the result."""
    if name not in _template_cache:
        path = TEMPLATE_DIR / name
        _template_cache[name] = path.read_text(encoding="utf-8")
    return _template_cache[name]


def _author_label(vcite_obj) -> str:
    """Build 'Author (Year)' or 'Author & Author (Year)' for the panel label.

    Uses the source's authors list and year.  Falls back to title if
    authors are missing.
    """
    authors = vcite_obj.source.authors
    year = vcite_obj.source.year

    if not authors:
        label = html.escape(vcite_obj.source.title[:60])
    elif len(authors) == 1:
        label = html.escape(_surname(authors[0]))
    elif len(authors) == 2:
        label = (
            html.escape(_surname(authors[0]))
            + " &amp; "
            + html.escape(_surname(authors[1]))
        )
    else:
        label = html.escape(_surname(authors[0])) + " et al."

    if year:
        label += f" ({year})"
    return label


def _surname(name: str) -> str:
    """Extract surname from 'Last, First' or 'First Last' formats."""
    if "," in name:
        return name.split(",")[0].strip()
    parts = name.strip().split()
    return parts[-1] if parts else name


def _source_title(vcite_obj) -> str:
    """Return the full source title, HTML-escaped; fallback if missing."""
    title = (vcite_obj.source.title or "").strip()
    if not title or title.lower() == "unknown":
        return '<span class="vcite-locator-note">Title not resolved</span>'
    return html.escape(title)


def _source_meta(vcite_obj) -> str:
    """Build the dot-separated authors / venue / year line."""
    src = vcite_obj.source
    parts: list[str] = []

    if src.authors:
        if len(src.authors) == 1:
            parts.append(html.escape(src.authors[0]))
        elif len(src.authors) == 2:
            parts.append(html.escape("; ".join(src.authors)))
        else:
            parts.append(html.escape(src.authors[0]) + " et al.")

    if src.venue:
        parts.append(html.escape(src.venue))

    if src.year:
        parts.append(str(src.year))

    if src.source_type:
        parts.append(html.escape(src.source_type))

    return " &middot; ".join(parts) if parts else (
        '<span class="vcite-locator-note">No bibliographic metadata</span>'
    )


def _doi_url(doi: str) -> str:
    """Normalize a DOI to a doi.org URL."""
    doi = doi.strip()
    if doi.startswith("http"):
        return doi
    return f"https://doi.org/{doi}"


def _locator_html(vcite_obj) -> str:
    """Build the links/locator row pointing the reader INTO the cited source.

    Prefers the most specific pointer available:
      fragment_url  →  deep-link to the passage
      page_ref      →  page marker
      section       →  section marker
    Always shows a canonical source link (DOI preferred, then URL).
    Adds an archive link when archive_url is set.
    If nothing is available, shows an honest note.
    """
    src = vcite_obj.source
    tgt = vcite_obj.target
    bits: list[str] = []

    # Specific locators within the source
    if tgt.fragment_url:
        bits.append(
            f'<a class="vcite-link" href="{html.escape(tgt.fragment_url)}" '
            'target="_blank" rel="noopener">Open passage &#x2197;</a>'
        )
    if tgt.page_ref:
        bits.append(
            '<span class="vcite-locator-note">p.&nbsp;'
            f"{html.escape(tgt.page_ref)}</span>"
        )
    if tgt.section:
        bits.append(
            '<span class="vcite-locator-note">&sect;&nbsp;'
            f"{html.escape(tgt.section)}</span>"
        )

    # Canonical source link
    canonical_label = "Open source &#x2197;"
    if src.doi:
        bits.append(
            f'<a class="vcite-link" href="{html.escape(_doi_url(src.doi))}" '
            f'target="_blank" rel="noopener">{canonical_label}</a>'
        )
    elif src.url:
        bits.append(
            f'<a class="vcite-link" href="{html.escape(src.url)}" '
            f'target="_blank" rel="noopener">{canonical_label}</a>'
        )

    # Archived copy
    if src.archive_url:
        bits.append(
            f'<a class="vcite-link" href="{html.escape(src.archive_url)}" '
            'target="_blank" rel="noopener">Archived copy &#x2197;</a>'
        )

    if not bits:
        return (
            '<span class="vcite-locator-note">No source link &mdash; '
            "document-level reference only.</span>"
        )

    # If we only have a canonical link (no specific locator), note that the
    # pointer is to the document, not a passage location inside it.
    has_specific_locator = bool(tgt.fragment_url or tgt.page_ref or tgt.section)
    if not has_specific_locator:
        bits.append(
            '<span class="vcite-locator-note">(document-level; no page '
            "or section provided)</span>"
        )

    return " ".join(bits)


# ---------------------------------------------------------------------------
# Enrichment -> panel badges & detail
# ---------------------------------------------------------------------------


_VERIFY_LABELS: dict[str, tuple[str, str, str]] = {
    # status -> (css-modifier, glyph, label)
    "verified":           ("ok",    "&#x2713;", "Source-verified"),
    "internal-only":      ("info",  "&#x229C;", "Internal hash OK"),
    "partial":            ("warn",  "&#x25D0;", "Partial match"),
    "source-drift":       ("drift", "&#x26A0;", "Source drift"),
    "internal-mismatch":  ("fail",  "&#x2717;", "Internal hash mismatch"),
    "unreachable":        ("muted", "&#x003F;", "Source unreachable"),
    "not-checked":        ("muted", "&#x2026;", "Not verified"),
}


def _verification_enrichment(vcite_obj) -> dict | None:
    """Return the ``verification`` sub-object if present, else None."""
    enrichment = getattr(vcite_obj, "enrichment", None) or {}
    v = enrichment.get("verification") if isinstance(enrichment, dict) else None
    return v if isinstance(v, dict) else None


def _strain_enrichment(vcite_obj) -> dict | None:
    """Return the ``strain`` sub-object if present, else None."""
    enrichment = getattr(vcite_obj, "enrichment", None) or {}
    s = enrichment.get("strain") if isinstance(enrichment, dict) else None
    return s if isinstance(s, dict) else None


def _verification_badge(vcite_obj) -> str:
    """Render a compact verification badge for the meta row.

    Returns empty string if no verification enrichment is present — the
    panel then just shows the source link + hash, unchanged from the
    un-verified flow.
    """
    v = _verification_enrichment(vcite_obj)
    if not v:
        return ""
    status = v.get("status") or "not-checked"
    modifier, glyph, label = _VERIFY_LABELS.get(
        status, _VERIFY_LABELS["not-checked"],
    )
    checked_at = v.get("checked_at", "")
    title = _verification_title(v)
    return (
        f'<span class="vcite-verify vcite-verify--{modifier}" title="{title}">'
        f'<span class="vcite-verify-glyph">{glyph}</span> {label}'
        + (f' &middot; <span class="vcite-verify-date">{_short_date(checked_at)}</span>'
           if checked_at else "")
        + "</span>"
    )


def _verification_title(v: dict) -> str:
    """Assemble the tooltip text (browser title= attribute) for the badge."""
    parts: list[str] = []
    if v.get("match_type"):
        sim = v.get("match_similarity")
        if isinstance(sim, (int, float)) and sim < 1.0:
            parts.append(f"Match: {v['match_type']} ({sim:.2f})")
        else:
            parts.append(f"Match: {v['match_type']}")
    if v.get("source_hash_valid") is True:
        parts.append("Source hash recomputed and matched")
    elif v.get("source_hash_valid") is False:
        parts.append("Source hash recomputed — DIFFERS from captured hash")
    if v.get("source_checked_url"):
        parts.append(f"Source: {v['source_checked_url']}")
    if v.get("fetch_error"):
        parts.append(f"Fetch error: {v['fetch_error']}")
    warnings = v.get("warnings") or []
    for w in warnings:
        parts.append(f"Warning: {w}")
    # title attribute is single-line; use " — " as separator
    return html.escape(" — ".join(parts)) if parts else ""


_STRAIN_BANDS: dict[str, tuple[str, str]] = {
    "low":      ("ok",   "Low claim distance"),
    "moderate": ("warn", "Moderate claim distance"),
    "high":     ("drift", "High claim distance"),
    "extreme":  ("fail", "Extreme claim distance"),
}


def _strain_badge(vcite_obj) -> str:
    """Render a compact strain badge. Only shown when strain enrichment exists.

    Displayed as a supplementary signal next to the verification badge.
    """
    s = _strain_enrichment(vcite_obj)
    if not s:
        return ""
    band = str(s.get("band") or "").lower()
    modifier, label = _STRAIN_BANDS.get(band, ("muted", f"Strain: {band}"))
    score = s.get("score")
    score_str = f"{score:.2f}" if isinstance(score, (int, float)) else ""
    title = _strain_title(s)
    return (
        f'<span class="vcite-strain vcite-strain--{modifier}" title="{title}">'
        f'<span class="vcite-strain-glyph">&#x223F;</span> {label}'
        + (f' &middot; <span class="vcite-strain-score">{score_str}</span>'
           if score_str else "")
        + "</span>"
    )


def _strain_title(s: dict) -> str:
    parts: list[str] = []
    method = s.get("method") or ""
    calibrated = s.get("calibrated")
    discipline = s.get("discipline") or ""
    if method:
        parts.append(f"Method: {method}")
    if calibrated and discipline:
        parts.append(f"Calibrated for {discipline}")
    elif discipline:
        parts.append(f"Discipline context: {discipline}")
    # Components (lexical)
    comps = s.get("components") or {}
    if comps:
        keep = ("jaccard_overlap", "rouge_l", "idf_overlap",
                "bigram_divergence", "embedding_distance",
                "nli_entailment", "nli_contradiction")
        summarized = ", ".join(
            f"{k}={comps[k]:.2f}" if isinstance(comps.get(k), (int, float))
            else f"{k}={comps[k]}"
            for k in keep if k in comps
        )
        if summarized:
            parts.append(summarized)
    parts.append(
        "Lexical signal only — does not certify claim validity"
    )
    return html.escape(" — ".join(parts))


def _enrichment_detail_block(vcite_obj) -> str:
    """Render a collapsible details block with verification + strain specifics.

    Only rendered when at least one of the two sub-objects is present.
    """
    v = _verification_enrichment(vcite_obj)
    s = _strain_enrichment(vcite_obj)
    if not v and not s:
        return ""

    rows: list[str] = []

    if v:
        status = v.get("status") or "not-checked"
        _, _, label = _VERIFY_LABELS.get(status, _VERIFY_LABELS["not-checked"])
        rows.append("<dt>Verification</dt>")
        rows.append(
            f'<dd>{html.escape(label)} at '
            f'{html.escape(_short_date(v.get("checked_at", "")) or "?")}</dd>'
        )
        if v.get("source_checked_url"):
            rows.append("<dt>Source checked</dt>")
            rows.append(
                f'<dd><a class="vcite-link" href="{html.escape(v["source_checked_url"])}" '
                f'target="_blank" rel="noopener">'
                f'{html.escape(v["source_checked_url"])}</a></dd>'
            )
        if v.get("match_type"):
            match_line = v["match_type"]
            sim = v.get("match_similarity")
            if isinstance(sim, (int, float)) and sim < 1.0:
                match_line = f"{match_line} (similarity {sim:.2f})"
            rows.append("<dt>Passage match</dt>")
            rows.append(f"<dd>{html.escape(match_line)}</dd>")
        if v.get("source_hash_valid") is True:
            rows.append("<dt>Source hash</dt>")
            rows.append("<dd>Recomputed; matches captured hash</dd>")
        elif v.get("source_hash_valid") is False:
            rows.append("<dt>Source hash</dt>")
            rec = v.get("source_hash_recomputed", "")
            rows.append(
                "<dd>Recomputed; <strong>differs</strong> from captured hash"
                + (f' &middot; <code>{html.escape(rec)}</code>' if rec else "")
                + "</dd>"
            )
        if v.get("fetch_error"):
            rows.append("<dt>Fetch note</dt>")
            rows.append(f'<dd>{html.escape(v["fetch_error"])}</dd>')

    if s:
        rows.append("<dt>Claim distance (strain)</dt>")
        score = s.get("score")
        score_str = f"{score:.3f}" if isinstance(score, (int, float)) else "?"
        band = html.escape(str(s.get("band") or ""))
        method = html.escape(str(s.get("method") or "lexical"))
        calibrated = " · calibrated" if s.get("calibrated") else ""
        discipline = html.escape(str(s.get("discipline") or ""))
        rows.append(
            f"<dd>{score_str} ({band}) &middot; method: {method}{calibrated}"
            + (f" &middot; {discipline}" if discipline else "")
            + "</dd>"
        )
        claim = s.get("claiming_context")
        if claim:
            rows.append("<dt>Claiming context</dt>")
            truncated = claim if len(claim) <= 400 else claim[:400] + "…"
            rows.append(
                f'<dd class="vcite-claim-context">{html.escape(truncated)}</dd>'
            )

    rows_html = "\n    ".join(rows)
    return (
        '<details class="vcite-enrichment">\n'
        '  <summary>Verification &amp; strain details</summary>\n'
        f'  <dl class="vcite-enrichment-dl">\n    {rows_html}\n  </dl>\n'
        "</details>"
    )


def _short_date(iso: str) -> str:
    """Trim an ISO-8601 timestamp to the date for display."""
    if not iso:
        return ""
    # Accept both "2026-04-22T10:15:00Z" and "2026-04-22"
    return iso.split("T", 1)[0][:10]


def _inject_group(body_html: str, members: list) -> str:
    """Inject a single span wrapping the shared claim text + one badge per citation.

    For multi-cite groups (e.g., "claim (A, 2020; B, 2021)"), all members
    share the same text_exact but cite different sources. They must share
    a single inline wrapper with multiple badges.
    """
    # Use the first member's quote for locating the text; the wrapper's
    # data-vcite holds the FIRST id; additional badges link to the rest.
    first_quote, first_obj = members[0]
    all_ids = [obj.id for _, obj in members]

    badges = "".join(
        f'<sup class="vcite-badge" data-vcite="{obj.id}" '
        f'onclick="toggleVcite(this)">v</sup>'
        for _, obj in members
    )

    target_text = first_quote.text_exact

    def _wrap(match_text: str, start: int, end: int) -> str:
        inline_mark = (
            f'<span class="vcite-mark" data-vcite="{all_ids[0]}" '
            f'data-vcite-ids="{",".join(all_ids)}" '
            f'onclick="toggleVcite(this)">{match_text}</span>'
            f'{badges}'
        )
        return body_html[:start] + inline_mark + body_html[end:]

    # First attempt: exact literal match.
    idx = body_html.find(target_text)
    if idx >= 0:
        return _wrap(target_text, idx, idx + len(target_text))

    # Second: HTML-escaped variant.
    escaped_target = html.escape(target_text)
    idx = body_html.find(escaped_target)
    if idx >= 0:
        return _wrap(escaped_target, idx, idx + len(escaped_target))

    # Third: whitespace-insensitive regex match. This handles the common
    # case where the plain-text extraction collapsed newlines to spaces
    # but the source HTML contains "word\n word" (newline + space).
    words = target_text.split()
    if len(words) >= 3:
        # Any whitespace/tags between words
        pattern = r"\s+".join(re.escape(w) for w in words)
        match = re.search(pattern, body_html)
        if match:
            return _wrap(match.group(0), match.start(), match.end())

        # Tag-tolerant: allow inline tags between words
        tag_gap = r"(?:\s*<[^>]+>\s*)*\s+"
        pattern = tag_gap.join(re.escape(w) for w in words)
        match = re.search(pattern, body_html)
        if match:
            return _wrap(match.group(0), match.start(), match.end())

    # Fourth: anchor-based fallback for very long claims.
    if len(words) >= 4:
        start_anchor = " ".join(words[0:4])
        for trim in range(0, min(4, len(words) - 4)):
            end_words = words[-(4 - trim):] if trim == 0 else words[-(4 - trim):-trim]
            end_anchor = " ".join(end_words)
            start_idx = body_html.find(start_anchor)
            if start_idx < 0:
                continue
            search_region = body_html[start_idx:start_idx + len(target_text) + 200]
            end_idx_rel = search_region.find(end_anchor)
            if end_idx_rel >= 0:
                end_pos = start_idx + end_idx_rel + len(end_anchor)
                matched = body_html[start_idx:end_pos]
                if abs(len(matched) - len(target_text)) < len(target_text) * 0.3:
                    return _wrap(matched, start_idx, end_pos)

    return body_html


def _inject_one(body_html: str, quote, vcite_obj) -> str:
    """Find quote.text_exact in *body_html* and wrap it with VCITE inline marks.

    Only inserts the <span> + <sup> wrapper — panels are collected
    separately into a container at the end of the document to avoid
    <div>-inside-<p> nesting issues.
    """
    target_text = quote.text_exact

    def _wrap(match_text: str, start: int, end: int) -> str:
        inline_mark = (
            f'<span class="vcite-mark" data-vcite="{vcite_obj.id}" '
            f'onclick="toggleVcite(this)">{match_text}</span>'
            f'<sup class="vcite-badge" '
            f'onclick="toggleVcite(this.previousElementSibling)">v</sup>'
        )
        return body_html[:start] + inline_mark + body_html[end:]

    # First attempt: exact literal match.
    idx = body_html.find(target_text)
    if idx >= 0:
        return _wrap(target_text, idx, idx + len(target_text))

    # Second attempt: match with HTML entities decoded.
    escaped_target = html.escape(target_text)
    idx = body_html.find(escaped_target)
    if idx >= 0:
        return _wrap(escaped_target, idx, idx + len(escaped_target))

    # Third attempt: anchor-based matching with fuzzy boundaries.
    # The parser may extract text with slightly different boundaries
    # (e.g., including/excluding punctuation near quote marks).
    # Use interior words as anchors — skip first/last word boundary issues.
    words = target_text.split()
    if len(words) >= 4:
        # Use words 1-3 (skipping word 0 which may have boundary issues)
        # and words -4 to -2 (skipping last word)
        start_anchor = " ".join(words[0:4])
        # Try progressively shorter end anchors
        for trim in range(0, min(4, len(words) - 4)):
            end_words = words[-(4 - trim):] if trim == 0 else words[-(4 - trim):-trim]
            end_anchor = " ".join(end_words)

            start_idx = body_html.find(start_anchor)
            if start_idx < 0:
                continue

            # Search for end anchor after start
            search_region = body_html[start_idx:start_idx + len(target_text) + 200]
            end_idx_rel = search_region.find(end_anchor)
            if end_idx_rel >= 0:
                end_pos = start_idx + end_idx_rel + len(end_anchor)
                matched = body_html[start_idx:end_pos]
                # Sanity check: matched text should be roughly same length
                if abs(len(matched) - len(target_text)) < len(target_text) * 0.3:
                    return _wrap(matched, start_idx, end_pos)

    # Fourth attempt: regex tolerating inline tags between words.
    words = target_text.split()
    if len(words) >= 3:
        tag_gap = r"(?:\s*<[^>]+>\s*)*\s+"
        pattern_parts = [re.escape(w) for w in words]
        pattern = tag_gap.join(pattern_parts)
        match = re.search(pattern, body_html)
        if match:
            return _wrap(match.group(0), match.start(), match.end())

    # Could not locate — return unchanged.
    return body_html


def _map_decoded_pos_to_encoded(encoded: str, decoded: str, decoded_pos: int) -> int:
    """Map a character position in html.unescape()'d text back to the encoded HTML.

    Walks both strings in parallel, consuming HTML entities as single
    decoded characters, to find the encoded position corresponding to
    decoded_pos.
    """
    enc_i = 0
    dec_i = 0
    while dec_i < decoded_pos and enc_i < len(encoded):
        if encoded[enc_i] == "&":
            # Find the end of the entity
            semi = encoded.find(";", enc_i)
            if semi > enc_i:
                entity = encoded[enc_i : semi + 1]
                decoded_char = html.unescape(entity)
                # This entity corresponds to len(decoded_char) decoded characters
                dec_i += len(decoded_char)
                enc_i = semi + 1
                continue
        # Regular character — same in both strings
        enc_i += 1
        dec_i += 1
    return enc_i


def _inject_banner(body_html: str, count: int) -> str:
    """Insert the VCITE banner after the opening <body>, <main>, or <article> tag."""
    banner = build_vcite_banner(count) + "\n\n"

    for tag in ("article", "main", "body"):
        pattern = re.compile(rf"(<{tag}[^>]*>)", re.IGNORECASE)
        match = pattern.search(body_html)
        if match:
            insert_pos = match.end()
            return body_html[:insert_pos] + "\n" + banner + body_html[insert_pos:]

    # No recognized wrapper — prepend.
    return banner + body_html


def _inject_into_head(body_html: str, block: str) -> str:
    """Insert *block* before </head>."""
    match = re.search(r"</head>", body_html, re.IGNORECASE)
    if match:
        return body_html[: match.start()] + block + "\n" + body_html[match.start() :]
    # No </head> — insert at the very beginning.
    return block + "\n" + body_html


def _inject_before_close_body(body_html: str, block: str) -> str:
    """Insert *block* before </body>."""
    match = re.search(r"</body>", body_html, re.IGNORECASE)
    if match:
        return body_html[: match.start()] + block + "\n" + body_html[match.start() :]
    # No </body> — append at the very end.
    return body_html + "\n" + block


def _wrap_fragment(fragment: str) -> str:
    """Wrap a bare HTML fragment in a full document skeleton."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        "<title>VCITE-Enhanced Article</title>\n"
        "</head>\n"
        "<body>\n"
        + fragment
        + "\n</body>\n"
        "</html>"
    )


def _strip_existing_vcite(html_str: str) -> str:
    """Remove all existing VCITE markup so the article can be re-enhanced.

    Strips:
    - <span class="vcite-mark" ...>text</span> → keeps text
    - <sup class="vcite-badge" ...>v</sup> → removed
    - <div class="vcite-panel" ...>...</div> → removed (nested-div aware)
    - <div class="vcite-banner" ...>...</div> → removed
    - <div class="vcite-panels-container" ...>...</div> → removed
    - <script type="application/ld+json"> containing VCiteCitation → removed
    - <style> containing vcite- classes → removed
    - <script> containing toggleVcite → removed
    """
    # Remove vcite-badge sup elements
    html_str = re.sub(
        r'<sup\s+class="vcite-badge"[^>]*>.*?</sup>', "", html_str, flags=re.DOTALL
    )

    # Unwrap vcite-mark spans (keep inner text)
    html_str = re.sub(
        r'<span\s+class="vcite-mark"[^>]*>(.*?)</span>',
        r"\1",
        html_str,
        flags=re.DOTALL,
    )

    # Remove vcite div blocks (panels, banner, container) — handle nesting
    for cls in ("vcite-panel", "vcite-banner", "vcite-panels-container"):
        pattern = re.compile(rf'<div\s+[^>]*class="[^"]*{cls}[^"]*"[^>]*>')
        while True:
            m = pattern.search(html_str)
            if not m:
                break
            start = m.start()
            pos = m.end()
            depth = 1
            while pos < len(html_str) and depth > 0:
                open_m = re.search(r"<div[\s>]", html_str[pos:])
                close_m = re.search(r"</div>", html_str[pos:])
                if close_m is None:
                    break
                if open_m and open_m.start() < close_m.start():
                    depth += 1
                    pos += open_m.end()
                else:
                    depth -= 1
                    if depth == 0:
                        html_str = html_str[:start] + html_str[pos + close_m.end() :]
                        break
                    pos += close_m.end()

    # Remove JSON-LD blocks containing VCiteCitation. Iterate so we can
    # check the full content (not just the start) for "VCiteCitation", which
    # may appear after nested braces in source/target sub-objects.
    def _strip_vcite_jsonld(s: str) -> str:
        out = []
        i = 0
        pattern = re.compile(
            r'<script\s+type="application/ld\+json">', re.IGNORECASE
        )
        while True:
            m = pattern.search(s, i)
            if not m:
                out.append(s[i:])
                break
            end = s.find("</script>", m.end())
            if end < 0:
                out.append(s[i:])
                break
            block = s[m.start():end + len("</script>")]
            if "VCiteCitation" in block:
                # Drop this block
                out.append(s[i:m.start()])
            else:
                out.append(s[i:end + len("</script>")])
            i = end + len("</script>")
        return "".join(out)

    html_str = _strip_vcite_jsonld(html_str)

    # Remove <style> blocks containing vcite- classes
    html_str = re.sub(
        r"<style>\s*/\*.*?VCITE.*?\*/.*?</style>",
        "",
        html_str,
        flags=re.DOTALL | re.IGNORECASE,
    )
    html_str = re.sub(
        r"<style>[^<]*\.vcite-[^<]*</style>",
        "",
        html_str,
        flags=re.DOTALL,
    )

    # Remove <script> blocks whose body contains toggleVcite. Use a stateful
    # scan rather than a naive regex, because bundled IIFE bodies contain
    # literal '<' characters (e.g., comparisons, arrow fns) that would break
    # a [^<]* boundary. We only strip <script> tags without a type attribute
    # (our injected VCITE JS is untyped) and leave application/ld+json
    # blocks alone (they're handled above by _strip_vcite_jsonld).
    def _strip_vcite_script(s: str) -> str:
        out: list[str] = []
        i = 0
        pattern = re.compile(r"<script\s*>", re.IGNORECASE)
        while True:
            m = pattern.search(s, i)
            if not m:
                out.append(s[i:])
                break
            end = s.find("</script>", m.end())
            if end < 0:
                out.append(s[i:])
                break
            block = s[m.start() : end + len("</script>")]
            if "toggleVcite" in block or "attachVerifyButtons" in block:
                out.append(s[i : m.start()])
            else:
                out.append(s[i : end + len("</script>")])
            i = end + len("</script>")
        return "".join(out)

    html_str = _strip_vcite_script(html_str)

    # Clean up extra blank lines
    html_str = re.sub(r"\n{3,}", "\n\n", html_str)

    return html_str
