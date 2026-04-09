# Changelog

All notable changes to the VCITE specification and reference implementations.

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
