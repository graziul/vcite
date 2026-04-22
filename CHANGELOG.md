# Changelog

All notable changes to the VCITE specification and reference implementations.

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
