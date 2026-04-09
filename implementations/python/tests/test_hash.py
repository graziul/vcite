"""Tests for the VCITE passage fingerprinting algorithm (spec §5).

Validates the reference implementation against 23 test vectors:
- 4 mandatory spec vectors (§5.3)
- 3 appendix A examples
- 16 edge case vectors covering Unicode, whitespace, context padding,
  empty inputs, delimiter handling, and NFC normalization
"""

from pathlib import Path

import pytest
import yaml

from vcite.hash import compute_hash, normalize_segment, pad_context

VECTORS_PATH = Path(__file__).parent.parent.parent.parent / "test-suite" / "vectors.yaml"


@pytest.fixture(scope="module")
def vectors():
    """Load all test vectors from YAML."""
    with open(VECTORS_PATH) as f:
        return yaml.safe_load(f)


# -- Spec §5.3 Mandatory Vectors --


class TestSpecVectors:
    """These 4 vectors MUST be reproduced exactly by any conforming implementation."""

    def test_sv1_basic_ascii(self):
        assert compute_hash("exactly 42%", "The rate is ", " as measured") == \
            "sha256:f2d30080cf6f2dd31c4e160673b427742c132bd7fe6b014e0b5026daea80bbf5"

    def test_sv2_unicode_nfc(self):
        assert compute_hash("r\u00e9sum\u00e9 complet", "caf\u00e9 au lait ", " du rapport") == \
            "sha256:c9ac6f27318e7f3a7d27b85a9823ac7644e6a02d2f58c2abd1801ae99a9a53e4"

    def test_sv3_whitespace_collapse(self):
        assert compute_hash("  spaces  here  ", "  multiple   ", "  trimmed  ") == \
            "sha256:ad4c8f44cc63c1d34451eab399094657961632d044a29c9c852d2bac064f3948"

    def test_sv4_no_context(self):
        assert compute_hash("Only exact, no context", "", "") == \
            "sha256:d8ea2d1c308a3d38328362479c1a97dbdf5a9a87ca64a6a4b3fdd430853edd8b"


# -- Appendix A Examples --


class TestAppendixExamples:
    """Hashes for the three example VCITE objects in Appendix A."""

    def test_a1_academic_zittrain(self):
        text_exact = (
            "over 70% of the URLs provided in articles published in "
            "the Harvard Law Review did not lead to originally cited information"
        )
        assert compute_hash(text_exact, "As documented by Zittrain et al., ",
                            ". This rate of decay accelerates") == \
            "sha256:d2ba5887d4456199ce37a7860ce011485519925dc75c3564f50d1ffa1e1dc933"

    def test_a2_journalism_cjr(self):
        text_exact = (
            "eight major AI search tools provided incorrect or inaccurate "
            "answers to more than 60% of 1,600 test queries"
        )
        assert compute_hash(text_exact, "The CJR found that ",
                            ", with error rates ranging") == \
            "sha256:26c71181069e54c4d776f2a03de838c81aab3eff1a64a71ecde920f629367707"

    def test_a3_plain_text_ai(self):
        text_exact = (
            "AI-generated text often cannot be verified or retrieved by "
            "anyone other than the original author"
        )
        assert compute_hash(text_exact) == \
            "sha256:b8ba02cbee19230434c6a5b1431c0f8bfab8e00eb13b670875faa874959fb298"


# -- NFC Normalization --


class TestNormalization:
    """NFC normalization must produce identical hashes for equivalent inputs."""

    def test_nfd_nfc_equivalence(self):
        """Decomposed (e + combining acute) == precomposed (e)."""
        nfd = compute_hash("cafe\u0301")
        nfc = compute_hash("caf\u00e9")
        assert nfd == nfc
        assert nfd == "sha256:b433ffec5f0511a6d43881e4fb8bed86ba6616a16608477478c0cdd872b48285"

    def test_angstrom_nfc(self):
        """U+212B (Angstrom) normalizes to U+00C5 (Latin A with ring above)."""
        assert compute_hash("\u212B") == \
            "sha256:e89cc1c9076e00a3ec13fd451c04aef915732b0cf25cc3d26478552198ab2c6e"

    def test_hangul_jamo_composition(self):
        """Hangul Jamo leading consonant + vowel compose under NFC."""
        assert compute_hash("\u1100\u1161") == \
            "sha256:17a436bf3abdb0060ee3ba7e6c0208d688354386a8042679a22fb660740066cf"

    def test_nbsp_not_collapsed(self):
        """Non-breaking space (U+00A0) must NOT be treated as whitespace."""
        nbsp_hash = compute_hash("hello\u00a0world")
        space_hash = compute_hash("hello world")
        assert nbsp_hash != space_hash
        assert nbsp_hash == "sha256:2eceb2ef315fb702311c91140076a43159d6e99b5b738f035cff65d08daeab1f"

    def test_whitespace_collapse(self):
        """Tabs, newlines, multiple spaces collapse to single space."""
        assert compute_hash("Hello,   world!\n\ttest") == \
            "sha256:f97fd0de4198f3a6ba7dbfb83e7cc1c45b23905f9fa4330c12c15a260f1a1542"


# -- Context Padding --


class TestContextPadding:
    """Context windows must be exactly 50 code points after padding/truncation."""

    def test_exact_50_chars(self):
        """50-char context needs no padding or truncation."""
        assert compute_hash("test", "A" * 50, "A" * 50) == \
            "sha256:deb6e1e50d10560c7e65a4c48c1e7d7c58bf212935c091043b735fbefb317d4c"

    def test_over_length_truncation(self):
        """100-char context truncated to first 50."""
        assert compute_hash("test", "B" * 100, "B" * 100) == \
            "sha256:86309984bf5222c0dbdb2611a75ad25df73e852f7f8d697414b880be6a97d4b4"

    def test_truncation_equivalence(self):
        """100-char context of same char produces same hash as 50-char."""
        assert compute_hash("test", "A" * 100, "A" * 100) == \
            compute_hash("test", "A" * 50, "A" * 50)

    def test_short_padding(self):
        """Short context space-padded to 50."""
        assert compute_hash("test", "short", "ctx") == \
            "sha256:a16f3204c5229ddd197e60ad3cfeefe38ce956ec586825f83671bcabbb329980"

    def test_49_char_boundary(self):
        """49-char context gets 1 space of padding."""
        assert compute_hash("test", "X" * 49, "") == \
            "sha256:ec71a933caf02232061eaec28ba101e856d1a97a9ba1232acb77223beb1fa1ac"


# -- Edge Cases --


class TestEdgeCases:
    """Corner cases: empty inputs, special characters, delimiters."""

    def test_empty_all(self):
        assert compute_hash("", "", "") == \
            "sha256:da6f851a04676cd01c5e80335da666433c880012982d53cb022336bf565acfbd"

    def test_whitespace_only_equals_empty(self):
        """Whitespace-only exact text normalizes to empty."""
        assert compute_hash("   \t\n  ") == compute_hash("")

    def test_pipe_in_exact(self):
        """Pipe delimiter in exact text does not break the algorithm."""
        assert compute_hash("a|b|c") == \
            "sha256:277e31e19888f6d24cd513dcd3b4850518c0fc55966ebc52dd87288863ca421a"

    def test_cjk_characters(self):
        """CJK characters count as code points, not bytes."""
        assert compute_hash("\u4f60\u597d\u4e16\u754c") == \
            "sha256:784d8327eb064ca62d2bfbfd5542f42336d154c885bfe98dda565b76606065ed"

    def test_emoji(self):
        """Astral plane emoji are single code points."""
        assert compute_hash("\U0001F600\U0001F4A1") == \
            "sha256:313603505a6cde53ee7148c3bfadb403e10036c2612be9783dac874d4c70fc6d"

    def test_empty_context_simple(self):
        assert compute_hash("Hello, world!") == \
            "sha256:cad437fb7351553fe2d565e4b67e59713e063222a2c65a2f768cce73352a1586"


# -- Determinism --


class TestDeterminism:
    """The algorithm must be deterministic across repeated calls."""

    def test_1000_identical_calls(self):
        results = {compute_hash("test", "before", "after") for _ in range(1000)}
        assert len(results) == 1


# -- Internal Functions --


class TestInternals:
    """Unit tests for normalize_segment and pad_context."""

    def test_normalize_nfc(self):
        assert normalize_segment("cafe\u0301") == "caf\u00e9"

    def test_normalize_whitespace(self):
        assert normalize_segment("  hello   world\t\n ") == "hello world"

    def test_normalize_empty(self):
        assert normalize_segment("") == ""

    def test_normalize_whitespace_only(self):
        assert normalize_segment("   \t\n  ") == ""

    def test_pad_exact(self):
        assert len(pad_context("A" * 50)) == 50

    def test_pad_short(self):
        result = pad_context("hi")
        assert len(result) == 50
        assert result == "hi" + " " * 48

    def test_pad_long_truncates(self):
        result = pad_context("B" * 100)
        assert len(result) == 50
        assert result == "B" * 50

    def test_pad_empty(self):
        assert pad_context("") == " " * 50


# -- YAML-Driven Tests --


class TestFromYAML:
    """Run all vectors from the YAML file to catch any discrepancy."""

    def _run_vectors(self, vectors_list):
        for v in vectors_list:
            result = compute_hash(
                v["text_exact"],
                v.get("text_before", ""),
                v.get("text_after", ""),
            )
            assert result == v["expected_hash"], \
                f"Vector {v['id']} failed: expected {v['expected_hash']}, got {result}"

    def test_all_spec_vectors(self, vectors):
        self._run_vectors(vectors["spec_vectors"])

    def test_all_appendix_vectors(self, vectors):
        self._run_vectors(vectors["appendix_vectors"])

    def test_all_edge_case_vectors(self, vectors):
        self._run_vectors(vectors["edge_case_vectors"])
