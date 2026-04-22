---
title: "VCITE: Verified Citation with Inline Text Evidence"
version: "0.1"
date: 2026-03-30
status: "0.1-STABLE — hash algorithm and core data model frozen; serializations and governance still draft. Safe to cite and implement against."
stable_since: 2026-04-22
author: Chris Graziul, Illinois Data Equity Project (IDEP)
license: CC-BY 4.0 — free to implement, extend, and cite
---

# VCITE

**Verified Citation with Inline Text Evidence**

Specification -- Working Draft 0.1 | 30 March 2026

---

## Abstract

VCITE (Verified Citation with Inline Text Evidence) is an open, format-agnostic specification for embedding author-asserted, cryptographically verifiable passage citations directly in text documents. Unlike existing citation systems, which provide document-level links, retroactive extraction, or centralized verification services, VCITE enables any author in any medium -- academic paper, news article, HTML page, or AI-generated output -- to embed the exact passage they are citing alongside a SHA-256 fingerprint of that passage and a pointer to a durable archive. The standard is not a citation style (like APA or Chicago) nor a discovery service (like Scite or Semantic Scholar). It is an evidence layer that can sit beneath any citation style and integrate with any discovery service. Third-party enrichment services such as Scite.ai Smart Citations, Perma.cc archiving, and W3C Text Fragment deep-linking are supported as optional integration layers. None are required for conformance.

---

## 1. Problem Statement

### 1.1 The Verification Gap

Citation has always had two jobs: attribution and verifiability. Contemporary infrastructure handles attribution reasonably well. It handles verifiability poorly, and the problem is accelerating along three independent axes.

**First, link rot.** Over 70% of URLs cited in major law review articles fail within years of publication. The Internet Archive and Perma.cc address this at the document level, but neither preserves the specific passage a citation was meant to support. A reader following a Perma.cc link must still find the relevant passage themselves.

**Second, AI hallucination.** Language models fabricate citations at rates between 18% and 55% depending on model and task. Current verification tools (Veru, SwanRef, CheckIfExist) check whether a cited document exists -- they do not confirm that the document says what the author claims. A real paper with a fabricated claim is harder to catch than a fully invented citation.

**Third, medium fragmentation.** Scite.ai's Smart Citations solve the verification display problem for academic literature with DOIs. Nothing analogous exists for journalism, government reports, web content, grey literature, or AI outputs -- the majority of text produced and cited in practice.

### 1.2 What Existing Solutions Miss

The table below maps existing tools to the capabilities they provide. Every empty cell represents a gap VCITE is designed to fill.

| System | Passage-level | Embedded in doc | Hash verify | Offline fallback | Non-academic | Open std |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|
| Text Fragments | Y | -- | -- | -- | Y | ~\* |
| W3C Annotation | Y | -- | -- | -- | Y | Y |
| Perma.cc | -- | -- | -- | Y | Y | -- |
| Scite.ai | Y | -- | -- | -- | -- | -- |
| APA / Chicago | -- | -- | -- | -- | Y | Y |
| **VCITE (this spec)** | **Y** | **Y** | **Y** | **Y** | **Y** | **Y** |

\* Text Fragments are an open WICG draft with incomplete cross-browser support and no enforcement mechanism.

---

## 2. Design Principles

**P1 -- Author-asserted.** The citation object is created by the author at the time of writing, not extracted post-hoc by a third-party service. This is the central epistemic difference from Scite, Semantic Scholar, and similar tools: VCITE makes the author's specific evidentiary claim machine-readable and auditable.

**P2 -- Passage-specific.** Every VCITE object MUST identify a specific span of text in the source, not merely the source document. Citing a whole paper, article, or URL without anchoring to a passage is not conformant at L2 or above.

**P3 -- Cryptographically verifiable.** A SHA-256 hash of the cited passage (plus fixed context window) allows any reader to independently confirm that the embedded snippet matches the source -- without network access, without trusting the author, and without any central service.

**P4 -- Service-independent.** No third-party service (archive, index, identifier registry) is required for a conformant Level 1 or Level 2 citation object. Services like Scite.ai, Perma.cc, and DOI resolvers are optional enrichment layers. The standard degrades gracefully when any or all of them are unavailable.

**P5 -- Format-portable.** The data model is format-agnostic. Serializations are defined for HTML (data attributes + JSON-LD), Markdown (extended attribute syntax), LaTeX (custom macro), and plain text (structured comment). The same citation object, differently serialized, is semantically identical.

**P6 -- Composable with existing infrastructure.** VCITE extends the W3C Web Annotation TextQuoteSelector vocabulary. It is compatible with DOI metadata, Scite citation statements, Perma.cc WACZ archives, and OpenURL resolution. Implementers adopting VCITE do not abandon prior toolchains.

---

## 3. Terminology

| Term | Definition |
|------|------------|
| **citation object** | A structured data object conforming to this specification that encodes a specific passage-level evidentiary claim. |
| **passage** | A contiguous span of text in a source document that the author asserts as evidence for a claim. |
| **passage fingerprint** | A SHA-256 hash computed over the normalized passage string, as defined in Section 5. |
| **context window** | The 50 Unicode code points immediately preceding and following the passage, used as disambiguation context in the hash input. |
| **text fragment URL** | A URL using the WICG Text Fragment specification (`#:~:text=...`) that deep-links directly to the passage in the source document. |
| **archive** | A durable, timestamped copy of the source document at a stable URL. Perma.cc WACZ format is the reference implementation; self-hosted WACZ archives are also conformant. |
| **enrichment** | Optional third-party data appended to a citation object at render time, such as Scite.ai citation tallies, CrossRef metadata, or Retraction Watch flags. Enrichment does not affect conformance. |
| **relation** | The author's characterization of how the cited passage relates to the claim being made. Values defined in Section 4.4. |
| **REQUIRED / OPTIONAL** | When capitalized, these terms carry the normative meanings defined in RFC 2119. |

---

## 4. Data Model

### 4.1 Top-Level Structure

A VCITE citation object is a JSON object. When embedded in other formats, it is serialized as defined in Section 6. The top-level fields are:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `vcite` | string | REQUIRED | Specification version. Currently `"1.0"`. Implementations MUST reject objects with unrecognized versions. |
| `id` | string | REQUIRED | Locally unique identifier for this citation, scoped to the document. Recommended format: `"vcite-"` + first 8 hex chars of hash. |
| `source` | object | REQUIRED | Bibliographic metadata for the source document. See Section 4.2. |
| `target` | object | REQUIRED | Passage location and verification data. See Section 4.3. |
| `relation` | string | REQUIRED | How the cited passage relates to the claim. Controlled vocabulary defined in Section 4.4. |
| `captured_at` | string | REQUIRED | ISO 8601 datetime when the citation object was created. Used to resolve hash mismatches against archived versions. |
| `captured_by` | string | OPTIONAL | Who or what generated the citation. Values: `"author"` \| `"tool"` \| `"model"`. Supports attribution transparency for AI-generated citations. |
| `enrichment` | object | OPTIONAL | Third-party enrichment data. See Section 7. MUST NOT affect conformance determination. |

### 4.2 Source Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | REQUIRED | Full title of the source document. |
| `authors` | array | OPTIONAL | List of author name strings. OPTIONAL to accommodate institutional, anonymous, or AI-generated sources. |
| `year` | integer | OPTIONAL | Year of publication or first public availability. |
| `doi` | string | OPTIONAL | Digital Object Identifier without `"https://doi.org/"` prefix. Include when available. |
| `isbn` | string | OPTIONAL | ISBN-13 for book sources. |
| `url` | string | OPTIONAL | Canonical URL of the source at time of capture. At least one of `doi`, `isbn`, or `url` MUST be present at L2+. |
| `venue` | string | OPTIONAL | Journal name, publisher, news outlet, or platform. |
| `archive_url` | string | OPTIONAL | Stable archive URL (Perma.cc or self-hosted WACZ). Strongly RECOMMENDED for web sources. |
| `source_type` | string | OPTIONAL | Classification of source kind. Controlled values: `"academic"` \| `"journalism"` \| `"government"` \| `"web"` \| `"ai_output"` \| `"other"`. |

### 4.3 Target Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text_exact` | string | REQUIRED | The verbatim passage being cited. Maximum 1,000 UTF-8 characters. If the passage exceeds this limit, use the first 500 and last 500 characters with `"..."` as separator; the hash is computed over the full text. |
| `hash` | string | REQUIRED | Passage fingerprint. Format: `"sha256:"` + hex digest. Computed as defined in Section 5. |
| `text_before` | string | REQUIRED (L2+) | Up to 50 Unicode code points immediately preceding `text_exact` in the source. Used for disambiguation and as part of hash input. |
| `text_after` | string | REQUIRED (L2+) | Up to 50 Unicode code points immediately following `text_exact` in the source. Used for disambiguation and as part of hash input. |
| `char_start` | integer | OPTIONAL | Zero-indexed UTF-8 character offset of the start of `text_exact` within the source document's plain-text rendering. |
| `char_end` | integer | OPTIONAL | Zero-indexed UTF-8 character offset of the end of `text_exact` (exclusive). |
| `page_ref` | string | OPTIONAL | Human-readable page or location reference (e.g., `"p. 47"`, `"S 3.2"`, `"slide 12"`). |
| `section` | string | OPTIONAL | Section heading or structural location in the source document. |
| `fragment_url` | string | OPTIONAL | Text Fragment URL (`#:~:text=`) that deep-links to the passage. Strongly RECOMMENDED for web sources. |

### 4.4 Relation Vocabulary

The `relation` field takes one of the following values. Implementations MUST reject objects with values outside this set unless prefixed with `"x-"` (extension namespace).

| Value | Meaning |
|-------|---------|
| `"supports"` | The cited passage provides direct evidence for the claim being made. The reader should be able to read the passage and conclude the claim is substantiated. |
| `"contradicts"` | The cited passage is presented as evidence against the claim, or as a counterposition the author is engaging with. Use when citing opposing evidence. |
| `"defines"` | The cited passage provides a definition, taxonomy, or conceptual framework the author is adopting or invoking. Not an empirical support claim. |
| `"quantifies"` | The cited passage contains specific numerical data, statistics, or measurements the author is relying on. Subset of `"supports"` but machine-distinguishable. |
| `"contextualizes"` | The cited passage provides background, historical context, or framing that motivates the current work without directly supporting or contradicting a specific claim. |
| `"method"` | The cited passage describes a methodology, instrument, or procedure the author is replicating, adapting, or critiquing. |
| `"cautions"` | The cited passage identifies a limitation, caveat, or condition that qualifies the claim being made. |

The extension namespace `"x-"` is reserved for domain-specific values not covered above. Extensions MUST be documented and SHOULD be proposed for inclusion in future versions of this specification. Example: `"x-legal:exhibit"` for legal citation practice.

---

## 5. Hash Algorithm

### 5.1 Algorithm Definition

The passage fingerprint is computed as follows. Implementations MUST follow this procedure exactly to produce interoperable hashes.

1. **Construct the input string** by concatenating:
   - (a) `text_before`, truncated or padded to exactly 50 Unicode code points with trailing space-padding if shorter;
   - (b) the pipe character `|` as a delimiter;
   - (c) `text_exact`, the full verbatim passage;
   - (d) the pipe character `|` as a delimiter;
   - (e) `text_after`, truncated or padded to exactly 50 Unicode code points with trailing space-padding if shorter.
2. **Normalize the input string:**
   - (a) apply Unicode NFC normalization;
   - (b) collapse all runs of whitespace characters (U+0009, U+000A, U+000D, U+0020) to a single U+0020 space;
   - (c) strip leading and trailing whitespace from each of the three segments (`text_before`, `text_exact`, `text_after`) before padding.
3. **Encode** the normalized input string as UTF-8 bytes.
4. **Compute** the SHA-256 digest of the byte sequence.
5. **Encode** the digest as a lowercase hexadecimal string.
6. **Prepend** the string `"sha256:"` to produce the final `hash` field value.

> **Clarification (v0.1.1):** "50 UTF-8 characters" in the original draft should read "50 Unicode code points." For CJK text, 50 code points may be up to 150 UTF-8 bytes. Implementations MUST count code points, not bytes. The reference implementation (Section 5.2) uses Python's `list(s)`, which iterates over code points.

> **Clarification (v0.1.1):** Non-breaking space (U+00A0) is intentionally NOT collapsed by the whitespace normalization regex `[\t\n\r ]+`. The regex targets only U+0009 (tab), U+000A (line feed), U+000D (carriage return), and U+0020 (space). Implementers MUST NOT treat U+00A0 as equivalent to U+0020.

> **Clarification (v0.1.1):** The pipe character `|` is used as a delimiter in the hash input but is NOT escaped in `text_exact` or context fields. The fixed-length context windows (always exactly 50 code points after padding) make the raw string `before|exact|after` unambiguously parseable -- the first `|` always occurs at position 50, and the last `|` always occurs at position `len(input) - 50 - 1` (counting from the end, before the 50-code-point `text_after` segment).

### 5.2 Reference Implementation (Python)

```python
import hashlib
import unicodedata
import re

CONTEXT_LEN = 50  # Unicode code points

def normalize_segment(s: str) -> str:
    """NFC normalize and collapse whitespace."""
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"[\t\n\r ]+", " ", s)
    return s.strip()

def pad_context(s: str, length: int = CONTEXT_LEN) -> str:
    """Truncate or space-pad to exactly `length` code points."""
    chars = list(s)  # preserves multi-byte chars as single units
    if len(chars) >= length:
        return "".join(chars[:length])
    return "".join(chars) + " " * (length - len(chars))

def compute_hash(
    text_exact: str,
    text_before: str = "",
    text_after: str = "",
) -> str:
    """Return the VCITE passage fingerprint for a cited passage."""
    before = pad_context(normalize_segment(text_before))
    exact  = normalize_segment(text_exact)
    after  = pad_context(normalize_segment(text_after))
    raw    = f"{before}|{exact}|{after}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
```

### 5.3 Test Vectors

The following test vectors MUST be reproduced exactly by conforming implementations. An implementation that produces a different hash for any vector is non-conformant.

| # | `text_before` | `text_exact` | `text_after` | Expected hash |
|---|---------------|--------------|--------------|---------------|
| SV1 | `"The rate is "` | `"exactly 42%"` | `" as measured"` | `sha256:f2d30080cf6f2dd31c4e160673b427742c132bd7fe6b014e0b5026daea80bbf5` |
| SV2 | `"café au lait "` | `"résumé complet"` | `" du rapport"` | `sha256:c9ac6f27318e7f3a7d27b85a9823ac7644e6a02d2f58c2abd1801ae99a9a53e4` |
| SV3 | `"  multiple   "` | `"  spaces  here  "` | `"  trimmed  "` | `sha256:ad4c8f44cc63c1d34451eab399094657961632d044a29c9c852d2bac064f3948` |
| SV4 | (empty) | `"Only exact, no context"` | (empty) | `sha256:d8ea2d1c308a3d38328362479c1a97dbdf5a9a87ca64a6a4b3fdd430853edd8b` |

**SV1** tests basic ASCII input with short context windows (space-padded to 50 code points).
**SV2** tests Unicode NFC normalization with accented characters.
**SV3** tests whitespace collapse and stripping -- multiple spaces and tabs reduce to single spaces, then leading/trailing whitespace is stripped before padding.
**SV4** tests the minimal L1 case: no context at all. Both context windows are 50 spaces.

---

## 6. Serialization Formats

### 6.1 HTML / JSON-LD

In HTML documents, a VCITE citation is represented as an inline element carrying a data attribute that points to a JSON-LD block in the document head. This approach preserves separation between content and metadata, is compatible with existing structured data tooling, and degrades gracefully in browsers without VCITE-aware rendering.

**Inline mark (in body):**

```html
<span data-vcite="vcite-a3f8c2d1"
      class="vcite-mark">
  the exact cited text visible to the reader
</span>
<sup data-vcite-ref="vcite-a3f8c2d1" class="vcite-badge">1</sup>
```

**JSON-LD block (in document `<head>`):**

```json
{
  "@context": "https://vcite.pub/ns/v1/",
  "@type": "VCiteObject",
  "vcite": "1.0",
  "id": "vcite-a3f8c2d1",
  "source": { "title": "...", "doi": "..." },
  "target": {
    "text_before": "...",
    "text_exact": "...",
    "text_after": "...",
    "hash": "sha256:a3f8c2d1...",
    "fragment_url": "https://source.com/paper#:~:text=..."
  },
  "relation": "supports",
  "captured_at": "2026-03-30T12:00:00Z"
}
```

The JSON-LD block is wrapped in a `<script type="application/ld+json">` tag in the document `<head>`.

### 6.2 Markdown (Pandoc Extended Syntax)

VCITE citations in Markdown use Pandoc's generic attribute syntax. This preserves readability in plain text while enabling extraction by Markdown processors.

```markdown
The study found [significant effects]{.vcite
  vcite-id="vcite-a3f8c2d1"
  vcite-hash="sha256:a3f8c2d1..."
  vcite-exact="significant effects on cognitive load"
  vcite-before="Authors reported "
  vcite-after=" across all conditions"
  vcite-source-doi="10.xxxx/xxxxx"
  vcite-relation="supports"
  vcite-captured="2026-03-30"
}.
```

A Pandoc Lua filter (reference implementation provided separately) extracts `vcite-*` attributes and generates the corresponding JSON-LD in HTML output.

### 6.3 LaTeX

The `\vcite{}` macro provides academic authors with a citation command that embeds passage evidence in the PDF's XMP metadata while rendering a conventional citation marker in the text.

```latex
\usepackage{vcite}

% In body:
\vcite[
  id={vcite-a3f8c2d1},
  exact={the verbatim cited passage},
  before={preceding context},
  after={following context},
  hash={sha256:a3f8c2d1...},
  doi={10.xxxx/xxxxx},
  relation={supports},
  captured={2026-03-30}
]{AuthorYear}
```

The package renders as a standard `\cite{}` call. In PDF output, the VCITE JSON is embedded in the document's XMP metadata block, accessible to citation managers and verification tools without affecting document appearance.

### 6.4 Plain Text / AI Output

For contexts where markup is unavailable -- plain-text AI outputs, email, SMS, terminal output -- VCITE uses a compact inline notation:

```text
The cited text in context [[vcite:a3f8c2d1|sha256:a3f8c2d1...|
https://source.com/paper#:~:text=cited+text|supports]] continuation.
```

The bracket notation encodes: `[[vcite: id | hash | fragment_url_or_archive_url | relation]]`. A minimal L1 object omits the `fragment_url` field. Parsers MUST treat the plain-text form as informational only; the canonical object is the JSON form.

---

## 7. Integration Protocol

Enrichment services MAY append data to a VCITE object at render time. Enrichment MUST be placed in the `enrichment` object and MUST NOT modify any existing field. A renderer receiving an enriched object MUST be able to strip the `enrichment` field and recover a fully conformant citation object.

### 7.1 Scite.ai Smart Citations

When `source.doi` is present, a conforming renderer MAY query the Scite API at `api.scite.ai` to retrieve citation tallies and citation statements for the cited paper. The Scite response is embedded under `enrichment.scite`:

```json
{
  "enrichment": {
    "scite": {
      "supporting": 214,
      "contrasting": 12,
      "mentioning": 891,
      "statements": [
        {
          "text": "..citing paper excerpt..",
          "classification": "supporting",
          "citing_paper": "Author et al. (2023), Journal"
        }
      ],
      "fetched_at": "2026-03-30T12:00:00Z"
    }
  }
}
```

Scite data is not available for non-academic sources (journalism, web, AI output). Renderers MUST display a clear explanation of why Scite data is absent, not an empty panel. Recommended message: *"Scite indexes peer-reviewed academic literature. This source ([source_type]) is outside Scite's coverage."*

### 7.2 Perma.cc Archiving

Authors SHOULD generate a Perma.cc link at citation time and store it in `source.archive_url`. The Perma.cc API accepts a URL and returns a stable permalink. Self-hosted WACZ archives (using the Webrecorder toolchain) are also conformant and preferred for organizational independence.

### 7.3 Text Fragment Deep-Linking

When `target.fragment_url` is present, renderers SHOULD use it as the primary "open source" action. The `fragment_url` uses the WICG Text Fragment specification and is currently supported in Chrome, Edge, Safari, and Firefox. Renderers targeting environments without text fragment support SHOULD fall back to `source.url` or `source.archive_url`.

### 7.4 DOI Resolution and CrossRef

When `source.doi` is present, renderers MAY enrich source metadata via the CrossRef API (`api.crossref.org/works/{doi}`) to retrieve structured bibliographic data including publisher, volume, issue, page range, and retraction status. CrossRef data MUST be placed in `enrichment.crossref`.

---

## 8. Conformance Levels

VCITE defines three conformance levels to accommodate the range of authoring contexts from minimal (offline, LaTeX) to fully-enriched (web, academic publishing). A higher level subsumes all requirements of lower levels.

| Level | Required fields | Optional fields | Suitable for |
|-------|-----------------|-----------------|--------------|
| **L1 -- Minimal** | `text_exact`, `hash`, `source.title` | All others | Offline documents, LaTeX, plain text |
| **L2 -- Standard** | L1 + `text_before`, `text_after`, `source.url` or `source.doi`, `captured_at` | scite, archive, fragment_url | HTML articles, Markdown, journalism |
| **L3 -- Enhanced** | L2 + `fragment_url`, `archive_url`, `char_start`, `char_end` | scite enrichment | Academic publishing, AI output, legal |

A citation object claims a conformance level by including all REQUIRED fields for that level. Objects that include fields from higher levels without meeting all requirements of that level are not conformant at the higher level but MUST be processed by renderers as conformant at the highest level whose requirements they do meet.

---

## Stability & compatibility commitments

As of `stable_since: 2026-04-22`, VCITE 0.1 is declared **0.1-STABLE**. The
items below are FROZEN within the 0.x line. Conforming implementations and
downstream adopters MAY rely on them without fear of silent breakage. Items
marked **open for change** may still evolve in response to community feedback
before 1.0.

### FROZEN

- **Hash algorithm (§5.2).** The normalization procedure, input construction
  (`padded_before | text_exact | padded_after`), 50-code-point context window,
  NFC normalization, whitespace-collapse regex `[\t\n\r ]+`, SHA-256 digest,
  and `sha256:` prefix are FROZEN. Any change MUST increment the SemVer major
  version. To preserve backward compatibility, citation objects produced under
  a prior hash algorithm MUST continue to verify against the rules that were
  current at their `captured_at` timestamp; a future version MAY only change
  the rules applied to newly minted objects.
- **Core data model (§4).** The field names, types, required/optional status,
  and semantics of `VCiteCitation`, `VCiteSource`, and `VCiteTarget` — as
  defined in §4.1, §4.2, and §4.3 — are FROZEN at the field level. No field
  MAY be removed, renamed, retyped, or have its semantics altered within the
  0.x line. Additive changes (new OPTIONAL fields) are permitted and MUST
  default to omitted in all serializations so that consumers unaware of the
  new field remain conformant.
- **Relation vocabulary (§4.4).** The base seven values — `supports`,
  `contradicts`, `defines`, `quantifies`, `contextualizes`, `method`,
  `cautions` — are FROZEN in both membership and meaning. The `x-*`
  extension namespace remains open; new base values MUST NOT be introduced
  outside the `x-*` namespace until 1.0.
- **Conformance levels (§8).** The L1, L2, and L3 definitions and their
  required-field sets are FROZEN. An object that conforms to Lₙ under 0.1
  MUST continue to conform to Lₙ under all 0.x releases.
- **`captured_by` enumeration (§4.1).** The allowed values are FROZEN at
  `"author"`, `"tool"`, and `"model"`. Implementations MUST reject other
  values.
- **Test vectors (§5.3).** The four mandatory test vectors SV1–SV4 are
  FROZEN. Their inputs and expected hashes MUST NOT change within the 0.x
  line. Additional vectors MAY be added.

### Open for change (may evolve before 1.0)

- The JSON-LD context URL is `https://vcite.pub/ns/v1/` pending domain
  registration; the concrete URL MAY change, but the property names it maps
  MUST continue to align with §4.
- Optional serialization formats for Markdown (§6.2), LaTeX (§6.3), and
  plain text / AI output (§6.4) remain DRAFT and MAY evolve in response to
  implementer feedback. The canonical JSON form (§4) is stable.
- Enrichment field conventions (§7) remain open for new integration layers.
- The governance model (§9) may shift to a W3C Community Group or
  independent foundation before 1.0.

### Process for FROZEN changes

Any change to a FROZEN item constitutes a breaking change and MUST:

1. Increment the SemVer major version (i.e., be part of a 1.0 or later
   release).
2. Publish a migration path describing how existing objects are to be
   re-verified or re-serialized.
3. Be reflected by an update to `test-suite/vectors.yaml` with new vectors
   covering the change, without removing or altering existing mandatory
   vectors (the old vectors document the prior major version).

---

## 9. Governance and Openness

VCITE is an open specification published under the Creative Commons Attribution 4.0 International license. Any party may implement, extend, and redistribute conforming implementations without restriction.

**Namespace.** The canonical namespace is `https://vcite.pub/ns/v1/` (domain registration pending). The JSON-LD context file, schema definitions, and test vectors will be published at this URL.

**Versioning.** The specification uses semantic versioning. Breaking changes to the data model increment the major version. The `vcite` field in every citation object identifies the version it conforms to. Renderers MUST reject objects with unrecognized major versions and SHOULD warn on unknown minor versions.

**Extension registry.** Domain-specific relation values prefixed `"x-"` SHOULD be registered in the public extension registry at `https://vcite.pub/ns/v1/extensions`. Registration is open and requires only documentation of the value's meaning and at least one conforming implementation.

**Standards track.** VCITE is designed for submission to the W3C Web Annotation Working Group as a profile of the Web Annotation Data Model, specifically extending the TextQuoteSelector vocabulary with hash verification and archiving fields. Submission is planned as a W3C Community Group proposal following the first stable (1.0) release.

**Stewardship.** The specification is stewarded by the Illinois Data Equity Project (IDEP). Community input is accepted through the GitHub issue tracker at the vcite repository. A W3C Community Group submission is planned at v1.0 to formalize open governance and broaden stewardship beyond a single institution. If adoption warrants it, transition to an independent foundation will be considered post-v1.0.

---

## Appendix A: Complete Example Objects

### A.1 Academic Source (L3 Conformant, with Scite Enrichment)

```json
{
  "vcite": "1.0",
  "id": "vcite-a3f8c2d1",
  "source": {
    "title": "Perma: Scoping and Addressing the Problem of Link Rot",
    "authors": ["Zittrain, Jonathan", "Albert, Kendra", "Lessig, Lawrence"],
    "year": 2014,
    "doi": "10.2139/ssrn.2329161",
    "venue": "Harvard Law Review Forum",
    "archive_url": "https://perma.cc/XR4K-2329",
    "source_type": "academic"
  },
  "target": {
    "text_before": "As documented by Zittrain et al., ",
    "text_exact": "over 70% of the URLs provided in articles published in the Harvard Law Review did not lead to originally cited information",
    "text_after": ". This rate of decay accelerates",
    "hash": "sha256:d2ba5887d4456199ce37a7860ce011485519925dc75c3564f50d1ffa1e1dc933",
    "char_start": 1204,
    "char_end": 1441,
    "page_ref": "p. 4",
    "section": "S 2. Scope of the Problem",
    "fragment_url": "https://papers.ssrn.com/...#:~:text=over+70%25"
  },
  "relation": "supports",
  "captured_at": "2026-03-30T12:00:00Z",
  "captured_by": "author",
  "enrichment": {
    "scite": {
      "supporting": 214,
      "contrasting": 12,
      "mentioning": 891,
      "fetched_at": "2026-03-30T12:00:00Z"
    }
  }
}
```

### A.2 Journalism Source (L2 Conformant, no DOI)

```json
{
  "vcite": "1.0",
  "id": "vcite-c7e3a9f5",
  "source": {
    "title": "AI search engines gave incorrect answers to 60%+ of queries",
    "authors": ["Tow Center for Digital Journalism"],
    "year": 2025,
    "url": "https://www.cjr.org/tow_center/ai-search-audit",
    "venue": "Columbia Journalism Review",
    "archive_url": "https://perma.cc/YT2M-CJR2",
    "source_type": "journalism"
  },
  "target": {
    "text_before": "The CJR found that ",
    "text_exact": "eight major AI search tools provided incorrect or inaccurate answers to more than 60% of 1,600 test queries",
    "text_after": ", with error rates ranging",
    "hash": "sha256:26c71181069e54c4d776f2a03de838c81aab3eff1a64a71ecde920f629367707",
    "section": "Findings: Error rates by platform",
    "fragment_url": "https://cjr.org/tow_center/...#:~:text=60%25"
  },
  "relation": "quantifies",
  "captured_at": "2026-03-30T12:00:00Z",
  "captured_by": "author"
}
```

### A.3 Plain Text / AI Output (L1 Conformant)

```text
AI-generated text often cannot be verified or retrieved by
anyone other than the original author
[[vcite:f1d2e8b3|sha256:b8ba02cbee19230434c6a5b1431c0f8bfab8e00eb13b670875faa874959fb298|
https://guides.nyu.edu/citations#:~:text=cannot+be+verified|
contextualizes]].
```

---

## Appendix B: Open Questions for Comment

The following questions are open for community comment and will be resolved before v1.0 is declared stable.

**B1 -- Context window size.** Is 50 Unicode code points the right context window for disambiguation? Shorter windows risk collisions in repetitive text; longer windows increase brittleness when sources are lightly edited. Should the context window be configurable per `source_type`?

**B2 -- Non-text sources.** How should VCITE handle sources that are not plain text: scanned PDFs (where char offsets are meaningless), audio/video (where time offsets are more natural), data tables (where cell coordinates are more natural), or images? Should a `media_type` field determine which target fields are applicable?

**B3 -- Relation vocabulary completeness.** The seven relation values proposed in Section 4.4 were designed for general-purpose use. Are they sufficient for legal citation practice (which has its own citation function vocabulary, e.g., "cf.", "see generally", "but see")? Should a legal extension be defined in v1.0 or deferred?

**B4 -- Copyright and fair use.** Embedding `text_exact` in a citation object creates a permanent copy of up to 1,000 characters of potentially copyrighted text. The 50-code-point context window fields add another 100 characters. Does this fall within fair use / fair dealing in all target jurisdictions? Should the spec recommend a maximum `text_exact` length shorter than 1,000 characters for non-academic sources?

**B5 -- AI model citation.** When an AI model generates a VCITE object (`captured_by: "model"`), how should verifiers treat the hash? The model may have accessed a version of the source different from the current live version. Should model-generated VCITE objects be required to include `archive_url`, making L3 effectively mandatory for AI outputs?

**B6 -- Governance structure.** Should v1.0 be stewarded by IDEP, a W3C Community Group, or a new independent foundation? What are the implications for long-term maintenance, extension registry management, and standards-track submission?
