#!/usr/bin/env python3
"""VCITE verify — reverse-lookup and cryptographic verification of citations.

Given a VCITE citation (JSON file, JSON array, or enhanced HTML), fetches
the original source document, locates the cited passage, recomputes the
SHA-256 fingerprint, and reports whether the citation is accurate.

This closes the verification loop:
  Author creates VCITE citation → Reader verifies against source

Usage:
    python tools/verify.py citation.json
    python tools/verify.py citations.json --offline
    python tools/verify.py enhanced-article.html
    python tools/verify.py citation.json --format json
"""

import argparse
import difflib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# Add implementations and tools to path
TOOLS_DIR = Path(__file__).parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "implementations" / "python"))
sys.path.insert(0, str(TOOLS_DIR))

from vcite import compute_hash, VCiteCitation
from vcite.hash import normalize_segment
from source_fetch import fetch_source, FetchResult


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PassageMatch:
    """Result of searching for a cited passage in source text."""

    found: bool
    matched_text: str = ""  # the text found in the source
    char_start: int = -1
    char_end: int = -1
    context_before: str = ""  # context window extracted from source
    context_after: str = ""
    match_type: str = ""  # "exact", "normalized", "fuzzy"
    similarity: float = 0.0  # 0.0-1.0 for fuzzy matches


@dataclass
class VerificationResult:
    """Full verification result for one VCITE citation."""

    citation_id: str
    source_title: str

    # Overall status
    status: str  # "verified", "hash_mismatch", "passage_not_found",
                 # "source_unavailable", "insufficient_metadata",
                 # "passage_verified" (passage found but context differs)

    # Internal consistency (hash matches embedded text)
    internal_hash_valid: bool

    # Source verification (hash matches original source)
    source_hash_valid: Optional[bool] = None
    source_hash_recomputed: str = ""

    # Passage location in source
    passage_match: Optional[PassageMatch] = None

    # Source fetch details
    source_url: str = ""
    fetch_error: str = ""

    # Citation metadata for context
    conformance_level: int = 0
    relation: str = ""
    page_ref: str = ""
    captured_by: str = ""

    # Warnings (non-fatal issues)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {}
        for k, v in asdict(self).items():
            if v is not None and v != "" and v != [] and v != -1:
                d[k] = v
        return d


# ---------------------------------------------------------------------------
# Passage search
# ---------------------------------------------------------------------------

def find_passage(source_text: str, citation: VCiteCitation) -> PassageMatch:
    """Search for the cited passage in the source document text.

    Tries three strategies in order:
    1. Exact match (normalized whitespace, case-sensitive)
    2. Normalized match (case-insensitive, whitespace-collapsed)
    3. Fuzzy match (allows small edits, using difflib)
    """
    target_text = citation.target.text_exact
    if not target_text:
        return PassageMatch(found=False)

    # Strategy 1: Exact normalized match (preserves case)
    norm_source = normalize_segment(source_text)
    norm_target = normalize_segment(target_text)

    idx = norm_source.find(norm_target)
    if idx >= 0:
        return _build_match(source_text, norm_source, idx, len(norm_target), "exact", 1.0)

    # Strategy 2: Case-insensitive match
    lower_source = norm_source.lower()
    lower_target = norm_target.lower()

    idx = lower_source.find(lower_target)
    if idx >= 0:
        return _build_match(source_text, norm_source, idx, len(norm_target),
                            "normalized", 1.0)

    # Strategy 3: Fuzzy match using sliding window
    match = _fuzzy_search(norm_source, norm_target)
    if match:
        return match

    return PassageMatch(found=False)


def _build_match(
    original_text: str,
    normalized_text: str,
    norm_idx: int,
    norm_length: int,
    match_type: str,
    similarity: float,
) -> PassageMatch:
    """Build a PassageMatch from a position in normalized text."""
    matched = normalized_text[norm_idx:norm_idx + norm_length]

    # Extract context windows (50 code points, matching VCITE spec)
    before_start = max(0, norm_idx - 50)
    context_before = normalized_text[before_start:norm_idx]
    context_after = normalized_text[norm_idx + norm_length:norm_idx + norm_length + 50]

    return PassageMatch(
        found=True,
        matched_text=matched,
        char_start=norm_idx,
        char_end=norm_idx + norm_length,
        context_before=context_before,
        context_after=context_after,
        match_type=match_type,
        similarity=similarity,
    )


def _fuzzy_search(
    source: str,
    target: str,
    threshold: float = 0.85,
) -> Optional[PassageMatch]:
    """Sliding-window fuzzy search for target in source.

    Uses difflib.SequenceMatcher to find the best approximate match.
    Only returns a match if similarity >= threshold.
    """
    target_len = len(target)
    if target_len == 0 or len(source) == 0:
        return None

    # For very long sources, use a two-phase approach:
    # Phase 1: Find candidate regions using short anchors
    # Phase 2: Score candidates with full SequenceMatcher

    best_ratio = 0.0
    best_start = -1
    best_end = -1
    best_text = ""

    # Extract anchor words from the target (first few significant words)
    target_lower = target.lower()
    words = target_lower.split()
    if len(words) < 3:
        return None  # too short for reliable fuzzy matching

    # Use 3-word anchors from the start and middle of the target
    anchors = []
    if len(words) >= 3:
        anchors.append(" ".join(words[:3]))
    if len(words) >= 6:
        mid = len(words) // 2
        anchors.append(" ".join(words[mid:mid + 3]))

    source_lower = source.lower()

    # Find candidate positions near anchors
    candidate_positions: set[int] = set()
    for anchor in anchors:
        search_start = 0
        while True:
            idx = source_lower.find(anchor, search_start)
            if idx < 0:
                break
            # The passage could start up to target_len chars before the anchor
            region_start = max(0, idx - target_len)
            candidate_positions.add(region_start)
            # Also try positions near the anchor
            for offset in range(0, min(target_len, 200), 20):
                pos = max(0, idx - offset)
                candidate_positions.add(pos)
            search_start = idx + 1

    if not candidate_positions:
        # No anchors found — try exhaustive search on shorter passages only
        if target_len > 500 or len(source) > 50000:
            return None
        # Small text: try every position
        step = max(1, target_len // 4)
        candidate_positions = set(range(0, len(source) - target_len + 1, step))

    # Score candidates
    window_tolerance = int(target_len * 0.2)  # allow ±20% length variation
    for start in sorted(candidate_positions):
        for length in (target_len, target_len - window_tolerance,
                       target_len + window_tolerance):
            if length <= 0:
                continue
            end = start + length
            if end > len(source):
                continue
            candidate = source[start:end]
            ratio = difflib.SequenceMatcher(
                None, target_lower, candidate.lower()
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_start = start
                best_end = end
                best_text = candidate

    if best_ratio >= threshold and best_start >= 0:
        before_start = max(0, best_start - 50)
        context_before = source[before_start:best_start]
        context_after = source[best_end:best_end + 50]

        return PassageMatch(
            found=True,
            matched_text=best_text,
            char_start=best_start,
            char_end=best_end,
            context_before=context_before,
            context_after=context_after,
            match_type="fuzzy",
            similarity=best_ratio,
        )

    return None


# ---------------------------------------------------------------------------
# Verification logic
# ---------------------------------------------------------------------------

def verify_citation_offline(citation: VCiteCitation) -> VerificationResult:
    """Verify internal consistency only (no network fetch).

    Checks that the embedded hash matches text_exact + context.
    """
    internal_valid = citation.verify()

    warnings = []
    if citation.captured_by == "model" and not citation.source.archive_url:
        warnings.append(
            "AI-generated citation without archive_url "
            "(spec B5 recommends L3 for model citations)"
        )
    if citation.conformance_level == 1:
        warnings.append("L1 citation: no context windows or source URL for verification")

    return VerificationResult(
        citation_id=citation.id,
        source_title=citation.source.title,
        status="verified" if internal_valid else "hash_mismatch",
        internal_hash_valid=internal_valid,
        conformance_level=citation.conformance_level,
        relation=citation.relation,
        page_ref=citation.target.page_ref or "",
        captured_by=citation.captured_by,
        warnings=warnings,
    )


def verify_citation(citation: VCiteCitation) -> VerificationResult:
    """Full verification: check internal hash, fetch source, verify passage.

    Steps:
    1. Verify internal hash consistency
    2. Fetch original source document
    3. Locate cited passage in source text
    4. Extract context windows from source
    5. Recompute hash from source text + context
    6. Compare recomputed hash with claimed hash
    """
    # Step 1: Internal consistency check
    internal_valid = citation.verify()

    warnings: list[str] = []
    if citation.captured_by == "model" and not citation.source.archive_url:
        warnings.append(
            "AI-generated citation without archive_url "
            "(spec B5 recommends L3 for model citations)"
        )

    # Check if we have enough metadata to fetch
    has_fetchable = (
        citation.source.url
        or citation.source.doi
        or citation.source.archive_url
    )
    if not has_fetchable:
        return VerificationResult(
            citation_id=citation.id,
            source_title=citation.source.title,
            status="insufficient_metadata",
            internal_hash_valid=internal_valid,
            conformance_level=citation.conformance_level,
            relation=citation.relation,
            page_ref=citation.target.page_ref or "",
            captured_by=citation.captured_by,
            warnings=warnings + [
                "No URL, DOI, or archive_url — cannot fetch source for verification"
            ],
        )

    # Step 2: Fetch source document
    fetch_result = fetch_source(citation)
    if fetch_result.error or not fetch_result.text:
        return VerificationResult(
            citation_id=citation.id,
            source_title=citation.source.title,
            status="source_unavailable",
            internal_hash_valid=internal_valid,
            source_url=fetch_result.url,
            fetch_error=fetch_result.error,
            conformance_level=citation.conformance_level,
            relation=citation.relation,
            page_ref=citation.target.page_ref or "",
            captured_by=citation.captured_by,
            warnings=warnings,
        )

    # Stash fetched text for optional drift tracking (not serialized)
    _fetched_text = fetch_result.text
    _fetched_url = fetch_result.url

    # Step 3: Find the passage in the source
    match = find_passage(fetch_result.text, citation)
    if not match.found:
        return VerificationResult(
            citation_id=citation.id,
            source_title=citation.source.title,
            status="passage_not_found",
            internal_hash_valid=internal_valid,
            passage_match=match,
            source_url=fetch_result.url,
            conformance_level=citation.conformance_level,
            relation=citation.relation,
            page_ref=citation.target.page_ref or "",
            captured_by=citation.captured_by,
            warnings=warnings + [
                "Passage not found in source — source may have been "
                "updated since citation was created"
            ],
        )

    # Step 4-5: Recompute hash from source text + context
    recomputed_hash = compute_hash(
        match.matched_text,
        match.context_before,
        match.context_after,
    )

    # Step 6: Compare hashes
    source_hash_valid = (recomputed_hash == citation.target.hash)

    if match.match_type == "fuzzy" and match.similarity < 1.0:
        warnings.append(
            f"Fuzzy match (similarity: {match.similarity:.1%}) — "
            "source text differs slightly from cited text"
        )

    if not source_hash_valid and match.match_type in ("exact", "normalized"):
        # The passage was found but context differs — hash won't match
        # because context windows in the source differ from the author's.
        # This is expected when the author captured different context.
        warnings.append(
            "Passage found in source but context windows differ from citation — "
            "this is normal if the author used different surrounding text"
        )

    # Determine overall status
    if source_hash_valid and internal_valid:
        status = "verified"
    elif match.found and internal_valid and match.match_type in ("exact", "normalized"):
        # Passage is genuinely in the source; hash mismatch is due to
        # context window differences (a common and benign scenario)
        status = "passage_verified"
    else:
        status = "hash_mismatch"

    result = VerificationResult(
        citation_id=citation.id,
        source_title=citation.source.title,
        status=status,
        internal_hash_valid=internal_valid,
        source_hash_valid=source_hash_valid,
        source_hash_recomputed=recomputed_hash,
        passage_match=match,
        source_url=fetch_result.url,
        conformance_level=citation.conformance_level,
        relation=citation.relation,
        page_ref=citation.target.page_ref or "",
        captured_by=citation.captured_by,
        warnings=warnings,
    )
    # Attach fetched text for drift tracking (private, not serialized)
    result._source_text = _fetched_text
    return result


# ---------------------------------------------------------------------------
# Citation loading
# ---------------------------------------------------------------------------

def load_citations_from_json(path: Path) -> list[VCiteCitation]:
    """Load VCITE citations from a JSON file (single object or array)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [VCiteCitation.from_dict(item) for item in data]
    if isinstance(data, dict):
        return [VCiteCitation.from_dict(data)]
    raise ValueError(f"Expected JSON object or array, got {type(data).__name__}")


def load_citations_from_html(path: Path) -> list[VCiteCitation]:
    """Extract VCITE citations from JSON-LD embedded in an HTML file."""
    content = path.read_text(encoding="utf-8")
    citations: list[VCiteCitation] = []

    # Find JSON-LD script blocks containing VCiteCitation
    pattern = re.compile(
        r'<script\s+type="application/ld\+json">\s*([\s\S]*?)\s*</script>',
        re.IGNORECASE,
    )
    for match in pattern.finditer(content):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue

        # Could be a single object or an array
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") != "VCiteCitation":
                continue
            # Strip JSON-LD keys before deserializing
            clean = {k: v for k, v in item.items()
                     if not k.startswith("@")}
            try:
                citations.append(VCiteCitation.from_dict(clean))
            except (KeyError, ValueError):
                continue

    return citations


def load_citations(path: Path) -> list[VCiteCitation]:
    """Load VCITE citations from a file (JSON or HTML)."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_citations_from_json(path)
    if suffix in (".html", ".htm"):
        return load_citations_from_html(path)
    # Try JSON first, fall back to HTML
    try:
        return load_citations_from_json(path)
    except (json.JSONDecodeError, KeyError, ValueError):
        return load_citations_from_html(path)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

_STATUS_SYMBOLS = {
    "verified": "\u2713",       # checkmark
    "passage_verified": "~",    # passage found, context differs
    "hash_mismatch": "\u2717",  # X mark
    "passage_not_found": "?",
    "source_unavailable": "!",
    "insufficient_metadata": "-",
}

_STATUS_LABELS = {
    "verified": "VERIFIED",
    "passage_verified": "PASSAGE FOUND",
    "hash_mismatch": "HASH MISMATCH",
    "passage_not_found": "PASSAGE NOT FOUND",
    "source_unavailable": "SOURCE UNAVAILABLE",
    "insufficient_metadata": "INSUFFICIENT METADATA",
}


def format_result_text(result: VerificationResult) -> str:
    """Format a single verification result for terminal output."""
    symbol = _STATUS_SYMBOLS.get(result.status, "?")
    label = _STATUS_LABELS.get(result.status, result.status.upper())
    lines = []

    # Header
    lines.append(f"  [{symbol}] {result.citation_id}: {label}")
    lines.append(f"      Source: {result.source_title}")

    if result.page_ref:
        lines.append(f"      Location: {result.page_ref}")

    lines.append(f"      Relation: {result.relation} | "
                 f"Level: L{result.conformance_level} | "
                 f"Captured by: {result.captured_by}")

    # Internal hash
    lines.append(f"      Internal hash: {'valid' if result.internal_hash_valid else 'INVALID'}")

    # Source verification details
    if result.source_url:
        lines.append(f"      Source URL: {result.source_url}")

    if result.passage_match and result.passage_match.found:
        pm = result.passage_match
        lines.append(f"      Match type: {pm.match_type}"
                     + (f" ({pm.similarity:.0%})" if pm.match_type == "fuzzy" else ""))
        # Show a snippet of what was found
        snippet = pm.matched_text[:80]
        if len(pm.matched_text) > 80:
            snippet += "..."
        lines.append(f"      Found: \"{snippet}\"")

    if result.source_hash_valid is not None:
        lines.append(f"      Source hash: "
                     f"{'matches' if result.source_hash_valid else 'differs'}")

    if result.fetch_error:
        lines.append(f"      Fetch error: {result.fetch_error}")

    for warning in result.warnings:
        lines.append(f"      Warning: {warning}")

    return "\n".join(lines)


def format_summary(results: list[VerificationResult]) -> str:
    """Format a summary line for all results."""
    total = len(results)
    verified = sum(1 for r in results if r.status == "verified")
    passage_found = sum(1 for r in results if r.status == "passage_verified")
    failed = sum(1 for r in results if r.status == "hash_mismatch")
    not_found = sum(1 for r in results if r.status == "passage_not_found")
    unavailable = sum(1 for r in results if r.status == "source_unavailable")
    no_meta = sum(1 for r in results if r.status == "insufficient_metadata")

    parts = [f"{total} citations checked"]
    if verified:
        parts.append(f"{verified} fully verified")
    if passage_found:
        parts.append(f"{passage_found} passage confirmed")
    if failed:
        parts.append(f"{failed} hash mismatch")
    if not_found:
        parts.append(f"{not_found} passage not found")
    if unavailable:
        parts.append(f"{unavailable} source unavailable")
    if no_meta:
        parts.append(f"{no_meta} insufficient metadata")

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _log(msg: str):
    print(msg, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Verify VCITE citations against their original sources",
        epilog=(
            "Examples:\n"
            "  python tools/verify.py citation.json\n"
            "  python tools/verify.py citations.json --offline\n"
            "  python tools/verify.py enhanced.html --format json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        help="Input file: JSON (single citation or array) or enhanced HTML",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Offline mode: only check internal hash consistency, skip source fetch",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only print summary, not individual results",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite database path for storing results and tracking source drift",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        _log(f"File not found: {input_path}")
        sys.exit(1)

    # Load citations
    try:
        citations = load_citations(input_path)
    except Exception as e:
        _log(f"Error loading citations: {e}")
        sys.exit(1)

    if not citations:
        _log("No VCITE citations found in input file")
        sys.exit(1)

    _log(f"Loaded {len(citations)} citation(s) from {input_path.name}\n")

    # Verify each citation
    results: list[VerificationResult] = []
    for i, citation in enumerate(citations):
        _log(f"[{i + 1}/{len(citations)}] Verifying {citation.id}...")

        if args.offline:
            result = verify_citation_offline(citation)
        else:
            result = verify_citation(citation)

        results.append(result)

        if not args.quiet and args.format == "text":
            print(format_result_text(result))
            print()

    # Output
    if args.format == "json":
        json_output = json.dumps(
            [r.to_dict() for r in results],
            indent=2,
            ensure_ascii=False,
        )
        print(json_output)
    else:
        # Summary
        print("=" * 60)
        print(format_summary(results))

    # Store results in database if --db provided
    if args.db:
        from hashdb import HashDB
        with HashDB(args.db) as db:
            for result in results:
                db.store_result(result, input_file=str(input_path))
                source_text = getattr(result, "_source_text", None)
                if source_text and result.source_url:
                    is_drift, _ = db.record_source(result.source_url, source_text)
                    if is_drift:
                        _log(f"  Source drift detected: {result.source_url}")
            _log(f"\nStored {len(results)} result(s) in {args.db}")

    # Exit code: 0 if all verified/passage_verified, 1 otherwise
    all_ok = all(r.status in ("verified", "passage_verified") for r in results)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
