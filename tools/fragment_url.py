"""W3C Text Fragment URL construction for VCITE citations.

Generates URLs conforming to the WICG Text Fragments specification:
    https://wicg.github.io/scroll-to-text-fragment/

Grammar (after the ``#:~:`` delimiter):
    text=[prefix-,]textStart[,textEnd][,-suffix]

This module only generates fragment URLs heuristically; it never fetches
the source to verify that the fragment resolves. Callers should treat the
output as a best-effort deep link.

Public API:
    build_text_fragment_url(source_url, text_exact, text_before="", text_after="")
    strip_fragment(url) -> url with any ``:~:text=...`` suffix removed

Stdlib only.
"""

from __future__ import annotations

import re
from urllib.parse import quote as _percent_quote

# A minimal stopword list used only to decide whether a passage is "too
# generic" to deserve a fragment URL. We do NOT strip stopwords from the
# generated fragment itself — the browser matches the literal text.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
        "from", "had", "has", "have", "he", "her", "his", "i", "if", "in",
        "into", "is", "it", "its", "of", "on", "or", "our", "s", "she",
        "so", "that", "the", "their", "them", "then", "there", "these",
        "they", "this", "to", "was", "we", "were", "will", "with", "you",
        "your",
    }
)

# Words count for the heuristic split between "short" (use whole passage
# as textStart) and "long" (use textStart,textEnd).
_SHORT_PASSAGE_WORD_LIMIT = 6
# Number of words to take from each end for the textStart / textEnd pair.
_HEAD_TAIL_WORDS = 3
# Number of words to pull from text_before / text_after for prefix/suffix.
_CONTEXT_WORDS = 3
# Minimum meaningful (non-stopword) word count required to generate a URL.
_MIN_MEANINGFUL_WORDS = 3


def _split_words(text: str) -> list[str]:
    """Split on whitespace, preserving punctuation attached to words.

    We intentionally keep punctuation because text fragment matching is
    literal: stripping a trailing period would make the fragment fail to
    match when the browser looks for the passage.
    """
    return [w for w in re.split(r"\s+", text.strip()) if w]


def _meaningful_word_count(text: str) -> int:
    """Count words that are not stopwords after lowercasing and stripping
    surrounding punctuation. Used as a generic-content heuristic."""
    count = 0
    for word in _split_words(text):
        stripped = re.sub(r"^\W+|\W+$", "", word).lower()
        if stripped and stripped not in _STOPWORDS:
            count += 1
    return count


def _encode_fragment_part(text: str) -> str:
    """Percent-encode a single textStart/textEnd/prefix/suffix part.

    Per the Text Fragment spec, these separators are reserved and MUST be
    percent-encoded in the payload:
        ``,``  (part separator)
        ``&``  (directive separator)
        ``-``  (prefix/suffix marker)

    We also percent-encode any character that is not unreserved per RFC
    3986, which keeps the URL safe in the widest range of contexts. The
    browser performs case-insensitive, whitespace-tolerant matching, so
    spaces are encoded as ``%20`` rather than ``+`` to avoid ambiguity.
    """
    # urllib.parse.quote with safe='' percent-encodes everything except
    # unreserved characters. Then explicitly encode the three reserved
    # fragment characters (they happen to already be encoded by quote,
    # but we keep the comment for clarity).
    return _percent_quote(text, safe="")


def build_text_fragment_url(
    source_url: str,
    text_exact: str,
    text_before: str = "",
    text_after: str = "",
) -> str | None:
    """Build a W3C Text Fragment URL for the given passage.

    Returns ``None`` when:
      * ``source_url`` is falsy or not http(s);
      * the passage is too short or generic (fewer than 3 non-stopword
        meaningful words after trimming);
      * the passage text is empty after whitespace collapse.

    Otherwise returns ``{source_url_canonical}#:~:text=...``.
    """
    if not source_url or not isinstance(source_url, str):
        return None
    lowered = source_url.strip().lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        return None
    if not text_exact or not text_exact.strip():
        return None
    if _meaningful_word_count(text_exact) < _MIN_MEANINGFUL_WORDS:
        return None

    # Canonicalize base URL: strip any pre-existing ``:~:text=`` directive
    # but preserve any regular ``#anchor``.
    base = strip_fragment(source_url)

    words = _split_words(text_exact)
    if len(words) <= _SHORT_PASSAGE_WORD_LIMIT:
        # Short passage: use the whole thing as textStart.
        text_start = " ".join(words)
        text_end: str | None = None
    else:
        # Long passage: textStart is the first N words, textEnd is the
        # last N words. This yields a compact URL that is tolerant of
        # minor whitespace differences and matches the browser's
        # range-match behavior.
        text_start = " ".join(words[:_HEAD_TAIL_WORDS])
        text_end = " ".join(words[-_HEAD_TAIL_WORDS:])

    # Optional disambiguation via prefix/suffix context.
    prefix: str | None = None
    if text_before:
        ctx_words = _split_words(text_before)
        if ctx_words:
            prefix = " ".join(ctx_words[-_CONTEXT_WORDS:])

    suffix: str | None = None
    if text_after:
        ctx_words = _split_words(text_after)
        if ctx_words:
            suffix = " ".join(ctx_words[:_CONTEXT_WORDS])

    parts: list[str] = []
    if prefix:
        parts.append(f"{_encode_fragment_part(prefix)}-")
    parts.append(_encode_fragment_part(text_start))
    if text_end:
        parts.append(_encode_fragment_part(text_end))
    if suffix:
        parts.append(f"-{_encode_fragment_part(suffix)}")

    directive = "text=" + ",".join(parts)

    # Delimiter placement: the spec says ``:~:`` introduces the fragment
    # directive and MAY follow an existing anchor. We therefore always
    # append ``#:~:`` when there is no existing anchor, and ``:~:`` when
    # there is one.
    if "#" in base:
        return f"{base}:~:{directive}"
    return f"{base}#:~:{directive}"


def strip_fragment(url: str) -> str:
    """Remove any ``:~:text=...`` (or other fragment directive) from ``url``.

    Preserves an existing plain ``#anchor`` when present:
      * ``https://x/y#sec-2:~:text=foo`` -> ``https://x/y#sec-2``
      * ``https://x/y#:~:text=foo``      -> ``https://x/y``
      * ``https://x/y#sec-2``            -> ``https://x/y#sec-2`` (unchanged)
      * ``https://x/y``                  -> ``https://x/y`` (unchanged)
    """
    if not url or ":~:" not in url:
        return url
    head, _, _ = url.partition(":~:")
    # ``head`` ends with ``#`` for bare-fragment URLs and with
    # ``#anchor`` for anchored ones. Drop a trailing ``#`` so a bare
    # fragment produces the clean canonical URL.
    if head.endswith("#"):
        return head[:-1]
    return head
