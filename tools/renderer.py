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

    # Work backwards so earlier positions remain stable after insertion.
    pairs = list(zip(quotes, vcite_objects))
    pairs.sort(key=lambda pair: pair[0].position, reverse=True)

    body_html = original_html
    for quote, vcite_obj in pairs:
        body_html = _inject_one(body_html, quote, vcite_obj)

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


def _inject_one(body_html: str, quote, vcite_obj) -> str:
    """Find quote.text_exact in *body_html* and wrap it with VCITE markup.

    Strategy: search for the literal text inside the HTML body content.
    We use a regex that tolerates inline HTML tags within the passage
    (e.g., <em>, <strong>) by allowing optional tag sequences between
    words.
    """
    target_text = quote.text_exact

    # First attempt: exact literal match.
    idx = body_html.find(target_text)
    if idx >= 0:
        panel = build_evidence_panel(vcite_obj, quote)
        wrapped = (
            f'<span class="vcite-mark" data-vcite="{vcite_obj.id}" '
            f'onclick="toggleVcite(this)">{target_text}</span>'
            f'<sup class="vcite-badge" '
            f'onclick="toggleVcite(this.previousElementSibling)">v</sup>\n'
            + panel
        )
        return body_html[:idx] + wrapped + body_html[idx + len(target_text) :]

    # Second attempt: match with HTML entities decoded.
    escaped_target = html.escape(target_text)
    idx = body_html.find(escaped_target)
    if idx >= 0:
        panel = build_evidence_panel(vcite_obj, quote)
        wrapped = (
            f'<span class="vcite-mark" data-vcite="{vcite_obj.id}" '
            f'onclick="toggleVcite(this)">{escaped_target}</span>'
            f'<sup class="vcite-badge" '
            f'onclick="toggleVcite(this.previousElementSibling)">v</sup>\n'
            + panel
        )
        return (
            body_html[:idx] + wrapped + body_html[idx + len(escaped_target) :]
        )

    # Third attempt: build a regex that allows inline tags between words
    # and tolerates &mdash; / -- / — variations.
    words = target_text.split()
    if len(words) >= 3:
        # Escape each word for regex, allow tags + whitespace between them
        tag_gap = r"(?:\s*<[^>]+>\s*)*\s+"
        pattern_parts = [re.escape(w) for w in words]
        pattern = tag_gap.join(pattern_parts)
        match = re.search(pattern, body_html)
        if match:
            original_span = match.group(0)
            panel = build_evidence_panel(vcite_obj, quote)
            wrapped = (
                f'<span class="vcite-mark" data-vcite="{vcite_obj.id}" '
                f'onclick="toggleVcite(this)">{original_span}</span>'
                f'<sup class="vcite-badge" '
                f'onclick="toggleVcite(this.previousElementSibling)">v</sup>\n'
                + panel
            )
            return body_html[: match.start()] + wrapped + body_html[match.end() :]

    # Could not locate — return unchanged (caller may log a warning).
    return body_html


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
