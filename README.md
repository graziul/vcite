# VCITE — Verified Citation with Inline Text Evidence

> An open specification for embedding passage-level, cryptographically
> verifiable citations in any document format.

**Version**: 0.1.0 (Draft)
**Author**: Chris Graziul, Illinois Data Equity Project (IDEP)
**License**: CC-BY 4.0 (specification) / MIT (implementations)
**Spec**: [SPEC.md](SPEC.md) | **Schema**: [JSON Schema](schema/vcite.schema.json)

---

## The problem

Citations provide attribution but not verifiability. A reader who encounters
"(Smith, 2020, p. 14)" must locate the document, find the page, and confirm
the passage actually says what the citing author claims. Over 70% of URLs in
major law review articles fail within years of publication. Language models
fabricate citations at rates between 18% and 55%. Existing verification tools
check whether a cited document *exists* — they do not confirm that it says
what the author claims.

## What VCITE does

VCITE embeds the exact cited passage plus a SHA-256 fingerprint directly in
the document. A reader — or a machine — can independently verify that the
embedded passage wording matches the source by recomputing the hash, without
network access and without trusting the citing author. Hash integrity is not
claim validity: whether the source actually substantiates the author's claim
remains the reader's judgment. VCITE works in LaTeX, Markdown, HTML, plain
text, and AI outputs, with three conformance levels from minimal offline use
(L1) to full archival permanence (L3).

---

## FAQ

### What does the hash actually prove?

Integrity and provenance of the cited passage text and its two 50-code-point
context windows. If the hash in a VCITE object matches the recomputed hash
over the embedded `text_before`, `text_exact`, and `text_after`, then the
passage wording has not been altered since the author captured it
([SPEC §2, P3](SPEC.md#2-design-principles)). If the source document is
retrievable, a match also confirms that the passage appears in the source at
that wording.

### What does the hash NOT prove?

It does not prove that the author's claim is accurate, that the source
itself is trustworthy, that the passage wasn't taken out of context, or
that the passage means what the author implies. It does not prove that the
embedded passage even appears in the source unless a verifier fetches the
source and checks — anyone with a source document can paste arbitrary text
into a VCITE object and publish a self-consistent hash. Meaning-level
verification is an open research direction tracked in
[tools/strain/DESIGN.md](tools/strain/DESIGN.md).

### How do I verify a citation offline?

Take `text_exact`, `text_before`, and `text_after` from the VCITE object.
Apply NFC normalization, collapse `[\t\n\r ]+` to a single space, and strip
each segment. Pad the two context windows to exactly 50 Unicode code points.
Concatenate as `text_before | text_exact | text_after` (pipe delimiters),
UTF-8 encode, SHA-256, prepend `sha256:`. Compare to the embedded hash. The
canonical procedure is [SPEC §5](SPEC.md#5-hash-algorithm); the reference
function is
[`implementations/python/vcite/hash.py`](implementations/python/vcite/hash.py);
canonical inputs and outputs are in
[test-suite/vectors.yaml](test-suite/vectors.yaml).

### How do I verify a citation against the source (online)?

Run `python tools/verify.py article.html`. The verifier fetches the source
(via URL, DOI, or archive), locates the passage, and recomputes the hash.
For batch enrichment of existing citation files, use
`python tools/enrich.py <file> --verify`, which annotates each citation with
a status of `verified`, `source-drift`, `partial`, or `unreachable`.

### What if the source changes (link rot, text edits)?

L3 conformance requires `archive_url` (Perma.cc or self-hosted WACZ) so a
timestamped copy of the source survives link rot ([SPEC §4.2](SPEC.md#42-source-object),
[§7.2](SPEC.md#72-permacc-archiving)). When the live source drifts from the
captured wording, `tools/verify.py` reports the mismatch and `tools/enrich.py`
writes a `source-drift` status. `captured_at` records when the author saw
the passage, which is the reference point for resolving drift against an
archived copy.

### Why should I trust a hash from an untrusted publisher?

You don't. The point of the hash is that the reader recomputes it locally
from the embedded passage — server-side claims are only as trustworthy as
the server. Today the Python reference implementation
([`implementations/python`](implementations/python/)) is the path for
offline recompute; the JavaScript implementation currently ships `hash.mjs`
only ([`implementations/javascript/src/hash.mjs`](implementations/javascript/src/hash.mjs)),
so a browser-side recompute requires wiring that function into your own
page. An in-browser verifier UI is not yet provided.

### What about AI-generated citations?

VCITE supports `captured_by: "model"` to mark model-generated citations
([SPEC §4.1](SPEC.md#41-top-level-structure)). The hash verifies that the
passage text the model asserted is internally consistent and, if the source
is retrievable, that the text appears there. It does not detect the harder
fabrication mode where a real passage is cited but does not support the
claim the model attaches to it. [SPEC §B5](SPEC.md#appendix-b-open-questions-for-comment)
notes that model-captured citations should prefer L3 (with `archive_url`)
so a fixed reference point exists.

### Is VCITE a replacement for Scite, Perma.cc, or DOIs?

No. VCITE is the evidence layer; Scite, Perma.cc, CrossRef, and Text
Fragment URLs are enrichment, archival, and discovery layers that compose
with it. [SPEC §P4](SPEC.md#2-design-principles) makes service-independence
a design principle — L1 and L2 citations are conformant without any
third-party service — and [§P6](SPEC.md#2-design-principles) and
[§7](SPEC.md#7-integration-protocol) define how those services plug in as
optional enrichment.

---

## Get started

```bash
git clone https://github.com/graziul/vcite.git
cd vcite/implementations/python
pip install -e .
```

```python
from vcite import compute_hash
print(compute_hash("over 70% of URLs failed"))
# sha256:...
```

That's it. You can now compute passage fingerprints. Read on for complete
workflows by use case.

---

## Cookbook

### 1. Citing a passage in a research paper

You're writing a paper and want to cite a specific finding from a source.
You want the citation to be verifiable — not just "trust me, it says this."

```python
from vcite import VCiteCitation, VCiteSource, VCiteTarget

# Step 1: Identify the passage you're citing
passage = (
    "over 70% of the URLs provided in articles published in the "
    "Harvard Law Review did not lead to originally cited information"
)

# Step 2: Grab ~50 characters of surrounding context from the source
before = "As documented by Zittrain et al., "
after = ". This rate of decay accelerates"

# Step 3: Create the citation object (hash is computed automatically)
citation = VCiteCitation(
    vcite="1.0",
    id="vcite-link-rot",
    source=VCiteSource(
        title="Perma: Scoping and Addressing the Problem of Link Rot",
        authors=["Zittrain, Jonathan", "Albert, Kendra", "Lessig, Lawrence"],
        year=2014,
        doi="10.2139/ssrn.2329161",
        venue="Harvard Law Review Forum",
        source_type="academic",
    ),
    target=VCiteTarget(
        text_exact=passage,
        text_before=before,
        text_after=after,
        page_ref="p. 4",
        section="§ 2. Scope of the Problem",
    ),
    relation="supports",
    captured_at="2026-04-09T12:00:00Z",
    captured_by="author",
)

# Step 4: The hash was computed automatically
print(citation.target.hash)
# sha256:d2ba5887d4456199ce37a7860ce011485519925dc75c3564f50d1ffa1e1dc933

# Step 5: Export for your paper format
print(citation.to_json())          # JSON (canonical form)
print(citation.to_jsonld())        # JSON-LD (for HTML embedding)
print(citation.conformance_level)  # 2 (has context + DOI, no archive)
```

Then embed in your manuscript:

**LaTeX**:
```latex
\vcite[
  id={vcite-link-rot},
  exact={over 70\% of the URLs provided in articles published in
         the Harvard Law Review did not lead to originally cited
         information},
  before={As documented by Zittrain et al., },
  after={. This rate of decay accelerates},
  hash={sha256:d2ba5887d4456199ce37a7860ce011485519925dc75c3564f50d1ffa1e1dc933},
  doi={10.2139/ssrn.2329161},
  relation={supports},
  captured={2026-04-09}
]{Zittrain2014}
```

**Markdown** (Pandoc):
```markdown
As Zittrain et al. documented,
[over 70% of the URLs provided in articles published in the
Harvard Law Review did not lead to originally cited information]{.vcite
  vcite-id="vcite-link-rot"
  vcite-hash="sha256:d2ba5887d4456199ce37a7860ce011485519925dc75c3564f50d1ffa1e1dc933"
  vcite-exact="over 70% of the URLs provided in articles published in the Harvard Law Review did not lead to originally cited information"
  vcite-before="As documented by Zittrain et al., "
  vcite-after=". This rate of decay accelerates"
  vcite-source-doi="10.2139/ssrn.2329161"
  vcite-relation="supports"
  vcite-captured="2026-04-09"
}.
```

---

### 2. Verifying someone else's citation

You received a document with VCITE citations. You want to check whether the
cited passage actually matches the source.

```python
from vcite import VCiteCitation
import json

# Load the VCITE object (from JSON-LD in an HTML page, a JSON file, etc.)
with open("citation.json") as f:
    citation = VCiteCitation.from_json(f.read())

# Verify: does the hash match the passage + context?
if citation.verify():
    print(f"VERIFIED: hash matches passage")
    print(f"  Passage: {citation.target.text_exact[:80]}...")
    print(f"  Source: {citation.source.title}")
    print(f"  Relation: {citation.relation}")
    print(f"  Level: L{citation.conformance_level}")
else:
    print("FAILED: hash does not match. The passage may have been altered.")
```

You can also verify manually with just the hash function:

```python
from vcite import compute_hash

# Recompute from the cited text and context
result = compute_hash(
    text_exact="over 70% of the URLs provided in articles published in the Harvard Law Review did not lead to originally cited information",
    text_before="As documented by Zittrain et al., ",
    text_after=". This rate of decay accelerates",
)

# Compare to the claimed hash
claimed = "sha256:d2ba5887d4456199ce37a7860ce011485519925dc75c3564f50d1ffa1e1dc933"
print("Match!" if result == claimed else "Mismatch!")
```

---

### 3. Embedding verifiable citations in a web page

You're building a web page and want citations that readers can verify
in-browser.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Article with VCITE citations</title>

  <!-- VCITE evidence block -->
  <script type="application/ld+json">
  {
    "@context": "https://vcite.pub/ns/v1/",
    "@type": "VCiteCitation",
    "vcite": "1.0",
    "id": "vcite-link-rot",
    "source": {
      "title": "Perma: Scoping and Addressing the Problem of Link Rot",
      "doi": "10.2139/ssrn.2329161"
    },
    "target": {
      "text_before": "As documented by Zittrain et al., ",
      "text_exact": "over 70% of the URLs provided in articles published in the Harvard Law Review did not lead to originally cited information",
      "text_after": ". This rate of decay accelerates",
      "hash": "sha256:d2ba5887d4456199ce37a7860ce011485519925dc75c3564f50d1ffa1e1dc933",
      "fragment_url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2329161#:~:text=over+70%25"
    },
    "relation": "supports",
    "captured_at": "2026-04-09T12:00:00Z",
    "captured_by": "author"
  }
  </script>
</head>
<body>
  <p>
    As Zittrain et al. documented,
    <span data-vcite="vcite-link-rot" class="vcite-citation">
      over 70% of the URLs provided in articles published in the
      Harvard Law Review did not lead to originally cited information
    </span>.
  </p>
</body>
</html>
```

The `data-vcite` attribute links the inline text to the JSON-LD block.
Any VCITE-aware tool can extract the JSON-LD, recompute the hash, and
verify the citation.

---

### 4. Making AI outputs citation-verifiable

You're building an AI system that generates text citing sources. You want
those citations to be verifiable, not hallucinated.

**Plain text bracket notation** (for chat, email, terminal output):

```
The study found significant link rot in legal scholarship
[[vcite:vcite-link-rot|sha256:d2ba5887d4456199ce37a7860ce011485519925dc75c3564f50d1ffa1e1dc933|https://doi.org/10.2139/ssrn.2329161|supports]].
```

Format: `[[vcite:id|hash|source_url|relation]]`

**Programmatic generation**:

```python
from vcite import VCiteCitation, VCiteSource, VCiteTarget
from datetime import datetime

# The AI retrieved and verified this passage from a source
citation = VCiteCitation(
    vcite="1.0",
    id="vcite-ai-gen-001",
    source=VCiteSource(
        title="AI search engines gave incorrect answers to 60%+ of queries",
        url="https://www.cjr.org/tow_center/ai-search-audit",
        venue="Columbia Journalism Review",
        source_type="journalism",
    ),
    target=VCiteTarget(
        text_exact="eight major AI search tools provided incorrect or inaccurate answers to more than 60% of 1,600 test queries",
        text_before="The CJR found that ",
        text_after=", with error rates ranging",
    ),
    relation="quantifies",
    captured_at=datetime.now().isoformat() + "Z",
    captured_by="model",  # <-- marks this as AI-generated
)

# Verify the hash before including in output
assert citation.verify()

# Emit as JSON for structured output
print(citation.to_json())
```

The `captured_by: "model"` field distinguishes AI-generated citations from
human-authored ones. Verifiers can apply stricter policies to model-generated
citations (e.g., requiring L3 conformance with archive URLs).

---

### 5. Citing non-academic sources (journalism, reports, web)

Many sources lack DOIs. VCITE works for any text source.

```python
from vcite import VCiteCitation, VCiteSource, VCiteTarget

citation = VCiteCitation(
    vcite="1.0",
    id="vcite-cjr-audit",
    source=VCiteSource(
        title="AI search engines gave incorrect answers to 60%+ of queries",
        authors=["Tow Center for Digital Journalism"],
        year=2025,
        url="https://www.cjr.org/tow_center/ai-search-audit",
        archive_url="https://perma.cc/YT2M-CJR2",  # Perma.cc snapshot
        venue="Columbia Journalism Review",
        source_type="journalism",
    ),
    target=VCiteTarget(
        text_exact="eight major AI search tools provided incorrect or inaccurate answers to more than 60% of 1,600 test queries",
        text_before="The CJR found that ",
        text_after=", with error rates ranging",
        fragment_url="https://cjr.org/tow_center/ai-search-audit#:~:text=60%25",
    ),
    relation="quantifies",
    captured_at="2026-04-09T12:00:00Z",
    captured_by="author",
)

print(citation.conformance_level)  # 3 (has archive_url + fragment_url)
print(citation.target.hash)
# sha256:26c71181069e54c4d776f2a03de838c81aab3eff1a64a71ecde920f629367707
```

Use [Perma.cc](https://perma.cc) to create durable snapshots of web sources.
The `archive_url` field ensures the citation survives link rot.

---

### 6. Computing a hash without the Python library

The hash algorithm is simple enough to implement in any language. Here it is
in full (spec §5.2):

1. Normalize each segment: apply Unicode NFC, collapse `[\t\n\r ]+` to
   single space, strip leading/trailing whitespace
2. Pad/truncate `text_before` and `text_after` to exactly 50 Unicode code
   points (space-pad if shorter, truncate if longer)
3. Concatenate: `padded_before | text_exact | padded_after` (pipe delimiter)
4. Encode as UTF-8
5. SHA-256 hash
6. Prepend `sha256:`

```bash
# Quick verification with standard tools
echo -n '<padded_before>|<text_exact>|<padded_after>' | sha256sum
```

See [test-suite/vectors.yaml](test-suite/vectors.yaml) for test inputs and
expected outputs. Your implementation MUST reproduce all 4 mandatory vectors
(SV1-SV4) to be conformant.

---

## Conformance levels

| Level | Required | Use case |
|-------|----------|----------|
| **L1** | `text_exact` + `hash` | Offline, minimal, AI output |
| **L2** | L1 + `text_before` + `text_after` + source URL or DOI | Standard web/academic citation |
| **L3** | L2 + `archive_url` + `fragment_url` | Archival, durable, permanent |

Higher levels subsume lower levels. An L3 citation is also a valid L2 and L1.

## Relation vocabulary

| Value | Meaning |
|-------|---------|
| `supports` | Cited passage supports the claim |
| `contradicts` | Cited passage contradicts the claim |
| `defines` | Cited passage defines a term or concept |
| `quantifies` | Cited passage provides a measurement or statistic |
| `contextualizes` | Cited passage provides background context |
| `method` | Cited passage describes a method being used or discussed |
| `cautions` | Cited passage warns about limitations or risks |
| `x-*` | Extension namespace for domain-specific values |

## Serialization formats

| Format | Spec section | Description |
|--------|-------------|-------------|
| **JSON** | [§4](SPEC.md#4-data-model) | Canonical data model |
| **HTML / JSON-LD** | [§6.1](SPEC.md#61-html--json-ld) | Web pages with embedded evidence |
| **Markdown / Pandoc** | [§6.2](SPEC.md#62-markdown-pandoc-extended-syntax) | Academic writing with Pandoc |
| **LaTeX** | [§6.3](SPEC.md#63-latex) | `\vcite{}` macro for papers |
| **Plain text** | [§6.4](SPEC.md#64-plain-text--ai-output) | `[[vcite:...]]` bracket notation |

## Repository structure

```
SPEC.md                          The specification
schema/
  vcite.schema.json              JSON Schema for validation
  context.jsonld                 JSON-LD context (W3C Web Annotation mapping)
test-suite/
  vectors.yaml                   23 test vectors for interop testing
examples/
  academic-l3.json               Complete L3 academic citation
  journalism-l2.json             L2 journalism citation (no DOI)
  ai-output-l1.txt              L1 plain text notation
  embedding.html                 HTML page with JSON-LD
  citation.md                    Pandoc Markdown
  citation.tex                   LaTeX syntax
implementations/
  python/                        Python reference (pip install -e .)
  javascript/                    JavaScript/ESM reference (npm install)
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

- **Specification** ([SPEC.md](SPEC.md)): [CC-BY 4.0](LICENSE-SPEC)
- **Implementations** (code): [MIT](LICENSE-CODE)
