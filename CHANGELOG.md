# Changelog

All notable changes to the VCITE specification and reference implementations.

## [Unreleased]

Post-0.1-STABLE MVP work closing the seven delta-to-MVP items identified
in the project assessment. All changes are additive and preserve the
FROZEN commitments of 0.1-STABLE.

### Added

- **Enrichment contract** (`enrichment.verification`, `enrichment.strain`).
  Additive optional sub-objects carrying reverse-lookup and strain
  results in-band on the citation, consumed by the renderer. Status
  vocabulary: `verified`, `internal-only`, `partial`, `source-drift`,
  `internal-mismatch`, `unreachable`.
- **`tools/enrich.py`** — orchestrator that runs `verify.py` (and
  optionally strain analysis) and writes results into each citation's
  enrichment field. Distinguishes offline (internal-only) from online
  (source-consulted) so panels never claim "source-verified" when the
  source was not fetched.
- **In-browser fingerprint re-verification**. JavaScript impl now ships
  `src/models.mjs` and `src/verify.mjs` alongside the existing
  `src/hash.mjs`; `tools/templates/vcite.js` includes a bundled IIFE
  that attaches a "Verify fingerprint" button to every rendered panel.
  Clicking re-computes the SHA-256 in the reader's browser and reports
  pass/fail plus the recomputed hash. `node --test` suite of 73 tests
  including SV1–SV4 interop against Python.
- **LaTeX citation extraction** (`tools/parsers/latex_parser.py`).
  Supports `\begin{quote}` / `\begin{quotation}` / `\begin{displayquote}`,
  `\enquote`, TeX `` `'/``'' `` quotes, and the `\textquote*` family.
  Strips common inline macros, handles TeX escapes, and skips
  verbatim / lstlisting / math / footnote regions. 36 unit tests.
  `tools/enhance.py` auto-routes `.tex` / `.latex` inputs.
- **W3C Text Fragment URL generation** (`tools/fragment_url.py`).
  `build_text_fragment_url` produces `#:~:text=prefix-,start,end,-suffix`
  URLs at enhance time; enhance.py populates `target.fragment_url`
  automatically with `--no-fragment-url` as an escape hatch. Rendered
  panels surface these as `Open passage ↗` deep-links alongside the
  document-level `Open source ↗`. 26 unit tests.
- **Wayback Machine archival integration** (`tools/archive.py`).
  `enhance.py --archive` queries `/wayback/available` and falls back
  to Save Page Now, populating `source.archive_url` (L3 upgrade).
  `--archive-lookup-only` skips SPN for CI-safe runs. Anonymous /
  rate-limited / best-effort. 20 unit tests, all network mocked.
- **README FAQ** distinguishing hash integrity from claim validity,
  with eight questions covering offline/online verification, source
  drift, client-side recompute trust model, AI-generated citations,
  and composability with Scite/Perma.cc/DOIs.

### Fixed

- `captured_by` validation in the Python reference impl now accepts
  `"tool"` as required by SPEC §4.1 (was: `{"author", "model"}` only).
  Matching JS validation introduced at the same time.
- `tools/renderer.py` `_strip_existing_vcite` regression: the previous
  `<script>[^<]*toggleVcite[^<]*</script>` regex failed on any script
  body containing `<` (comparisons, arrow functions, bundled IIFEs),
  causing successive re-renders to accumulate duplicate script blocks.
  Replaced with a stateful scanner covering both `toggleVcite` and
  `attachVerifyButtons` IIFEs. Locked with two regression tests.

### Documented

- **Strain semantic gap**: `tools/strain/DESIGN.md` now notes that the
  `target.text_exact` field in current `enhance.py` output is the
  citing-article sentence, not the source passage the strain model
  assumes, so strain numbers from the current pipeline measure
  "context divergence within the citing article" rather than
  source-versus-claim distance. Two paths forward documented.

### Tests

- Python suite: 232 passing (from 60 at session start).
- JavaScript suite: 73 passing (from 33).
- SV1–SV4 interop enforced in the JS test suite against Python.

## [0.1-STABLE] - 2026-04-22

Documentation-only release. No code, schema, or test-vector changes. The 0.1
specification is declared safe to cite and implement against; the items below
are FROZEN within the 0.x line.

### Stability

- **Hash algorithm (§5.2): FROZEN.** Input construction, 50-code-point
  context windows, NFC normalization, whitespace-collapse regex, SHA-256
  digest, and `sha256:` prefix cannot change within 0.x. Any change requires
  a SemVer major bump (1.0) AND preserves backward compatibility: objects
  minted under the prior algorithm MUST continue to verify against the rules
  current at their `captured_at`.
- **Core data model (§4): FROZEN at the field level.** No field of
  `VCiteCitation`, `VCiteSource`, or `VCiteTarget` may be removed, renamed,
  retyped, or have its semantics altered in 0.x. Additive changes (new
  OPTIONAL fields) are permitted and MUST default to omitted in serializations.
- **Relation vocabulary (§4.4): FROZEN base seven.** `supports`,
  `contradicts`, `defines`, `quantifies`, `contextualizes`, `method`,
  `cautions`. The `x-*` extension namespace remains open.
- **Conformance levels (§8): FROZEN.** L1, L2, L3 required-field sets do not
  change in 0.x.
- **`captured_by` enumeration (§4.1): FROZEN.** `"author"` | `"tool"` |
  `"model"`.
- **Test vectors SV1–SV4: FROZEN** in inputs and expected hashes.
- **Open for change:** JSON-LD context URL (pending domain registration),
  optional serialization formats (Markdown/LaTeX/plain-text), enrichment
  field conventions, governance model.

### Status

- Spec status: **0.1-STABLE** (safe to cite; `stable_since: 2026-04-22`)
- Hash algorithm: **Frozen** (any change requires 1.0)
- Data model: **Frozen at field level** (additive changes allowed, no removals)
- Serialization formats: **Draft** (canonical JSON is stable; Markdown/LaTeX/plain-text may evolve)
- Governance: IDEP stewardship with open GitHub issue tracker (open for change before 1.0)

## [0.1.0] - 2026-04-09

### Added

- **Specification** (SPEC.md): Complete data model, hash algorithm, 5 serialization formats,
  3 conformance levels, integration protocol, governance model
- **Hash algorithm** (stable): SHA-256 passage fingerprinting with NFC normalization,
  whitespace collapse, and fixed-length context windows (50 Unicode code points)
- **Python reference implementation**: `compute_hash()`, `VCiteCitation` dataclass,
  serialization to JSON/JSON-LD, verification, conformance level detection
- **JavaScript reference implementation**: ESM module, Web Crypto API + Node.js fallback,
  interoperable with Python implementation
- **JSON Schema**: Draft 2020-12 schema for VCITE citation objects with conformance
  level validation (L1/L2/L3)
- **JSON-LD context**: W3C Web Annotation TextQuoteSelector mapping
- **Test suite**: 23 test vectors (4 mandatory, 3 appendix, 16 edge cases),
  4 cross-vector invariants
- **Examples**: Academic (L3), journalism (L2), AI output (L1) in JSON, HTML,
  Markdown, LaTeX, and plain text

### Status

- Hash algorithm: **Stable** (no breaking changes planned)
- Data model: **Draft** (field additions possible, no removals)
- Serialization formats: **Draft** (feedback welcome)
- Governance: IDEP stewardship with open GitHub issue tracker
- Target namespace: `https://vcite.pub/ns/v1/` (domain registration pending)

### Spec clarifications

- Context window counts Unicode code points, not UTF-8 bytes (matters for CJK)
- Non-breaking space (U+00A0) intentionally not collapsed by whitespace regex
- Pipe delimiter not escaped in hash input; fixed-length windows ensure unambiguous parsing
