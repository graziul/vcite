#!/usr/bin/env python3
"""VCITE enhance -- upgrade existing citations to passage-level verified citations.

Usage:
    python tools/enhance.py article.html -o enhanced.html
    python tools/enhance.py article.md -o enhanced.md
    python tools/enhance.py article.html --format json  # output VCITE objects only
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add implementations and tools to path
TOOLS_DIR = Path(__file__).parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "implementations" / "python"))
sys.path.insert(0, str(TOOLS_DIR))

from vcite import compute_hash, VCiteCitation, VCiteSource, VCiteTarget
from parsers.html_parser import extract_quotes_html, ExtractedQuote
from parsers.md_parser import extract_quotes_md
from parsers.latex_parser import extract_quotes_latex
from metadata import resolve_citation, SourceMetadata
from fragment_url import build_text_fragment_url
from archive import snapshot_source, lookup_existing_snapshot


def _log(msg: str):
    """Print progress to stderr so stdout stays clean for piped output."""
    print(msg, file=sys.stderr)


def _build_vcite_object(
    index: int,
    quote: ExtractedQuote,
    metadata: SourceMetadata | None,
    generate_fragment_url: bool = True,
) -> VCiteCitation:
    """Build a VCiteCitation from an extracted quote and optional metadata.

    When ``generate_fragment_url`` is True (default), a W3C Text Fragment
    URL is computed heuristically from the best available source URL and
    attached to ``target.fragment_url``. Set to False for deterministic
    test output.
    """
    source = VCiteSource(
        title=metadata.title if metadata else "Unknown",
        authors=metadata.authors if metadata else [],
        year=metadata.year if metadata else None,
        doi=metadata.doi if metadata else None,
        url=metadata.url if metadata else None,
        archive_url=metadata.archive_url if metadata else None,
        venue=metadata.venue if metadata else None,
        source_type=metadata.source_type if metadata else "academic",
    )

    target = VCiteTarget(
        text_exact=quote.text_exact,
        text_before=quote.text_before[-50:] if quote.text_before else "",
        text_after=quote.text_after[:50] if quote.text_after else "",
    )

    if generate_fragment_url:
        # Source URL precedence: metadata.url -> doi.org resolver.
        base_url: str | None = None
        if metadata and metadata.url:
            base_url = metadata.url
        elif metadata and metadata.doi:
            base_url = f"https://doi.org/{metadata.doi}"
        if base_url:
            fragment = build_text_fragment_url(
                base_url,
                target.text_exact,
                target.text_before,
                target.text_after,
            )
            if fragment:
                target.fragment_url = fragment

    relation = infer_relation(quote)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return VCiteCitation(
        vcite="1.0",
        id=f"vcite-{index + 1:03d}",
        source=source,
        target=target,
        relation=relation,
        captured_at=now,
        captured_by="model",
    )


def infer_relation(quote: ExtractedQuote) -> str:
    """Infer relation type from the cited passage and its immediate context.

    Uses the quote text itself (not the full paragraph) to avoid false
    triggers from rhetorical contrast words in surrounding prose.
    'contradicts' requires explicit disagreement language in the quote itself.
    Default is 'supports' — the most common citation relation.
    """
    # Use the quote text + short surrounding context, not full paragraph
    text = quote.text_exact.lower()
    ctx = (quote.text_before + " " + quote.text_after).lower()

    # defines: the quote IS a definition
    if any(w in text for w in ("defined as", "refers to", "means", "is termed")):
        return "defines"
    if any(w in ctx for w in ("define", "definition of")):
        return "defines"

    # contradicts: only if the quote itself expresses disagreement
    if any(w in text for w in ("disagree", "challenge", "refute", "contrary to", "not supported")):
        return "contradicts"

    # quantifies: the quote contains numbers or measurements
    if any(w in text for w in ("percent", "%", "rate", "proportion", "number of", "million")):
        return "quantifies"
    if re.search(r"\d+[.,]?\d*\s*%", text):
        return "quantifies"

    # cautions: the quote warns about risks or limitations
    if any(w in text for w in ("warn", "caution", "risk", "concern", "difficult", "harm")):
        return "cautions"

    # method: the quote describes a methodology
    if any(w in text for w in ("method", "approach", "technique", "framework", "model", "protocol")):
        return "method"

    # contextualizes: background information
    if any(w in text for w in ("history", "tradition", "background", "context", "evolution of")):
        return "contextualizes"

    return "supports"


def enhance_article(
    input_path: Path,
    output_path: Path,
    fmt: str = "html",
    skip_metadata: bool = False,
    no_fragment_url: bool = False,
    archive_mode: str = "off",
):
    """Main enhancement pipeline.

    1. Parse input to extract quoted passages
    2. Resolve citation hints to metadata (unless --no-metadata)
    3. Optionally request/lookup Wayback Machine snapshots (``archive_mode``):
       "off" (default), "snapshot" (lookup + SPN POST), or "lookup" (no POST).
    4. Build VCITE objects
    5. Render output
    """
    content = input_path.read_text(encoding="utf-8")

    # 1. Detect format and extract quotes
    if input_path.suffix in (".html", ".htm"):
        quotes = extract_quotes_html(content)
    elif input_path.suffix in (".md", ".markdown"):
        quotes = extract_quotes_md(content)
    elif input_path.suffix in (".tex", ".latex"):
        quotes = extract_quotes_latex(content)
    else:
        _log(f"Unsupported format: {input_path.suffix}")
        sys.exit(1)

    _log(f"Found {len(quotes)} quoted passages")

    # 2. Resolve citations to metadata and build VCITE objects
    if archive_mode != "off" and skip_metadata:
        _log(
            "    Note: --archive/--archive-lookup-only has no effect with "
            "--no-metadata (no URL to archive); skipping archival."
        )
        archive_mode = "off"

    vcite_objects: list[VCiteCitation] = []
    for i, quote in enumerate(quotes):
        _log(f"  [{i + 1}/{len(quotes)}] {quote.text_exact[:60]}...")

        metadata = None
        if not skip_metadata and quote.citation_hint:
            _log(f"    Resolving: {quote.citation_hint}")
            metadata = resolve_citation(quote.citation_hint)
            if metadata:
                _log(
                    f"    -> {metadata.title[:50]}... "
                    f"({metadata.doi or 'no DOI'})"
                )
            else:
                _log("    -> No metadata found")

        # 2b. Optionally attach a Wayback Machine archive_url.
        if archive_mode != "off" and metadata and not metadata.archive_url:
            archive_target = metadata.url or (
                f"https://doi.org/{metadata.doi}" if metadata.doi else None
            )
            if archive_target:
                if archive_mode == "lookup":
                    snap = lookup_existing_snapshot(archive_target)
                else:
                    snap = snapshot_source(archive_target)
                _log(
                    "    Archiving: "
                    f"{archive_target} -> {snap if snap else '(failed)'}"
                )
                if snap:
                    metadata.archive_url = snap

        citation = _build_vcite_object(
            i, quote, metadata, generate_fragment_url=not no_fragment_url
        )
        vcite_objects.append(citation)

    # 3. Render output
    if fmt == "json":
        _render_json(vcite_objects, output_path)
    elif fmt == "html":
        _render_enhanced_html(content, quotes, vcite_objects, output_path)
    elif fmt == "md":
        _render_enhanced_md(content, quotes, vcite_objects, output_path)
    elif fmt == "tex":
        _render_enhanced_tex(content, quotes, vcite_objects, output_path)

    _log(f"\nWrote {output_path} ({len(vcite_objects)} VCITE citations)")


def _render_json(
    vcite_objects: list[VCiteCitation], output_path: Path
):
    """Output VCITE objects as a JSON array."""
    data = [c.to_dict() for c in vcite_objects]
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    if str(output_path) == "-":
        sys.stdout.write(json_str + "\n")
    else:
        output_path.write_text(json_str + "\n", encoding="utf-8")


def _render_enhanced_html(
    original_html: str,
    quotes: list[ExtractedQuote],
    vcite_objects: list[VCiteCitation],
    output_path: Path,
):
    """Render full VCITE-enhanced HTML with inline marks, panels, CSS, and JS."""
    from renderer import render_enhanced_html

    result = render_enhanced_html(original_html, quotes, vcite_objects)
    output_path.write_text(result, encoding="utf-8")


def _render_enhanced_md(
    original_md: str,
    quotes: list[ExtractedQuote],
    vcite_objects: list[VCiteCitation],
    output_path: Path,
):
    """Append a VCITE metadata block to the Markdown file."""
    lines = [original_md.rstrip()]
    lines.append("\n\n---\n")
    lines.append("<!-- VCITE metadata -->\n")
    lines.append("```json\n")
    data = [c.to_dict() for c in vcite_objects]
    lines.append(json.dumps(data, indent=2, ensure_ascii=False))
    lines.append("\n```\n")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _render_enhanced_tex(
    original_tex: str,
    quotes: list[ExtractedQuote],
    vcite_objects: list[VCiteCitation],
    output_path: Path,
):
    """Append a VCITE metadata block inside a LaTeX comment.

    Full LaTeX rendering (wrapping each quote in \\begin{vcitepassage}
    macros, emitting \\vcite calls) is out of scope for the extraction
    pass; for now we round-trip the source and emit the JSON-LD manifest
    as a trailing comment block, which LaTeX will ignore at typeset time
    but downstream tools can parse.
    """
    data = [c.to_dict() for c in vcite_objects]
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    # Prefix every line with "% " so the JSON is a legal LaTeX comment.
    commented = "\n".join("% " + line for line in json_str.split("\n"))
    block = (
        "\n\n% ====== VCITE metadata (auto-generated) ======\n"
        f"{commented}\n"
        "% ====== end VCITE metadata ======\n"
    )
    output_path.write_text(original_tex.rstrip() + block, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Enhance citations with VCITE passage-level verification"
    )
    parser.add_argument("input", help="Input article (HTML or Markdown)")
    parser.add_argument(
        "-o",
        "--output",
        help="Output path (default: input with .vcite suffix; use - for stdout with --format json)",
    )
    parser.add_argument(
        "--format",
        choices=["html", "md", "tex", "json"],
        default=None,
        help="Output format (default: infer from output extension)",
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Skip CrossRef/Unpaywall metadata lookup (offline mode)",
    )
    parser.add_argument(
        "--no-fragment-url",
        action="store_true",
        help=(
            "Skip W3C Text Fragment URL generation for target.fragment_url "
            "(escape hatch for deterministic test output)"
        ),
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help=(
            "Populate source.archive_url via archive.org (lookup + Save Page "
            "Now fallback). Save Page Now may take 30-60s per URL and is "
            "anonymous/unauthenticated (rate-limited). Requires metadata "
            "resolution; ignored under --no-metadata."
        ),
    )
    parser.add_argument(
        "--archive-lookup-only",
        action="store_true",
        help=(
            "Like --archive but only queries the Wayback `available` API — "
            "never triggers Save Page Now. Suitable for CI and reproducible "
            "runs. Mutually exclusive with --archive."
        ),
    )
    args = parser.parse_args()

    if args.archive and args.archive_lookup_only:
        _log("--archive and --archive-lookup-only are mutually exclusive")
        sys.exit(1)
    archive_mode = (
        "snapshot" if args.archive
        else "lookup" if args.archive_lookup_only
        else "off"
    )

    input_path = Path(args.input)
    if not input_path.exists():
        _log(f"File not found: {input_path}")
        sys.exit(1)

    # Determine output path
    # When --format json and no -o given, default to stdout for piping
    if args.output == "-":
        output_path = Path("-")
    elif args.output:
        output_path = Path(args.output)
    elif args.format == "json":
        output_path = Path("-")  # JSON defaults to stdout for piping
    else:
        output_path = input_path.with_suffix(f".vcite{input_path.suffix}")

    # Determine format
    fmt = args.format
    if not fmt:
        if str(output_path) == "-":
            fmt = "json"
        elif output_path.suffix in (".md", ".markdown"):
            fmt = "md"
        elif output_path.suffix in (".tex", ".latex"):
            fmt = "tex"
        elif output_path.suffix == ".json":
            fmt = "json"
        else:
            fmt = "html"

    # Handle stdout for JSON
    if str(output_path) == "-" and fmt != "json":
        _log("Stdout output (-) only supported with --format json")
        sys.exit(1)

    enhance_article(
        input_path,
        output_path,
        fmt,
        skip_metadata=args.no_metadata,
        no_fragment_url=args.no_fragment_url,
        archive_mode=archive_mode,
    )


if __name__ == "__main__":
    main()
