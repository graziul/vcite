# Citation Strain: Design & Research Exploration

> **STATUS: RESEARCH PROTOTYPE** — This is an exploratory research direction,
> not production tooling. The scoring algorithms, calibration parameters, and
> sheaf formalization are initial implementations for validation against
> annotated corpora. Do not use for automated editorial decisions.

> **KNOWN GAP (2026-04-22)** — The strain model in this document assumes
> `target.text_exact` is the **source passage**. In the current
> `tools/enhance.py` extractor, `text_exact` is set to the **citing-article
> sentence** that contains the citation, so `compute_local_strain(citation,
> claiming_context)` ends up comparing two slices of the citing document,
> not source against claim. Strain numbers from that pipeline measure
> "context divergence within the citing article," which is not what this
> design specifies.
>
> To produce DESIGN-aligned strain, either (a) run verification online so the
> matched passage from the source is available and then compute
> `strain(matched_source_passage, text_exact_from_article)`, or (b) change
> the extractor to set `text_exact` to a quoted span that truly lives in the
> source. Until one of these lands, `tools/enrich.py` emits strain as an
> optional signal that renderers may choose to suppress. The verification
> pipeline (`enrichment.verification`) is not subject to this gap — it's
> purely a hash/fetch check and is correct today.

## 1. What Is Strain?

Every citation creates a relationship between two texts:

- **Source passage** (`text_exact`): what the cited source actually says
- **Claiming context**: the sentence in the citing document where the citation
  appears — the claim being made _about_ the source

**Strain** measures the semantic distance between these two texts: how much
the citing author stretched, recontextualized, or distorted the source's
meaning to support their claim.

A citation with zero strain would be a direct quote used to make the exact
point the original author intended. A citation with maximum strain would
attribute a claim to a source that says nothing of the sort.

Most real citations fall somewhere in between — and the "acceptable" range
depends on discipline, citation convention, and rhetorical function.

## 2. Why This Matters for VCITE

VCITE already enables cryptographic verification that a passage _exists_ in a
source. Strain adds the semantic dimension: does the passage actually _mean_
what the citing author implies? This closes the gap between existence
verification (hash check) and meaning verification (strain check).

Together, they answer: "Is this citation honest?"

## 3. The Sheaf Structure

Citation strain is not just a per-citation number. It has a natural
local-to-global geometry that can be formalized using sheaf theory.

### 3.1 Local Sections (Per-Claim Strain)

Each citation in a document is a **local section**: a measurement of strain
at one point in the document's citation graph. The local strain score
captures how faithfully one specific claim represents one specific source
passage.

### 3.2 Global Sections (Per-Document Strain)

The **global section** aggregates local strains into a document-level picture.
But this is not just an average — it has structure:

- A document might have low average strain but one extreme outlier
  (a single misrepresented source propping up a key claim)
- A document might systematically strain in one direction (all citations
  subtly overstated to support a narrative)
- A document might cite the same source multiple times with inconsistent
  strain (contradictory interpretations of the same evidence)

### 3.3 Consistency Conditions

The sheaf perspective adds a **gluing axiom**: local sections must be
compatible on overlaps. In citation terms:

- If citation A and citation B both cite Source X, their strain vectors
  should be compatible — they shouldn't interpret the same source in
  contradictory ways unless the citing document explicitly acknowledges
  the tension
- If citation A supports claim P, and citation B supports claim ¬P,
  and both cite the same source, at least one has high strain
- The consistency check across all citations of a given source is a
  sheaf cohomology computation — obstructions to gluing indicate
  incoherent use of sources

### 3.4 Why Not Just Cosine Similarity?

Raw embedding distance misses this structure entirely. Two citations might
each have moderate strain individually, but be incompatible when considered
together (violating the gluing axiom). The sheaf formulation captures
relationships between citations, not just individual scores.

### 3.5 Formal Sketch

Let G = (V, E) be the citation graph where V = {documents} and E = {citations}.
Define a sheaf F over G:

- **Stalks**: F(v) = the semantic embedding space at document v
- **Restriction maps**: F(e) maps the cited passage embedding to the
  claiming context embedding along edge e
- **Local strain**: ||F(e)(source) - claim|| in the embedding space
- **Global strain**: H⁰(G, F) measures global consistency; H¹(G, F)
  detects obstruction to coherent interpretation

The sheaf Laplacian (Robinson, 2014) provides a computable approximation:
large eigenvalues of the sheaf Laplacian indicate high-strain regions of
the citation graph.

## 4. Discipline Dependence

### 4.1 The Calibration Problem

What constitutes "normal" strain varies dramatically by field:

| Discipline | Expected Strain Range | Why |
|-----------|----------------------|-----|
| Hard sciences | Low (0.0–0.2) | Citations closely track source claims; precision valued |
| Social sciences | Low–moderate (0.1–0.4) | Interpretive framing common but constrained |
| Humanities | Moderate (0.2–0.5) | Hermeneutic interpretation is normative |
| Legal scholarship | Variable (0.0–0.6) | Signal-dependent: "see" vs "cf." vs "but see" carry different expected strain |
| Journalism | Moderate (0.2–0.5) | Paraphrasing standard; context compression expected |
| AI-generated | Should be low (0.0–0.2) | Models should not editorialize on sources |

### 4.2 Legal Citation Signals as Strain Encoders

Legal citation practice (Bluebook conventions) already encodes expected
strain in the citation signal:

- **[no signal]** or **"see"**: Direct support. Expected strain: very low
- **"see also"**: Additional support. Expected strain: low–moderate
- **"see generally"**: Background support. Expected strain: moderate
  (source contextualizes rather than directly supports)
- **"cf."**: Analogous support. Expected strain: moderate–high
  (source supports by analogy, not directly)
- **"but see"**: Contrary authority. Expected strain: high by design
  (citation is intentionally adversarial to the claim)
- **"contra"**: Direct contradiction. Expected strain: maximum by design

This is a natural calibration corpus: legal scholarship with Bluebook
signals provides pre-labeled strain levels.

### 4.3 Calibration Strategy

1. **Collect discipline-specific corpora** of citations with known quality
   (peer-reviewed, retracted, disputed, etc.)
2. **Extract source passages and claiming contexts** using VCITE tooling
3. **Compute candidate strain scores** using multiple methods
4. **Regress against human judgments** or citation signal labels
5. **Fit discipline-specific calibration curves** that map raw scores
   to calibrated strain values

## 5. Computing Strain: A Hierarchy of Methods

### 5.1 Lexical Overlap (Baseline — No Dependencies)

The simplest strain measure: how much vocabulary is shared between the
source passage and the claiming context?

- **Jaccard similarity** of token sets
- **ROUGE-L** (longest common subsequence)
- **Weighted overlap** (IDF-weighted to emphasize informative terms)

Pros: No ML dependencies, fast, reproducible
Cons: Misses synonymy, paraphrase, semantic equivalence

### 5.2 N-gram Divergence

Compare n-gram distributions between source and claim:

- **KL divergence** or **Jensen-Shannon divergence** of bigram/trigram
  distributions
- Captures phrase-level rather than word-level similarity

### 5.3 Sentence Embeddings (Requires ML Models)

Embed source passage and claiming context into a shared semantic space:

- **SPECTER** (Cohan et al., 2020): trained specifically on scientific
  papers and citations
- **SciBERT** (Beltagy et al., 2019): pre-trained on scientific text
- **all-MiniLM-L6-v2** (Sentence-Transformers): general-purpose, fast
- **Instructor embeddings**: can be prompted for citation-specific similarity

Strain = 1 - cosine_similarity(embed(source), embed(claim))

Pros: Captures semantic similarity, handles paraphrase
Cons: Requires ML infrastructure, not reproducible across model versions

### 5.4 NLI-Based Entailment (Requires ML Models)

Use Natural Language Inference models to classify the relationship:

- Does the source passage **entail** the claim? (low strain)
- Is the source passage **neutral** to the claim? (moderate strain)
- Does the source passage **contradict** the claim? (high strain)

Models: DeBERTa-v3 (He et al., 2021), BART-MNLI, cross-encoder NLI

Strain can be derived from the probability distribution:
`strain = 1 - P(entailment) + α * P(contradiction)`

Pros: Directly tests semantic relationship, handles direction
Cons: NLI models have limited context windows, may not handle
domain-specific reasoning

### 5.5 LLM-Based Assessment (Most Expensive, Most Flexible)

Prompt a language model to assess citation faithfulness:

```
Given the cited passage: "{text_exact}"
And the claim made about it: "{claiming_context}"
Rate how faithfully the claim represents the source on a scale of 0-10.
Explain any distortions.
```

Pros: Handles nuance, can explain reasoning, discipline-aware
Cons: Expensive, non-deterministic, model-dependent

### 5.6 Recommended Approach: Ensemble with Calibration

No single method captures strain fully. The recommended approach:

1. Compute lexical overlap (baseline, always available)
2. If embeddings available, compute embedding distance
3. If NLI model available, compute entailment score
4. Combine via calibrated weighted average (weights learned from
   discipline-specific calibration corpus)

## 6. Data Model

Strain scores fit naturally in the VCITE `enrichment` field:

```json
{
  "enrichment": {
    "strain": {
      "local_score": 0.23,
      "method": "lexical+nli",
      "components": {
        "lexical_overlap": 0.85,
        "nli_entailment": 0.72,
        "nli_contradiction": 0.03
      },
      "discipline": "social_science",
      "calibrated": true,
      "claiming_context": "The tension between transparency and privacy...",
      "assessed_at": "2026-04-11T00:00:00Z"
    }
  }
}
```

Document-level (global) strain:

```json
{
  "strain_summary": {
    "global_score": 0.18,
    "consistency_score": 0.92,
    "citation_count": 20,
    "max_local_strain": 0.41,
    "strain_distribution": {
      "low": 15,
      "moderate": 4,
      "high": 1
    },
    "sheaf_obstructions": []
  }
}
```

## 7. Open Questions

1. **Ground truth**: What corpus of "known good" and "known bad" citations
   can we use for calibration? Retracted papers offer negative examples;
   systematic reviews offer positive examples.

2. **Directionality**: Should strain distinguish between overstating
   (source says less than claimed) and understating (source says more
   than claimed)? These have different epistemic implications.

3. **Context dependence**: The same text_exact might have low strain
   when cited in one context and high strain in another. Strain is a
   property of the citation act, not the passage alone.

4. **Temporal drift**: Sources don't change (especially with archive_url),
   but disciplinary consensus does. A citation that was low-strain in 2010
   might be high-strain by 2025 standards.

5. **Adversarial robustness**: Can authors game the strain score by
   carefully selecting passages that are technically present but
   misleading in context? (Yes — this is the "accurate but misleading"
   problem.)

## 8. Strain Decomposition

Drawing from the literature survey, strain decomposes into at least
four distinct dimensions:

1. **Fidelity strain**: Does the citation accurately represent the
   source's claims? (Chen et al., 2025)
2. **Completeness strain**: Does the citation omit critical qualifiers
   or context? (Martella et al., 2021 — found ~19% of citations to
   Freeman et al.'s active-learning meta-analysis misrepresented findings
   by attributing efficacy to activities the meta-analysis never evaluated)
3. **Directional strain**: Does the citation reverse the valence of the
   source? (Scite's supporting/contrasting classification)
4. **Contextual strain**: Is the citation used for a purpose the source
   doesn't support? (Jurgens et al., 2018 — citation frame analysis)

These dimensions are not independent. High completeness strain (dropping
a qualifier) often produces high directional strain (reversing valence).
The strain score should ideally capture all four, though the baseline
lexical scorer primarily measures fidelity.

## 9. The Telephone Effect and Strain Propagation

Chen, Teplitskiy & Jurgens (2025) — "The Noisy Path from Source to
Citation" (ACL 2025) — established the **telephone effect**: low-fidelity
citations propagate, causing downstream citations to have even lower
fidelity to the original source. Their analysis of ~13 million citation
pairs found:

- Fidelity is higher when citing more recent, intellectually proximate,
  and accessible papers
- Lower fidelity when first author has a higher H-index
- Strain compounds through citation chains: A cites B (low strain),
  C cites A's claim about B (higher strain), D cites C's claim about
  A's claim about B (highest strain)

This directly validates Greenberg's (2009) "amplification" mechanism
and has implications for the sheaf formalization: strain is not just
a local property of individual citations but a network property that
propagates along paths in the citation graph.

**Implication for VCITE**: The `text_exact` field in a VCITE citation
anchors to a specific passage, which prevents fidelity loss at the
first hop. But if downstream authors cite the VCITE-enhanced document
without propagating the VCITE anchors, the telephone effect resumes.
A strain-aware VCITE tool should flag citations of secondary sources
when the primary source is available.

## 10. Empirical Base Rates

Quotation error rates from systematic reviews establish the ground truth
that a strain metric should approximately reproduce:

| Discipline | Error Rate | Source |
|-----------|-----------|--------|
| General medicine | ~20% (range 0–50%) | Cochrane meta-analyses |
| Psychology | ~19% | Discipline-specific studies |
| General science | ~25% | Cross-disciplinary review |
| Ecology | ~11% | Field-specific audit |
| Education | ~26% | Martella et al. 2021 |
| Marine biology | ~10.6% | Field-specific audit |
| Physical geography | ~19% | Field-specific audit |

Wakeling et al. (2025) surveyed 2,648 authors evaluating real citations
of their own work: 16.6% quotation error rate with no significant
disciplinary differences. 24% said citations overgeneralized their work.
Only 11.3% ever took action when encountering inaccurate citations.

These rates establish calibration targets: a well-calibrated strain
metric should flag approximately 15–25% of citations as "high strain"
in a representative corpus.

## 11. Prior Art (Full Survey)

### Citation Fidelity Measurement (Most Relevant)
- **Chen, Teplitskiy & Jurgens (2025)**: "The Noisy Path from Source
  to Citation" (ACL 2025) — **closest existing work to citation strain**.
  Computational pipeline quantifying "citation fidelity" at scale across
  ~13M citation pairs. Established the telephone effect. Pipeline:
  citation context extraction → claim alignment → supervised fidelity
  scoring. Provides directly applicable architecture.
- **Sarol, Schneider & Kilicoglu (2024–2025)**: Automatic identification
  of citation distortions in biomedical literature. Annotated corpus of
  100 highly-cited biomedical papers. NLP models classify citations as
  ACCURATE, NOT_ACCURATE, or IRRELEVANT. Also tested LLMs (Gemini 1.5,
  GPT-4o, LLaMA-3.1) on a 3-step pipeline: extract, retrieve, verify.
  [GitHub](https://github.com/ScienceNLP-Lab/Citation-Integrity)
- **SemanticCite — Haan (2025)**: "Citation Verification with AI-Powered
  Full-Text Analysis" (arXiv). 4-class system: Supported, Partially
  Supported, Unsupported, Uncertain. Cross-disciplinary dataset of 1,000+
  citations across 8 disciplines. Hybrid retrieval (sparse + dense).
  [GitHub](https://github.com/sebhaan/semanticcite)

### Citation Intent Classification
- Jurgens et al. (2018): "Measuring the Evolution of a Scientific Field
  through Citation Frames" — 6 citation functions (Background, Motivation,
  Uses, Extension, Comparison/Contrast, Future). Largest behavioral
  citation study at time. Found citation framing evolves as fields mature.
- Cohan et al. (2019): "Structural Scaffolds for Citation Intent
  Classification" (NAACL) — SciCite dataset (11K+ annotations), multitask
  scaffolds using section structure. 13.3% F1 improvement.
- Lauscher et al. (2022): MultiCite — multi-label citation intent
- GraphCite (Balalau et al., 2022): GAT + SciBERT for graph-aware intent
- CitePrompt (Lahiri et al., 2023): prompt-based learning, SOTA on SciCite

### Citation Distortion
- **Greenberg (2009)**: "How citation distortions create unfounded
  authority" (BMJ) — foundational. Traced 242 papers, 675 citations,
  220K citation paths. Three mechanisms: citation bias (selective citing),
  amplification (citing reviews instead of primary data), invention
  (altering claims through citation). The telephone effect avant la lettre.
- Martella et al. (2021): "Quotation Accuracy Matters" (Review of
  Educational Research) — 19% of citations misrepresented findings
- Wakeling et al. (2025): "How Do Authors Perceive the Way Their Work
  Is Cited?" (JASIST) — 16.6% error rate from author surveys
- Bornmann & Leibel (2025): Framework distinguishing citation noise
  (stochastic) from citation bias (systematic directional error)
- De Lacey et al. (1985): early study of citation accuracy rates
- Mogull (2017): citation error and distortion in pharmacy literature

### Smart Citation Classification
- Nicholson et al. (2021): "scite: A smart citation index" (QSS) —
  production-scale (880M+ classified statements). 92.6% Mentioning,
  6.5% Supporting, 0.8% Contrasting. Coarse but scalable.

### Semantic Similarity for Scientific Text
- **SPECTER (Cohan et al., 2020)**: citation-informed document embeddings.
  Papers close in citation graph → close in embedding space. Useful for
  "topical distance" component of strain.
- SPECTER2 (Singh et al., 2023): 6M triplets, task-specific adapters.
  A "strain adapter" could be trained for fidelity assessment.
- SciBERT (Beltagy et al., 2019): domain-adapted BERT for science
- SciNCL (Ostendorff et al., 2022): improved scientific embeddings

### Sheaf Theory in Data Science
- **Robinson (2014)**: "Topological Signal Processing" — foundational
  sheaf framework for data consistency
- **Robinson (2017)**: "Sheaves are the canonical data structure for
  sensor integration" — introduced consistency radius and consistency
  filtration. The consistency radius IS a strain metric for sensor
  networks; directly applicable to citations as "sensors" reporting
  on source papers.
- **Hansen & Ghrist (2021)**: "Opinion Dynamics on Discourse Sheaves"
  (SIAM J. Appl. Math.) — sheaf Laplacian measures "discord" in
  opinion networks. Directly applicable: replace agents with papers,
  opinions with claims about sources. Strain = norm of sheaf coboundary.
- Bodnar et al. (2022): "Neural Sheaf Diffusion" (NeurIPS) — sheaves
  can be learned from data, not just specified. A citation strain sheaf
  could be learned end-to-end from annotated data.
- Curry (2014): "Sheaves, Cosheaves and Applications" — computational
  sheaf theory

### Fact Verification via NLI
- Thorne et al. (2018): FEVER — 185K claims, 3-class verification
- **Wadden et al. (2020)**: SciFact — 1,409 scientific claims paired with
  5,183 abstracts. 3-step pipeline: retrieve, select rationale, classify
  entailment. Architecture directly transferable to strain.
- Wadden et al. (2022): MultiVerS — full-document context via Longformer,
  0.72 F1 on SciFact
- Schuster et al. (2021): evidence-based fact checking

### Legal Citation Analysis
- Spriggs & Hansford (2000): citation practice in Supreme Court opinions
- Shapiro (1992): "Origins of the Serial Citation" — evolution of
  legal citation signals and their semantic functions

## 12. Recommended Architecture (Informed by Survey)

Based on the literature, the most promising strain architecture combines:

1. **Citation context extraction** (existing VCITE tooling)
2. **Evidence retrieval from source** (full-text, not just abstract —
   following MultiVerS and SemanticCite)
3. **NLI-based entailment classification** (SciFact pipeline)
4. **Continuous score mapping** (going beyond 3–4 class systems)
5. **Sheaf-theoretic aggregation** (consistency radius from Robinson 2017,
   discourse sheaf dynamics from Hansen & Ghrist 2021)
6. **Discipline calibration** (Bluebook signals for legal, error rate
   base rates for sciences, author survey data from Wakeling et al.)

The Chen et al. (2025) pipeline (citation context → claim alignment →
supervised fidelity scoring) provides the most directly applicable
end-to-end architecture. Their "fidelity" is our inverse-strain.
