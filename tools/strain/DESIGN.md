# Citation Strain: Design & Research Exploration

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

## 8. Prior Art

### Citation Intent Classification
- Jurgens et al. (2018): "Measuring the Evolution of a Scientific Field
  through Citation Frames" — 6 citation functions
- Cohan et al. (2019): "Structural Scaffolds for Citation Intent
  Classification in Scientific Publications" — Background, Method,
  Result Comparison
- Lauscher et al. (2022): MultiCite — multi-label citation intent

### Citation Distortion
- Greenberg (2009): "How citation distortions create unfounded authority"
  — measured claim mutation across citation chains in medical literature
- De Lacey et al. (1985): early study of citation accuracy rates
- Mogull (2017): citation error and distortion in pharmacy literature

### Semantic Similarity for Scientific Text
- SPECTER (Cohan et al., 2020): citation-informed document embeddings
- SciNCL (Ostendorff et al., 2022): improved scientific embeddings
- SciBERT (Beltagy et al., 2019): domain-adapted BERT for science

### Sheaf Theory in Data Science
- Robinson (2014): "Topological Signal Processing" — sheaf-theoretic
  framework for data integration and consistency
- Robinson (2017): "Sheaves are the canonical data structure for sensor
  integration" — formalization relevant to citation network analysis
- Curry (2014): "Sheaves, Cosheaves and Applications" — computational
  sheaf theory

### Fact Verification via NLI
- Thorne et al. (2018): FEVER — fact extraction and verification dataset
- Wadden et al. (2020): SciFact — scientific claim verification
- Schuster et al. (2021): evidence-based fact checking

### Legal Citation Analysis
- Spriggs & Hansford (2000): citation practice in Supreme Court opinions
- Shapiro (1992): "Origins of the Serial Citation" — evolution of
  legal citation signals and their semantic functions
