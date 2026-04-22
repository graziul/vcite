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
        text_before=html.escape(vcite_obj.target.text_before),
        text_exact=html.escape(vcite_obj.target.text_exact),
        text_after=html.escape(vcite_obj.target.text_after),
        relation=html.escape(vcite_obj.relation),
        hash_display=_truncate_hash(vcite_obj.target.hash),
        verify_url=_verify_url(vcite_obj),
    )


def build_vcite_css() -> str:
    """Return the VCITE CSS (read from templates/vcite.css)."""
    return _load_template("vcite.css")


def build_vcite_js() -> str:
    """Return the VCITE JS (read from templates/vcite.js)."""
    return _load_template("vcite.js")


def build_vcite_banner(count: int) -> str:
    """Return the VCITE explanation banner HTML."""
    return (
        '<div class="vcite-banner">\n'
        "  <strong>VCITE-enhanced article.</strong> This version carries "
        f"{count} passage-level\n"
        "  cryptographic fingerprints. Click any\n"
        '  <span style="background:var(--vcite-bg);border-bottom:2px solid '
        'var(--vcite-border);padding:1px 3px">highlighted passage</span>\n'
        "  to see its evidence chain. "
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


def _truncate_hash(full_hash: str) -> str:
    """Truncate a hash for display: first 12 + '...' + last 4.

    Input may be 'sha256:abcdef...' or bare hex.  We preserve the
    'sha256:' prefix and truncate only the hex portion.
    """
    if ":" in full_hash:
        prefix, hex_part = full_hash.split(":", 1)
        if len(hex_part) > 16:
            return f"{prefix}:{hex_part[:12]}...{hex_part[-4:]}"
        return full_hash
    if len(full_hash) > 16:
        return f"{full_hash[:12]}...{full_hash[-4:]}"
    return full_hash


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


def _verify_url(vcite_obj) -> str:
    """Build the verification URL from DOI or URL."""
    if vcite_obj.source.doi:
        doi = vcite_obj.source.doi
        if doi.startswith("http"):
            return html.escape(doi)
        return html.escape(f"https://doi.org/{doi}")
    if vcite_obj.source.url:
        return html.escape(vcite_obj.source.url)
    return "#"


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

    # Remove <script> blocks containing toggleVcite
    html_str = re.sub(
        r"<script>[^<]*toggleVcite[^<]*</script>",
        "",
        html_str,
        flags=re.DOTALL,
    )

    # Clean up extra blank lines
    html_str = re.sub(r"\n{3,}", "\n\n", html_str)

    return html_str
