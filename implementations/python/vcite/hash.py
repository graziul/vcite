"""VCITE passage fingerprinting — reference implementation (spec §5.2).

This module implements the SHA-256 passage fingerprint algorithm defined
in the VCITE specification. The algorithm computes a deterministic hash
over a cited passage and its surrounding context, enabling cryptographic
verification that a citation matches its source.

The implementation follows spec §5.1 exactly:
  1. Normalize each segment (NFC + whitespace collapse)
  2. Pad/truncate context windows to exactly CONTEXT_LEN code points
  3. Concatenate with pipe delimiters
  4. SHA-256 over UTF-8 encoding
  5. Prepend "sha256:" prefix

Spec note: The whitespace regex covers U+0009 (tab), U+000A (LF),
U+000D (CR), U+0020 (space) only. Non-breaking space (U+00A0) and
other Unicode whitespace are intentionally NOT collapsed. The context
window counts Unicode code points, not UTF-8 bytes.
"""

import hashlib
import re
import unicodedata

CONTEXT_LEN = 50  # Unicode code points, not bytes


def normalize_segment(s: str) -> str:
    """NFC normalize and collapse ASCII whitespace.

    Per spec §5.1: apply Unicode NFC normalization, then collapse runs
    of tab/LF/CR/space to a single space, then strip leading/trailing
    whitespace from the segment.
    """
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"[\t\n\r ]+", " ", s)
    return s.strip()


def pad_context(s: str, length: int = CONTEXT_LEN) -> str:
    """Truncate or space-pad to exactly `length` Unicode code points.

    Per spec §5.1: context windows are fixed-length. Shorter strings
    are right-padded with U+0020 spaces. Longer strings are truncated.
    """
    chars = list(s)  # preserves multi-byte chars as single units
    if len(chars) >= length:
        return "".join(chars[:length])
    return "".join(chars) + " " * (length - len(chars))


def compute_hash(
    text_exact: str,
    text_before: str = "",
    text_after: str = "",
) -> str:
    """Compute the VCITE passage fingerprint for a cited passage.

    Args:
        text_exact: The verbatim cited passage.
        text_before: Up to 50 characters of context before the passage.
        text_after: Up to 50 characters of context after the passage.

    Returns:
        A string of the form "sha256:<64 hex chars>".
    """
    before = pad_context(normalize_segment(text_before))
    exact = normalize_segment(text_exact)
    after = pad_context(normalize_segment(text_after))
    raw = f"{before}|{exact}|{after}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
