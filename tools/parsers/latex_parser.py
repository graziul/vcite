"""Extract quoted passages and citations from LaTeX articles.

This extractor is a single-pass scanner plus a handful of regex passes.
It is NOT a full LaTeX parser: macros outside the explicit handling list
below pass through to ``text_exact``, which is acceptable for a first
round of extraction. Downstream hashing/matching can be tightened by
expanding the strip list as real-world patterns surface.

Handled quote patterns:
  * ``\\begin{quote}...\\end{quote}``
  * ``\\begin{quotation}...\\end{quotation}``
  * ``\\begin{displayquote}...\\end{displayquote}``
  * ``\\enquote{...}`` (csquotes package)
  * TeX double quotes: `` ``...'' ``
  * TeX single quotes: `` `...' ``
  * ``\\textquoteleft...\\textquoteright`` /
    ``\\textquotedblleft...\\textquotedblright``

Handled citation hints: ``\\cite{...}`` and the natbib/biblatex family
(``\\citet``, ``\\citep``, ``\\citeauthor``, ``\\citeyear``, ``\\parencite``,
``\\textcite``, ``\\citealt``, ``\\citeauthor*`` etc.). Inline
``(Author, Year)`` parenthetical hints are also matched via the same
regex as the HTML parser.

Positions reported in :class:`ExtractedQuote` refer to character offsets
in the ORIGINAL LaTeX source, not in a stripped intermediate.

Skipped regions (no quote extraction inside):
  * ``%`` comments (to end of line; ``\\%`` is preserved)
  * ``verbatim`` / ``lstlisting`` environments
  * math: ``\\[...\\]``, ``$$...$$``,
    ``\\begin{equation}...\\end{equation}``,
    ``\\begin{align}...\\end{align}``
  * ``\\footnote{...}`` calls (the whole call, with braces, is removed)
"""

from __future__ import annotations

import re

from .html_parser import (
    ExtractedQuote,
    MIN_QUOTE_LEN,
    _AUTHOR_YEAR_RE,
    _NAME_CHAR,  # noqa: F401 -- re-exported for downstream callers
)

__all__ = ["extract_quotes_latex", "ExtractedQuote"]


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Environments whose contents should be masked out (no extraction inside).
_SKIP_ENVS = ("verbatim", "lstlisting", "equation", "equation*",
              "align", "align*", "displaymath")

# Quote environments. Dotall so they can span lines.
_QUOTE_ENV_RE = re.compile(
    r"\\begin\{(quote|quotation|displayquote)\}(.*?)\\end\{\1\}",
    re.DOTALL,
)

# \enquote{...} -- content with balanced braces handled separately; the
# regex here only finds the opening; closing is located with a scanner.
_ENQUOTE_START_RE = re.compile(r"\\enquote\{")

# TeX double-quote: ``...''  (two backticks, two straight apostrophes).
# Restrict to non-greedy content without an embedded ``.
_TEX_DOUBLE_QUOTE_RE = re.compile(r"``(.+?)''", re.DOTALL)

# TeX single-quote: `...'   (one backtick, one apostrophe). To avoid
# matching apostrophes in normal prose (e.g. "author's"), require the
# opening backtick to be preceded by start-of-string, whitespace, or an
# opening punctuation character.
_TEX_SINGLE_QUOTE_RE = re.compile(
    r"(?:^|(?<=[\s(\[{]))`([^`'\n][^`'\n]{%d,}?)'" % (MIN_QUOTE_LEN - 1)
)

# \textquoteleft / \textquoteright (single) and dbl variants.
_TEXTQUOTE_DBL_RE = re.compile(
    r"\\textquotedblleft\s*(.*?)\\textquotedblright", re.DOTALL
)
_TEXTQUOTE_SGL_RE = re.compile(
    r"\\textquoteleft\s*(.*?)\\textquoteright", re.DOTALL
)

# Citation macros (natbib + biblatex family). The inner key list may be
# separated by commas; we capture the whole call as the hint.
_CITE_COMMANDS = (
    "cite", "citet", "citep", "citeauthor", "citeyear", "citealt",
    "citealp", "parencite", "textcite", "autocite", "footcite",
    "citet*", "citep*", "citeauthor*", "citeyearpar",
)
# Build an alternation; escape * for regex, and match optional [..][..] args.
_cite_alt = "|".join(re.escape(c) for c in _CITE_COMMANDS)
_CITE_RE = re.compile(
    r"\\(" + _cite_alt + r")"
    r"(?:\[[^\]]*\])?"      # optional first optional arg
    r"(?:\[[^\]]*\])?"      # optional second optional arg
    r"\{([^}]*)\}"          # mandatory key list
)

# Math environments (display math block starts/ends).
_MATH_BLOCK_RES = (
    re.compile(r"\\\[(.*?)\\\]", re.DOTALL),
    re.compile(r"\$\$(.*?)\$\$", re.DOTALL),
    re.compile(r"\\begin\{(equation\*?|align\*?|displaymath)\}(.*?)"
               r"\\end\{\1\}", re.DOTALL),
)


# ---------------------------------------------------------------------------
# LaTeX-to-text stripping
# ---------------------------------------------------------------------------

# Commands whose single braced argument should be unwrapped (keep content).
_UNWRAP_COMMANDS = (
    "emph", "textit", "textbf", "textsf", "texttt", "textrm", "textsc",
    "underline", "uline", "mbox", "hbox",
)

# Commands whose WHOLE call (including braced args) should be deleted.
# The argument count matters — we handle simple single-arg cases via a
# balanced-brace scanner.
_DELETE_COMMANDS_1ARG = (
    "label", "ref", "eqref", "pageref", "autoref", "cref",
    "footnote", "footnotetext", "marginpar",
    "index", "glossary", "nocite",
)

# All cite commands are also deleted (cite keys are extracted separately).
_DELETE_COMMANDS_1ARG = _DELETE_COMMANDS_1ARG + _CITE_COMMANDS


def _find_matching_brace(s: str, open_pos: int) -> int:
    """Return the index of the matching ``}`` for a ``{`` at ``open_pos``.

    Respects backslash-escaped ``\\{`` and ``\\}``. Returns ``-1`` if no
    match is found before end-of-string.
    """
    if open_pos >= len(s) or s[open_pos] != "{":
        return -1
    depth = 1
    i = open_pos + 1
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            # Skip the escaped next character (covers \{, \}, \\, etc.)
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _delete_call(text: str, cmd: str) -> str:
    """Delete every ``\\cmd[opt]{arg}`` call from ``text``.

    Uses a scanner that respects balanced braces so ``\\footnote{a {b} c}``
    is removed whole. Optional ``[...]`` arguments after the command name
    are also consumed.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    needle = "\\" + cmd
    nlen = len(needle)
    while i < n:
        if text.startswith(needle, i):
            # Must be followed by a non-letter (so \citet doesn't match \cite).
            after = i + nlen
            if after < n and text[after].isalpha():
                out.append(text[i])
                i += 1
                continue
            # Skip a star suffix if the command name already includes one.
            # Skip optional [...] args.
            j = after
            while j < n and text[j] == "[":
                close = text.find("]", j)
                if close == -1:
                    break
                j = close + 1
            # Skip the mandatory {...} arg if present.
            if j < n and text[j] == "{":
                close = _find_matching_brace(text, j)
                if close == -1:
                    out.append(text[i])
                    i += 1
                    continue
                i = close + 1
            else:
                # No arg — just drop the command name (rare but possible).
                i = j
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _unwrap_call(text: str, cmd: str) -> str:
    """Replace every ``\\cmd{X}`` call with ``X`` (keeping content)."""
    out: list[str] = []
    i = 0
    n = len(text)
    needle = "\\" + cmd
    nlen = len(needle)
    while i < n:
        if text.startswith(needle, i):
            after = i + nlen
            if after < n and text[after].isalpha():
                out.append(text[i])
                i += 1
                continue
            j = after
            if j < n and text[j] == "{":
                close = _find_matching_brace(text, j)
                if close == -1:
                    out.append(text[i])
                    i += 1
                    continue
                inner = text[j + 1:close]
                # Recursively strip inner commands of the same family
                # handled at the caller; here we just inline the content.
                out.append(inner)
                i = close + 1
                continue
            # No brace arg; leave the raw command.
            out.append(text[i])
            i += 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


# Escape-char substitutions applied after command stripping.
_ESCAPE_SUBS = [
    (re.compile(r"\\%"), "%"),
    (re.compile(r"\\&"), "&"),
    (re.compile(r"\\\$"), "$"),
    (re.compile(r"\\_"), "_"),
    (re.compile(r"\\#"), "#"),
    (re.compile(r"\\\{"), "{"),
    (re.compile(r"\\\}"), "}"),
    (re.compile(r"\\\^\{\}"), "^"),
    (re.compile(r"\\~\{\}"), "~"),
]


def _strip_latex(text: str) -> str:
    """Convert a LaTeX fragment to plain prose.

    Applied inside quoted passages and on the text windows used for
    text_before / text_after. The transformation is deliberately
    conservative: unknown macros pass through rather than being
    over-aggressively stripped.
    """
    # Delete whole calls (footnote, cite, label, ...)
    for cmd in _DELETE_COMMANDS_1ARG:
        if "\\" + cmd in text:
            text = _delete_call(text, cmd)
    # Unwrap formatting (emph, textbf, ...)
    # Multiple passes: nested emph{textbf{x}} needs two passes.
    for _ in range(3):
        before = text
        for cmd in _UNWRAP_COMMANDS:
            if "\\" + cmd in text:
                text = _unwrap_call(text, cmd)
        if text == before:
            break

    # Typographic shorthands.
    text = text.replace("---", "—")  # em dash
    text = text.replace("--", "–")   # en dash
    text = text.replace("~", " ")    # non-breaking space
    text = re.sub(r"\\\\(?:\[[^\]]*\])?", "\n", text)  # line break

    # Escaped characters.
    for pat, repl in _ESCAPE_SUBS:
        text = pat.sub(repl, text)

    # Collapse runs of whitespace (but keep newlines distinct so the
    # paragraph_context is readable).
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Masking: build a "safe" version where skipped regions are replaced with
# spaces of equal length so character positions in the masked string
# still map directly to positions in the original source.
# ---------------------------------------------------------------------------

def _mask_regions(src: str) -> str:
    """Return ``src`` with skipped regions replaced by spaces.

    Preserves newlines (so line-based scanning still works) and keeps
    string length identical so offsets line up with the original.
    """
    masked = list(src)
    n = len(src)

    def _blank(start: int, end: int) -> None:
        end = min(end, n)
        for i in range(start, end):
            if masked[i] != "\n":
                masked[i] = " "

    # Comments: from unescaped % to end of line.
    i = 0
    while i < n:
        ch = src[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "%":
            j = src.find("\n", i)
            if j == -1:
                j = n
            _blank(i, j)
            i = j
            continue
        i += 1

    # Verbatim-style environments.
    for env in ("verbatim", "lstlisting"):
        pat = re.compile(
            r"\\begin\{" + env + r"\}(.*?)\\end\{" + env + r"\}", re.DOTALL
        )
        for m in pat.finditer(src):
            _blank(m.start(), m.end())

    # Math blocks.
    for pat in _MATH_BLOCK_RES:
        for m in pat.finditer(src):
            _blank(m.start(), m.end())

    # \footnote{...} calls — mask so we do not extract quotes inside them,
    # and so citation-hint searches do not find cites placed in footnotes
    # attached to the wrong sentence.
    needle = "\\footnote"
    i = 0
    while True:
        j = src.find(needle, i)
        if j == -1:
            break
        after = j + len(needle)
        # Must be followed by non-letter so \footnotemark etc. are separate.
        if after < n and src[after].isalpha():
            i = after
            continue
        k = after
        while k < n and src[k] == "[":
            close = src.find("]", k)
            if close == -1:
                break
            k = close + 1
        if k < n and src[k] == "{":
            close = _find_matching_brace(src, k)
            if close != -1:
                _blank(j, close + 1)
                i = close + 1
                continue
        i = after

    return "".join(masked)


# ---------------------------------------------------------------------------
# Citation-hint extraction
# ---------------------------------------------------------------------------

def _find_latex_citation_hint(
    masked: str, quote_start: int, quote_end: int
) -> str:
    """Look for a citation macro or parenthetical hint near a quote.

    Picks the CLOSEST citation in either direction so that an
    introducing ``\\citet{...}`` before the quote is not shadowed by an
    unrelated citation attached to a later sentence. Returns the raw
    ``\\cite{...}`` call text (which metadata resolution can look up in
    a .bib file) or the inner text of a parenthetical ``(Author, Year)``
    match.
    """
    after = masked[quote_end:quote_end + 300]
    before_start = max(0, quote_start - 200)
    before = masked[before_start:quote_start]

    candidates: list[tuple[int, str]] = []

    m = _CITE_RE.search(after)
    if m:
        candidates.append((m.start(), m.group(0)))
    m_before_all = list(_CITE_RE.finditer(before))
    if m_before_all:
        # Closest to the quote = last match in the "before" window.
        last = m_before_all[-1]
        dist = len(before) - last.end()
        candidates.append((dist, last.group(0)))

    # Parenthetical (Author, Year) fallbacks.
    am = _AUTHOR_YEAR_RE.search(after)
    if am:
        candidates.append((am.start(), am.group(1)))
    bm_all = list(_AUTHOR_YEAR_RE.finditer(before))
    if bm_all:
        last = bm_all[-1]
        dist = len(before) - last.end()
        candidates.append((dist, last.group(1)))

    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Window / paragraph context
# ---------------------------------------------------------------------------

def _context_window(src: str, start: int, end: int, window: int = 50) -> tuple[str, str]:
    """Return ``(before, after)`` plain-text windows of ~``window`` chars.

    LaTeX stripping is applied inside the window so the resulting text
    is clean prose. Because stripping can shrink the string, we pull a
    larger raw slice and then trim the stripped result down to
    ``window`` characters.
    """
    raw_before = src[max(0, start - window * 3):start]
    raw_after = src[end:end + window * 3]
    b = _strip_latex(raw_before)
    a = _strip_latex(raw_after)
    if len(b) > window:
        b = b[-window:]
    if len(a) > window:
        a = a[:window]
    return b, a


def _find_paragraph_context(src: str, position: int) -> str:
    """Return the paragraph (double-newline bounded) containing ``position``."""
    start = src.rfind("\n\n", 0, position)
    start = 0 if start == -1 else start + 2
    end = src.find("\n\n", position)
    if end == -1:
        end = len(src)
    return _strip_latex(src[start:end])


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_quotes_latex(content: str) -> list[ExtractedQuote]:
    """Extract cited passages from a LaTeX source string.

    Positions in the returned :class:`ExtractedQuote` objects refer to
    character offsets in the ORIGINAL ``content``, even though quote
    contents are stripped of LaTeX markup.
    """
    masked = _mask_regions(content)
    quotes: list[ExtractedQuote] = []
    seen: set[tuple[str, int]] = set()

    def _add(
        raw_text: str,
        raw_start: int,
        raw_end: int,
        match_start: int,
        match_end: int,
    ) -> None:
        stripped = _strip_latex(raw_text)
        if len(stripped) < MIN_QUOTE_LEN:
            return
        key = (stripped, raw_start)
        if key in seen:
            return
        seen.add(key)
        before, after = _context_window(content, match_start, match_end)
        hint = _find_latex_citation_hint(masked, match_start, match_end)
        paragraph = _find_paragraph_context(content, raw_start)
        quotes.append(
            ExtractedQuote(
                text_exact=stripped,
                text_before=before,
                text_after=after,
                citation_hint=hint,
                paragraph_context=paragraph,
                position=raw_start,
            )
        )

    # --- quote/quotation/displayquote environments ---
    for m in _QUOTE_ENV_RE.finditer(masked):
        inner_start = m.start(2)
        inner_end = m.end(2)
        raw_inner = content[inner_start:inner_end]
        _add(raw_inner, inner_start, inner_end, m.start(), m.end())

    # --- \enquote{...} (balanced braces) ---
    for m in _ENQUOTE_START_RE.finditer(masked):
        brace_open = m.end() - 1  # position of the '{'
        brace_close = _find_matching_brace(content, brace_open)
        if brace_close == -1:
            continue
        inner_start = brace_open + 1
        inner_end = brace_close
        raw_inner = content[inner_start:inner_end]
        _add(raw_inner, inner_start, inner_end, m.start(), brace_close + 1)

    # --- TeX-style double quotes ``...'' ---
    for m in _TEX_DOUBLE_QUOTE_RE.finditer(masked):
        inner_start = m.start(1)
        inner_end = m.end(1)
        raw_inner = content[inner_start:inner_end]
        _add(raw_inner, inner_start, inner_end, m.start(), m.end())

    # --- TeX-style single quotes `...' ---
    for m in _TEX_SINGLE_QUOTE_RE.finditer(masked):
        inner_start = m.start(1)
        inner_end = m.end(1)
        raw_inner = content[inner_start:inner_end]
        _add(raw_inner, inner_start, inner_end, m.start(), m.end())

    # --- \textquoteleft/right and dbl ---
    for pat in (_TEXTQUOTE_DBL_RE, _TEXTQUOTE_SGL_RE):
        for m in pat.finditer(masked):
            inner_start = m.start(1)
            inner_end = m.end(1)
            raw_inner = content[inner_start:inner_end]
            _add(raw_inner, inner_start, inner_end, m.start(), m.end())

    quotes.sort(key=lambda q: q.position)
    return quotes
