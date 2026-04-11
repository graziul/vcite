"""Sheaf consistency checker for citation strain.

Implements the local-to-global consistency analysis described in
DESIGN.md §3. Given a set of local strain measurements, checks
whether citations to the same source are used consistently.

The sheaf structure:
  - Nodes: sources cited in the document
  - Edges: individual citations (local sections)
  - Consistency: citations to the same source should not strain
    in contradictory directions

Obstruction detection identifies incoherent use of sources —
places where the author interprets the same source differently
in different parts of the document.

See: Robinson (2014), "Topological Signal Processing" for the
mathematical framework underlying this approach.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from scorer import LocalStrain, classify_strain


@dataclass
class SourceCluster:
    """All citations in a document that reference the same source."""
    source_key: str             # DOI, URL, or title used to identify source
    source_title: str
    citations: list[LocalStrain]
    mean_strain: float = 0.0
    strain_variance: float = 0.0
    max_strain_gap: float = 0.0  # max difference between any two citations
    consistent: bool = True


@dataclass
class SheafObstruction:
    """A detected inconsistency in how a source is cited.

    When two citations to the same source have strain scores that
    differ by more than the consistency threshold, this indicates
    the author is interpreting the source differently in different
    contexts — a sheaf gluing failure.
    """
    source_key: str
    source_title: str
    citation_a: str  # id
    citation_b: str  # id
    strain_a: float
    strain_b: float
    strain_gap: float
    description: str


@dataclass
class ConsistencyReport:
    """Full sheaf consistency analysis for a document."""
    consistency_score: float      # 0.0–1.0 (1.0 = fully consistent)
    source_clusters: list[SourceCluster]
    obstructions: list[SheafObstruction]
    multi_cited_sources: int      # sources cited more than once
    single_cited_sources: int


def _source_key(local_strain: LocalStrain, citation=None) -> str:
    """Generate a key for grouping citations by source.

    Uses DOI if available, then URL, then title (normalized).
    """
    if citation is not None:
        if citation.source.doi:
            return f"doi:{citation.source.doi}"
        if citation.source.url:
            return f"url:{citation.source.url}"
        return f"title:{citation.source.title.lower().strip()}"

    # Fallback: use the text_exact as a poor proxy (shouldn't happen)
    return f"text:{local_strain.text_exact[:50]}"


def cluster_by_source(
    local_strains: list[LocalStrain],
    citations: list = None,  # list[VCiteCitation], optional
) -> list[SourceCluster]:
    """Group local strain measurements by their source document.

    If VCiteCitation objects are provided, uses DOI/URL/title for
    grouping. Otherwise falls back to citation_id prefix matching.
    """
    groups: dict[str, list[tuple[LocalStrain, Optional[object]]]] = defaultdict(list)

    if citations and len(citations) == len(local_strains):
        for ls, cit in zip(local_strains, citations):
            key = _source_key(ls, cit)
            groups[key].append((ls, cit))
    else:
        # Without citation objects, each strain is its own group
        for ls in local_strains:
            groups[f"id:{ls.citation_id}"].append((ls, None))

    clusters = []
    for key, items in groups.items():
        strains = [item[0] for item in items]
        scores = [s.score for s in strains]

        mean = sum(scores) / len(scores) if scores else 0.0
        variance = (
            sum((s - mean) ** 2 for s in scores) / len(scores)
            if len(scores) > 1 else 0.0
        )
        max_gap = max(scores) - min(scores) if len(scores) > 1 else 0.0

        # Use title from the first citation if available
        title = key
        if items[0][1] is not None:
            title = items[0][1].source.title

        clusters.append(SourceCluster(
            source_key=key,
            source_title=title,
            citations=strains,
            mean_strain=mean,
            strain_variance=variance,
            max_strain_gap=max_gap,
            consistent=(max_gap < 0.3),  # threshold for consistency
        ))

    return clusters


def detect_obstructions(
    clusters: list[SourceCluster],
    threshold: float = 0.3,
) -> list[SheafObstruction]:
    """Detect sheaf obstructions — inconsistent use of the same source.

    An obstruction occurs when two citations to the same source have
    strain scores differing by more than `threshold`. This indicates
    the author interprets the same source differently in different
    parts of the document.

    Args:
        clusters: Source clusters from cluster_by_source()
        threshold: Maximum acceptable strain gap (default: 0.3)

    Returns:
        List of detected obstructions
    """
    obstructions = []

    for cluster in clusters:
        if len(cluster.citations) < 2:
            continue

        # Check all pairs
        for i in range(len(cluster.citations)):
            for j in range(i + 1, len(cluster.citations)):
                a = cluster.citations[i]
                b = cluster.citations[j]
                gap = abs(a.score - b.score)

                if gap >= threshold:
                    # Describe the nature of the inconsistency
                    cat_a = classify_strain(a.score)
                    cat_b = classify_strain(b.score)

                    desc = (
                        f"Source '{cluster.source_title}' is cited with "
                        f"{cat_a} strain ({a.score:.2f}) at {a.citation_id} "
                        f"and {cat_b} strain ({b.score:.2f}) at {b.citation_id}. "
                        f"Gap: {gap:.2f} exceeds threshold {threshold:.2f}."
                    )

                    obstructions.append(SheafObstruction(
                        source_key=cluster.source_key,
                        source_title=cluster.source_title,
                        citation_a=a.citation_id,
                        citation_b=b.citation_id,
                        strain_a=a.score,
                        strain_b=b.score,
                        strain_gap=gap,
                        description=desc,
                    ))

                    cluster.consistent = False

    return obstructions


def compute_consistency_score(
    clusters: list[SourceCluster],
    obstructions: list[SheafObstruction],
) -> float:
    """Compute a global consistency score from sheaf analysis.

    The score reflects what fraction of multi-cited sources are
    used consistently. Single-cited sources don't contribute
    (they're trivially consistent — there's no overlap to check).

    Returns:
        Float in [0.0, 1.0] where 1.0 = fully consistent
    """
    multi_cited = [c for c in clusters if len(c.citations) > 1]
    if not multi_cited:
        return 1.0  # no overlaps to check

    consistent_count = sum(1 for c in multi_cited if c.consistent)
    return consistent_count / len(multi_cited)


def analyze_consistency(
    local_strains: list[LocalStrain],
    citations: list = None,
    threshold: float = 0.3,
) -> ConsistencyReport:
    """Full sheaf consistency analysis.

    Args:
        local_strains: Per-citation strain measurements
        citations: Optional VCiteCitation objects for source grouping
        threshold: Maximum acceptable strain gap between co-source citations

    Returns:
        ConsistencyReport with clusters, obstructions, and scores
    """
    clusters = cluster_by_source(local_strains, citations)
    obstructions = detect_obstructions(clusters, threshold)
    consistency = compute_consistency_score(clusters, obstructions)

    multi = sum(1 for c in clusters if len(c.citations) > 1)
    single = sum(1 for c in clusters if len(c.citations) == 1)

    return ConsistencyReport(
        consistency_score=consistency,
        source_clusters=clusters,
        obstructions=obstructions,
        multi_cited_sources=multi,
        single_cited_sources=single,
    )
