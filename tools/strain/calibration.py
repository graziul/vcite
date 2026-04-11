"""Discipline-specific calibration for citation strain.

Raw strain scores are not directly comparable across disciplines.
A strain score of 0.3 might be perfectly normal in legal scholarship
(where interpretive citation is expected) but alarming in hard science
(where citations should closely track source claims).

This module provides:
  1. Discipline profiles with baseline parameters
  2. Calibration functions that map raw strain to discipline-adjusted strain
  3. A framework for fitting calibration curves from annotated corpora

See DESIGN.md §4 for the full calibration strategy.
"""

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DisciplineProfile:
    """Strain calibration parameters for a specific discipline.

    These are initial estimates based on qualitative analysis of
    citation norms. They should be replaced with empirically-fitted
    parameters from annotated corpora.
    """
    name: str
    # Expected strain distribution parameters
    baseline_mean: float       # mean strain in well-cited papers
    baseline_std: float        # standard deviation of strain
    # Thresholds (discipline-adjusted)
    low_threshold: float       # below this = low strain
    moderate_threshold: float  # below this = moderate strain
    high_threshold: float      # below this = high strain; above = extreme
    # Relation-specific adjustments
    # Some relations inherently involve higher strain (e.g., "contextualizes"
    # involves more interpretive distance than "supports")
    relation_adjustments: dict[str, float] = field(default_factory=dict)
    # Legal signal adjustments (only for legal scholarship)
    signal_adjustments: dict[str, float] = field(default_factory=dict)
    # Notes on discipline norms
    notes: str = ""


# ---------------------------------------------------------------------------
# Pre-defined discipline profiles (initial estimates)
# ---------------------------------------------------------------------------

PROFILES: dict[str, DisciplineProfile] = {
    "hard_science": DisciplineProfile(
        name="Hard Sciences (Physics, Chemistry, Biology)",
        baseline_mean=0.15,
        baseline_std=0.08,
        low_threshold=0.20,
        moderate_threshold=0.35,
        high_threshold=0.55,
        relation_adjustments={
            "supports": 0.0,
            "contradicts": 0.10,  # citing opposing evidence is expected
            "defines": -0.05,     # definitions should be very close
            "quantifies": -0.05,  # numbers should match precisely
            "contextualizes": 0.10,
            "method": -0.03,
            "cautions": 0.05,
        },
        notes=(
            "Hard sciences value precision. Citations should closely track "
            "source claims. High strain typically indicates misrepresentation."
        ),
    ),

    "social_science": DisciplineProfile(
        name="Social Sciences (Sociology, Political Science, Economics)",
        baseline_mean=0.22,
        baseline_std=0.12,
        low_threshold=0.25,
        moderate_threshold=0.45,
        high_threshold=0.65,
        relation_adjustments={
            "supports": 0.0,
            "contradicts": 0.10,
            "defines": 0.0,
            "quantifies": -0.05,
            "contextualizes": 0.15,  # theoretical framing involves interpretation
            "method": 0.0,
            "cautions": 0.05,
        },
        notes=(
            "Social sciences allow moderate interpretive framing. "
            "Theoretical citation (contextualizes) inherently involves more "
            "distance from the source text."
        ),
    ),

    "humanities": DisciplineProfile(
        name="Humanities (History, Philosophy, Literature)",
        baseline_mean=0.30,
        baseline_std=0.15,
        low_threshold=0.30,
        moderate_threshold=0.50,
        high_threshold=0.70,
        relation_adjustments={
            "supports": 0.0,
            "contradicts": 0.10,
            "defines": 0.05,
            "quantifies": -0.05,
            "contextualizes": 0.20,  # hermeneutic interpretation is central
            "method": 0.05,
            "cautions": 0.05,
        },
        notes=(
            "Humanities citation is inherently interpretive. Hermeneutic "
            "tradition means sources are read through theoretical lenses. "
            "What would be 'high strain' in physics is normal here."
        ),
    ),

    "legal": DisciplineProfile(
        name="Legal Scholarship",
        baseline_mean=0.25,
        baseline_std=0.18,
        low_threshold=0.25,
        moderate_threshold=0.50,
        high_threshold=0.70,
        relation_adjustments={
            "supports": 0.0,
            "contradicts": 0.05,  # adversarial citation is conventional
            "defines": -0.05,
            "quantifies": -0.05,
            "contextualizes": 0.15,
            "method": 0.0,
            "cautions": 0.05,
        },
        signal_adjustments={
            # Bluebook signals encode expected strain
            "see": 0.0,           # direct support
            "see_also": 0.05,     # additional support
            "see_generally": 0.15, # background — more interpretive distance
            "cf": 0.25,           # analogous — significant interpretive leap
            "but_see": 0.35,      # contrary authority — high strain by design
            "contra": 0.45,       # direct contradiction — maximum by design
            "compare": 0.20,      # comparison — moderate distance
        },
        notes=(
            "Legal citation uses Bluebook signals (see, cf., but see, etc.) "
            "that explicitly encode expected interpretive distance. "
            "The signal itself is a strain annotation — calibration should "
            "use signal-labeled legal corpora as ground truth."
        ),
    ),

    "journalism": DisciplineProfile(
        name="Journalism",
        baseline_mean=0.28,
        baseline_std=0.14,
        low_threshold=0.30,
        moderate_threshold=0.50,
        high_threshold=0.65,
        relation_adjustments={
            "supports": 0.0,
            "contradicts": 0.05,
            "defines": 0.0,
            "quantifies": -0.10,  # numbers should be precise
            "contextualizes": 0.15,
            "method": 0.0,
            "cautions": 0.05,
        },
        notes=(
            "Journalism paraphrases heavily — higher baseline strain is "
            "normal. But quantitative claims should track sources precisely. "
            "Journalistic distortion is a well-studied phenomenon."
        ),
    ),

    "ai_output": DisciplineProfile(
        name="AI-Generated Content",
        baseline_mean=0.10,
        baseline_std=0.05,
        low_threshold=0.15,
        moderate_threshold=0.30,
        high_threshold=0.45,
        relation_adjustments={
            "supports": 0.0,
            "contradicts": 0.05,
            "defines": -0.05,
            "quantifies": -0.05,
            "contextualizes": 0.05,
            "method": 0.0,
            "cautions": 0.0,
        },
        notes=(
            "AI-generated text should not editorialize on sources. Low "
            "strain expected. High strain in AI output may indicate "
            "hallucination or confabulation rather than interpretation."
        ),
    ),
}


# ---------------------------------------------------------------------------
# Calibration functions
# ---------------------------------------------------------------------------

def get_profile(discipline: str) -> DisciplineProfile:
    """Get the discipline profile, falling back to social_science default."""
    return PROFILES.get(discipline, PROFILES["social_science"])


def calibrate_score(
    raw_score: float,
    discipline: str,
    relation: str = "supports",
    legal_signal: Optional[str] = None,
) -> float:
    """Calibrate a raw strain score for discipline and relation context.

    Adjusts the raw score based on:
    1. Discipline baseline (what's "normal" strain for this field)
    2. Relation type (some relations inherently involve more distance)
    3. Legal citation signal (if applicable)

    The calibrated score is a z-score-like value: how many standard
    deviations this citation's strain is from the discipline baseline,
    then mapped back to [0, 1] via a sigmoid.

    Returns:
        Calibrated strain score in [0.0, 1.0]
    """
    profile = get_profile(discipline)

    # Apply relation adjustment
    adjusted = raw_score - profile.relation_adjustments.get(relation, 0.0)

    # Apply legal signal adjustment
    if legal_signal and profile.signal_adjustments:
        signal_adj = profile.signal_adjustments.get(legal_signal, 0.0)
        adjusted -= signal_adj  # subtract because signal "explains" the strain

    # Compute z-score relative to discipline baseline
    if profile.baseline_std > 0:
        z = (adjusted - profile.baseline_mean) / profile.baseline_std
    else:
        z = 0.0

    # Map z-score to [0, 1] via sigmoid
    # z = 0 → 0.5 (average for discipline)
    # z = 2 → ~0.88 (high for discipline)
    # z = -2 → ~0.12 (low for discipline)
    calibrated = 1.0 / (1.0 + math.exp(-z))

    return max(0.0, min(1.0, calibrated))


def classify_calibrated(
    calibrated_score: float,
    discipline: str,
) -> str:
    """Classify calibrated strain using discipline-specific thresholds."""
    profile = get_profile(discipline)
    if calibrated_score < profile.low_threshold:
        return "low"
    elif calibrated_score < profile.moderate_threshold:
        return "moderate"
    elif calibrated_score < profile.high_threshold:
        return "high"
    else:
        return "extreme"


# ---------------------------------------------------------------------------
# Calibration fitting (future: from annotated corpora)
# ---------------------------------------------------------------------------

@dataclass
class CalibrationDatapoint:
    """One labeled example for fitting calibration curves.

    For building discipline-specific calibration, we need:
    - Raw strain scores from the scorer
    - Human or expert labels of citation quality
    - Discipline and relation metadata
    """
    raw_score: float
    human_label: float    # 0.0 = faithful, 1.0 = distorted
    discipline: str
    relation: str
    source_type: str      # academic, journalism, web, grey, ai_output
    legal_signal: str = ""
    # Optional metadata
    citation_id: str = ""
    source_title: str = ""
    notes: str = ""


def fit_profile_from_data(
    datapoints: list[CalibrationDatapoint],
    discipline: str,
) -> DisciplineProfile:
    """Fit a discipline profile from labeled calibration data.

    This is a placeholder for the full calibration pipeline.
    A production implementation would:
    1. Compute mean and std of raw scores for "faithful" citations
    2. Fit relation-specific adjustments via regression
    3. Set thresholds via ROC analysis against human labels

    Currently returns a simple empirical profile.
    """
    if not datapoints:
        return get_profile(discipline)

    scores = [d.raw_score for d in datapoints]
    labels = [d.human_label for d in datapoints]

    mean_score = sum(scores) / len(scores)
    variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
    std_score = math.sqrt(variance) if variance > 0 else 0.1

    # Compute relation-specific means
    relation_groups: dict[str, list[float]] = {}
    for dp in datapoints:
        relation_groups.setdefault(dp.relation, []).append(dp.raw_score)

    relation_adjustments = {}
    for rel, rel_scores in relation_groups.items():
        rel_mean = sum(rel_scores) / len(rel_scores)
        relation_adjustments[rel] = rel_mean - mean_score

    # Set thresholds at percentiles of "faithful" citations
    faithful = sorted(d.raw_score for d in datapoints if d.human_label < 0.5)
    if faithful:
        n = len(faithful)
        low_t = faithful[int(n * 0.75)] if n > 3 else mean_score
        mod_t = faithful[int(n * 0.90)] if n > 9 else mean_score + std_score
        high_t = faithful[int(n * 0.95)] if n > 19 else mean_score + 2 * std_score
    else:
        low_t = mean_score
        mod_t = mean_score + std_score
        high_t = mean_score + 2 * std_score

    return DisciplineProfile(
        name=f"Fitted: {discipline}",
        baseline_mean=mean_score,
        baseline_std=std_score,
        low_threshold=low_t,
        moderate_threshold=mod_t,
        high_threshold=high_t,
        relation_adjustments=relation_adjustments,
        notes=f"Empirically fitted from {len(datapoints)} datapoints",
    )
