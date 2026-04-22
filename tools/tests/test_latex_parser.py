"""Tests for the LaTeX citation extractor.

Covers the quote patterns, citation-hint extraction, command stripping,
escape handling, and the masked regions (verbatim, math, footnote,
comments) that should NOT yield quotes.
"""

import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).parent.parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

from parsers.latex_parser import (  # noqa: E402
    MIN_QUOTE_LEN,
    extract_quotes_latex,
    _strip_latex,
)


class TestQuoteEnvironment:
    """\\begin{quote}...\\end{quote} and friends."""

    def test_basic_quote_block(self):
        src = (
            r"Some intro text." "\n"
            r"\begin{quote}" "\n"
            r"This is a quoted passage that is definitely long enough." "\n"
            r"\end{quote}" "\n"
            r"Trailing prose." "\n"
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "quoted passage" in quotes[0].text_exact
        # Position must refer to the ORIGINAL source, inside the block
        inner_idx = src.index("This is a quoted")
        assert quotes[0].position == inner_idx or quotes[0].position == inner_idx - 1

    def test_quotation_block(self):
        src = (
            r"\begin{quotation}"
            r"A quotation environment with enough characters to qualify."
            r"\end{quotation}"
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "quotation environment" in quotes[0].text_exact

    def test_displayquote_block(self):
        src = (
            r"\begin{displayquote}"
            r"A displayquote environment with enough characters to qualify."
            r"\end{displayquote}"
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "displayquote environment" in quotes[0].text_exact


class TestEnquote:
    def test_simple_enquote(self):
        src = r"Prose before \enquote{this is the quoted content inline} and after."
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert quotes[0].text_exact == "this is the quoted content inline"

    def test_enquote_with_inner_braces(self):
        src = r"\enquote{a passage with {nested} braces that is long enough here}"
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "nested" in quotes[0].text_exact


class TestTexStyleQuotes:
    def test_double_quote(self):
        src = r"He said ``this is a verbatim passage to be extracted'' in reply."
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert quotes[0].text_exact == "this is a verbatim passage to be extracted"

    def test_single_quote(self):
        src = r"She wrote `this is a single-quoted passage to extract' nearby."
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "single-quoted passage" in quotes[0].text_exact

    def test_single_quote_does_not_match_apostrophe(self):
        """`author's` in regular prose must not become a quote."""
        src = r"The author's opinion on this matter is well known."
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 0

    def test_textquote_macros(self):
        src = (
            r"Begin \textquotedblleft a macro-delimited double quoted "
            r"passage that is long enough\textquotedblright end."
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "macro-delimited" in quotes[0].text_exact


class TestCommandStripping:
    def test_emph_stripped(self):
        src = (
            r"\begin{quote}"
            r"a passage with \emph{italic} and plain words in the middle"
            r"\end{quote}"
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "italic" in quotes[0].text_exact
        assert "\\emph" not in quotes[0].text_exact

    def test_textit_textbf_stripped(self):
        src = (
            r"\begin{quote}"
            r"this has \textit{italic text} and \textbf{bold text} inline here"
            r"\end{quote}"
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "italic text" in quotes[0].text_exact
        assert "bold text" in quotes[0].text_exact
        assert "\\textit" not in quotes[0].text_exact
        assert "\\textbf" not in quotes[0].text_exact

    def test_cite_removed_from_quote(self):
        src = (
            r"\begin{quote}"
            r"a quoted passage with a citation \citep{smith2020} embedded here"
            r"\end{quote}"
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "smith2020" not in quotes[0].text_exact
        assert "\\citep" not in quotes[0].text_exact

    def test_ref_and_label_removed(self):
        src = (
            r"\begin{quote}"
            r"as shown in \ref{fig:main} and labeled \label{quote:a} right here"
            r"\end{quote}"
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "fig:main" not in quotes[0].text_exact
        assert "quote:a" not in quotes[0].text_exact

    def test_footnote_removed_inside_quote(self):
        src = (
            r"\begin{quote}"
            r"a quote with \footnote{a footnote note here} text after"
            r"\end{quote}"
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "footnote note" not in quotes[0].text_exact


class TestEscapeHandling:
    def test_escapes_in_strip(self):
        raw = r"five \% of users and A \& B and a price of \$10"
        out = _strip_latex(raw)
        assert "5" not in out or "%" in out  # at least % unescaped
        assert "%" in out
        assert "&" in out
        assert "$" in out
        assert r"\%" not in out
        assert r"\&" not in out

    def test_underscores_and_hashes(self):
        raw = r"a variable called x\_y and a tag \#foo"
        out = _strip_latex(raw)
        assert "x_y" in out
        assert "#foo" in out

    def test_braces(self):
        raw = r"literal \{ and \} braces in text"
        out = _strip_latex(raw)
        assert "{" in out and "}" in out

    def test_dashes_and_tilde(self):
        raw = r"range 1--5 and em---dash and nbsp~here"
        out = _strip_latex(raw)
        assert "–" in out  # en dash
        assert "—" in out  # em dash
        # ~ becomes a space
        assert "~" not in out

    def test_backslash_newline(self):
        raw = r"line one\\line two"
        out = _strip_latex(raw)
        assert "\n" in out


class TestCitationHint:
    def test_cite_hint_after_quote(self):
        src = (
            r"\begin{quote}"
            r"a passage that sits before a cite call to follow"
            r"\end{quote}"
            r" \cite{smith2020example}."
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "smith2020example" in quotes[0].citation_hint

    def test_citet_hint(self):
        src = (
            r"As \citet{jones2021} shows, "
            r"\enquote{a passage with sufficient length here to extract}"
            r"."
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "jones2021" in quotes[0].citation_hint

    def test_citep_multi_key(self):
        src = (
            r"\begin{quote}"
            r"a multi-key cited passage, long enough to pass the gate"
            r"\end{quote}"
            r" \citep{a2020, b2021, c2022}."
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        hint = quotes[0].citation_hint
        assert "a2020" in hint and "b2021" in hint and "c2022" in hint

    def test_inline_paren_hint(self):
        src = (
            r"In prior work (Smith, 2020) shows "
            r"``the passage that we want to extract is here'' in context."
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "Smith" in quotes[0].citation_hint
        assert "2020" in quotes[0].citation_hint


class TestSkippedRegions:
    def test_verbatim_skipped(self):
        src = (
            r"\begin{verbatim}"
            "\n"
            r"``this fake quote is inside verbatim and must not match''"
            "\n"
            r"\end{verbatim}"
        )
        quotes = extract_quotes_latex(src)
        assert quotes == []

    def test_lstlisting_skipped(self):
        src = (
            r"\begin{lstlisting}"
            "\n"
            r"\begin{quote}a bogus quote inside a code listing sample\end{quote}"
            "\n"
            r"\end{lstlisting}"
        )
        quotes = extract_quotes_latex(src)
        assert quotes == []

    def test_math_display_skipped(self):
        src = r"\[ ``a fake quote inside displaymath and long enough to trip'' \]"
        quotes = extract_quotes_latex(src)
        assert quotes == []

    def test_equation_env_skipped(self):
        src = (
            r"\begin{equation}"
            r"``a fake quote in an equation with more than enough length''"
            r"\end{equation}"
        )
        quotes = extract_quotes_latex(src)
        assert quotes == []

    def test_dollardollar_math_skipped(self):
        src = r"$$ ``fake quote inside display math dollar-dollar that is long'' $$"
        quotes = extract_quotes_latex(src)
        assert quotes == []

    def test_footnote_contents_skipped(self):
        src = (
            r"Outside is fine. "
            r"\footnote{``a quote-looking passage inside a footnote, skipped''}"
            r" and more prose here."
        )
        quotes = extract_quotes_latex(src)
        assert quotes == []


class TestComments:
    def test_comment_line_skipped(self):
        src = (
            r"% ``a quote inside a comment line that must be skipped''" "\n"
            r"\begin{quote}real quoted content here that is long enough\end{quote}"
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        assert "real quoted content" in quotes[0].text_exact

    def test_escaped_percent_preserved(self):
        """\\% is prose, NOT a comment start."""
        src = (
            r"\begin{quote}"
            r"about five \% of subjects showed a clear long-form response"
            r"\end{quote}"
        )
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        # After stripping, \% becomes %
        assert "%" in quotes[0].text_exact


class TestMinLength:
    def test_short_quote_rejected(self):
        # Shorter than MIN_QUOTE_LEN after stripping
        src = r"\begin{quote}too short\end{quote}"
        quotes = extract_quotes_latex(src)
        assert quotes == []

    def test_min_length_boundary(self):
        # Exactly MIN_QUOTE_LEN characters in the stripped text
        content = "x" * MIN_QUOTE_LEN
        src = r"\begin{quote}" + content + r"\end{quote}"
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1


class TestIntegration:
    def test_full_paragraph(self):
        """Short paragraph: 2 block quotes, 1 TeX double-quote, 2 cites,
        one inline (Author, Year), one footnoted fake quote (skipped),
        one math block with fake quote (skipped).
        """
        src = r"""
As \citet{zittrain2014} documented,
\begin{quote}
over seventy percent of the URLs in the Harvard Law Review did not lead
to originally cited information
\end{quote}
which raises questions about the archive.

Recent work observes that \enquote{AI search tools are unreliable for
sourcing and verification work} \citep{lim2025}, echoing earlier critiques.

A pointed view argues ``the scholarly record is fraying at the edges
because citations point to missing documents'' (Smith, 2023).

An aside\footnote{``a fake quote inside a footnote''} passes through.

\begin{equation}
``a fake quote inside equation, long enough to pass the gate'' = 0
\end{equation}
"""
        quotes = extract_quotes_latex(src)
        # Expect: 1 quote block + 1 enquote + 1 TeX double-quote = 3
        assert len(quotes) == 3, f"got {len(quotes)} quotes: {[q.text_exact for q in quotes]}"

        texts = [q.text_exact for q in quotes]
        assert any("seventy percent" in t for t in texts)
        assert any("AI search tools" in t for t in texts)
        assert any("scholarly record" in t for t in texts)

        # Quotes are sorted by position in source
        positions = [q.position for q in quotes]
        assert positions == sorted(positions)

        # Citation hints landed on the right quotes
        for q in quotes:
            if "seventy percent" in q.text_exact:
                assert "zittrain2014" in q.citation_hint
            elif "AI search tools" in q.text_exact:
                assert "lim2025" in q.citation_hint
            elif "scholarly record" in q.text_exact:
                assert "Smith" in q.citation_hint and "2023" in q.citation_hint

    def test_position_in_original_source(self):
        """The position must index into the UNMODIFIED input string."""
        src = r"""Intro. \begin{quote}a passage with enough characters to qualify here\end{quote}."""
        quotes = extract_quotes_latex(src)
        assert len(quotes) == 1
        pos = quotes[0].position
        # The original source at that position starts near the passage text
        # (after possible leading whitespace inside the begin{quote})
        surrounding = src[pos:pos + 40]
        assert "passage with enough" in surrounding


class TestEnhanceCliIntegration:
    """End-to-end: run enhance.py on examples/citation-article.tex."""

    def test_enhance_latex_example(self, tmp_path):
        example = REPO_ROOT / "examples" / "citation-article.tex"
        if not example.exists():
            import pytest
            pytest.skip("citation-article.tex not available")

        out = tmp_path / "out.vcite.tex"
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "enhance.py"),
                str(example),
                "--no-metadata",
                "-o",
                str(out),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"enhance.py failed: {result.stderr}"
        content = out.read_text()
        # Original body is preserved
        assert r"\begin{document}" in content
        # VCITE metadata block is appended
        assert "VCITE metadata" in content
        # Three citations expected (matches the integration test fixture)
        import json
        # Extract the commented JSON
        lines = []
        in_block = False
        for line in content.splitlines():
            if "VCITE metadata (auto-generated)" in line:
                in_block = True
                continue
            if "end VCITE metadata" in line:
                break
            if in_block and line.startswith("% "):
                lines.append(line[2:])
        data = json.loads("\n".join(lines))
        assert isinstance(data, list)
        assert len(data) == 3
