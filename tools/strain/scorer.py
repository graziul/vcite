"""Citation strain measurement — baseline implementation.

RESEARCH PROTOTYPE — not production code. See DESIGN.md for context.

Computes strain between a cited passage (text_exact) and the claiming
context (the sentence where the citation appears in the citing document).

This module provides stdlib-only methods (lexical overlap, n-gram
divergence). Embedding-based and NLI-based scorers are stubbed for
future implementation with optional ML dependencies.

See DESIGN.md for the full research direction.
"""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class StrainComponents:
    """Individual components that contribute to the strain score."""
    jaccard_overlap: float = 0.0      # token-level Jaccard similarity
    rouge_l: float = 0.0             # longest common subsequence ratio
    idf_overlap: float = 0.0         # IDF-weighted token overlap
    bigram_divergence: float = 0.0   # Jensen-Shannon divergence of bigrams
    # Future ML-based components (populated by optional scorers)
    embedding_distance: Optional[float] = None
    nli_entailment: Optional[float] = None
    nli_contradiction: Optional[float] = None


@dataclass
class LocalStrain:
    """Strain measurement for a single citation."""
    citation_id: str
    score: float                      # 0.0 (faithful) to 1.0 (distorted)
    components: StrainComponents
    text_exact: str                   # what the source says
    claiming_context: str             # what the citing document claims
    relation: str                     # VCITE relation type
    method: str = "lexical"           # scoring method used
    calibrated: bool = False          # whether discipline calibration applied
    discipline: str = ""              # discipline used for calibration


@dataclass
class GlobalStrain:
    """Aggregate strain for an entire document."""
    global_score: float               # aggregate strain
    consistency_score: float          # sheaf consistency (1.0 = fully consistent)
    citation_count: int
    max_local_strain: float
    mean_local_strain: float
    median_local_strain: float
    strain_distribution: dict         # {"low": n, "moderate": n, "high": n}
    local_strains: list[LocalStrain]
    sheaf_obstructions: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Text normalization for strain comparison
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "not", "no", "as", "if", "than",
    "also", "such", "which", "who", "whom", "whose", "when", "where",
    "how", "what", "each", "every", "all", "both", "few", "more", "most",
    "other", "some", "any", "only", "own", "same", "so", "very",
})


def _tokenize(text: str) -> list[str]:
    """Lowercase, NFC-normalize, split on non-alphanumeric, remove stopwords."""
    text = unicodedata.normalize("NFC", text.lower())
    tokens = re.findall(r"[a-z\u00c0-\u024f\u0400-\u04ff']+|\d+", text)
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def _bigrams(tokens: list[str]) -> list[str]:
    """Generate bigrams from a token list."""
    return [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]


# ---------------------------------------------------------------------------
# Lexical strain components
# ---------------------------------------------------------------------------

def jaccard_similarity(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Jaccard similarity between two token sets."""
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def rouge_l(tokens_a: list[str], tokens_b: list[str]) -> float:
    """ROUGE-L: longest common subsequence ratio.

    Returns F1-like score combining precision and recall of the LCS.
    """
    if not tokens_a or not tokens_b:
        return 0.0
    m, n = len(tokens_a), len(tokens_b)
    # DP table for LCS length
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if tokens_a[i-1] == tokens_b[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    lcs_len = dp[m][n]
    if lcs_len == 0:
        return 0.0
    precision = lcs_len / n
    recall = lcs_len / m
    return (2 * precision * recall) / (precision + recall)


def idf_weighted_overlap(
    tokens_a: list[str],
    tokens_b: list[str],
    corpus_freqs: Optional[dict[str, int]] = None,
    corpus_size: int = 1000,
) -> float:
    """IDF-weighted token overlap.

    Emphasizes informative (rare) shared terms over common ones.
    If no corpus frequencies provided, uses uniform weights (falls back
    to regular Jaccard).
    """
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    shared = set_a & set_b
    all_tokens = set_a | set_b
    if not all_tokens:
        return 0.0

    if corpus_freqs is None:
        return len(shared) / len(all_tokens)

    def idf(token):
        df = corpus_freqs.get(token, 1)
        return math.log((corpus_size + 1) / (df + 1))

    shared_weight = sum(idf(t) for t in shared)
    total_weight = sum(idf(t) for t in all_tokens)
    return shared_weight / total_weight if total_weight > 0 else 0.0


def jensen_shannon_divergence(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Jensen-Shannon divergence between bigram distributions.

    Returns value in [0, 1] where 0 = identical distributions.
    Uses bigrams for phrase-level comparison.
    NOTE: Uses math.log2 — the [0,1] bound depends on base-2 logarithm.
    """
    bigrams_a = _bigrams(tokens_a)
    bigrams_b = _bigrams(tokens_b)
    if not bigrams_a or not bigrams_b:
        return 1.0

    count_a = Counter(bigrams_a)
    count_b = Counter(bigrams_b)
    all_bigrams = set(count_a.keys()) | set(count_b.keys())

    total_a = sum(count_a.values())
    total_b = sum(count_b.values())

    # Compute probability distributions with Laplace smoothing
    vocab = len(all_bigrams)
    def prob_a(bg):
        return (count_a.get(bg, 0) + 1) / (total_a + vocab)
    def prob_b(bg):
        return (count_b.get(bg, 0) + 1) / (total_b + vocab)

    # M = (P + Q) / 2
    jsd = 0.0
    for bg in all_bigrams:
        p = prob_a(bg)
        q = prob_b(bg)
        m = (p + q) / 2
        if p > 0:
            jsd += 0.5 * p * math.log2(p / m)
        if q > 0:
            jsd += 0.5 * q * math.log2(q / m)

    return min(jsd, 1.0)


# ---------------------------------------------------------------------------
# Main strain scorer
# ---------------------------------------------------------------------------

def compute_strain_lexical(
    text_exact: str,
    claiming_context: str,
) -> StrainComponents:
    """Compute lexical strain components between source and claim.

    Uses only stdlib — no ML dependencies required.
    """
    tokens_source = _tokenize(text_exact)
    tokens_claim = _tokenize(claiming_context)

    jaccard = jaccard_similarity(tokens_source, tokens_claim)
    rl = rouge_l(tokens_source, tokens_claim)
    idf_ov = idf_weighted_overlap(tokens_source, tokens_claim)
    jsd = jensen_shannon_divergence(tokens_source, tokens_claim)

    return StrainComponents(
        jaccard_overlap=jaccard,
        rouge_l=rl,
        idf_overlap=idf_ov,
        bigram_divergence=jsd,
    )


def components_to_score(components: StrainComponents) -> float:
    """Convert strain components to a single [0, 1] score.

    Higher score = more strain (less faithful citation).

    Current formula (uncalibrated):
      strain = (1 - weighted_mean(jaccard, rouge_l, idf_overlap)
                + 0.2 * bigram_divergence) / 1.2

    The /1.2 normalization ensures the output stays in [0, 1]
    without relying on clamping (max raw value is 1.0 + 0.2 = 1.2).

    This is a placeholder. Calibrated scoring will replace this with
    discipline-specific regression coefficients.
    """
    similarity = (
        0.3 * components.jaccard_overlap
        + 0.4 * components.rouge_l
        + 0.3 * components.idf_overlap
    )
    strain = (1.0 - similarity + 0.2 * components.bigram_divergence) / 1.2

    # Incorporate NLI if available
    if components.nli_entailment is not None:
        # NLI entailment directly reduces strain
        nli_strain = 1.0 - components.nli_entailment
        if components.nli_contradiction is not None:
            nli_strain += 0.3 * components.nli_contradiction
        nli_strain = min(1.0, nli_strain)
        # Blend: 60% NLI, 40% lexical (NLI is more semantically meaningful)
        strain = 0.4 * strain + 0.6 * nli_strain

    return max(0.0, min(1.0, strain))


def compute_local_strain(
    citation,  # VCiteCitation
    claiming_context: str,
    method: str = "lexical",
) -> LocalStrain:
    """Compute strain for a single citation.

    Args:
        citation: A VCiteCitation object
        claiming_context: The sentence in the citing document where
            this citation appears
        method: Scoring method ("lexical", "embedding", "nli", "ensemble")
    """
    components = compute_strain_lexical(
        citation.target.text_exact,
        claiming_context,
    )

    score = components_to_score(components)

    return LocalStrain(
        citation_id=citation.id,
        score=score,
        components=components,
        text_exact=citation.target.text_exact,
        claiming_context=claiming_context,
        relation=citation.relation,
        method=method,
    )


# ---------------------------------------------------------------------------
# Claiming context extraction
# ---------------------------------------------------------------------------

def extract_claiming_context(
    article_text: str,
    citation,  # VCiteCitation
    window: int = 200,
) -> str:
    """Extract the claiming context for a citation from the citing article.

    Searches for text_exact in the article and returns the surrounding
    sentence/clause. This is the text the AUTHOR wrote, not the source.

    Falls back to text_before + text_after from the citation object
    if the article text is not available.
    """
    target = citation.target.text_exact

    # Normalize for search
    norm_article = unicodedata.normalize("NFC", article_text)
    norm_target = unicodedata.normalize("NFC", target)

    idx = norm_article.find(norm_target)
    if idx < 0:
        # Try case-insensitive
        idx = norm_article.lower().find(norm_target.lower())

    if idx >= 0:
        # Found the cited passage in the article — get surrounding text
        region_start = max(0, idx - window)
        region_end = min(len(norm_article), idx + len(norm_target) + window)
        region = norm_article[region_start:region_end]

        # Extract the sentence containing and surrounding the citation
        # NOTE: This naive splitter will mis-split on abbreviations like
        # "et al.", "Fig.", "Dr." — acceptable for prototype, but a
        # production scorer should use a proper sentence tokenizer.
        sentences = re.split(r'(?<=[.!?])\s+', region)
        # Find sentence(s) containing the target
        relevant = []
        for sent in sentences:
            if norm_target[:30].lower() in sent.lower() or \
               norm_target[-30:].lower() in sent.lower():
                relevant.append(sent)
            elif relevant:
                # Include one sentence after
                relevant.append(sent)
                break

        if relevant:
            return " ".join(relevant).strip()

        return region.strip()

    # Fallback: use the before/after context from the citation itself
    return f"{citation.target.text_before}{target}{citation.target.text_after}"


# ---------------------------------------------------------------------------
# Strain classification thresholds
# ---------------------------------------------------------------------------

def classify_strain(score: float) -> str:
    """Classify a strain score into a human-readable category.

    Thresholds are uncalibrated defaults. Discipline-specific
    calibration will adjust these.
    """
    if score < 0.25:
        return "low"
    elif score < 0.50:
        return "moderate"
    elif score < 0.75:
        return "high"
    else:
        return "extreme"
