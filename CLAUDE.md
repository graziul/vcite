# VCITE: Verified Citation with Inline Text Evidence

Open specification for passage-level, cryptographically verifiable citations.
Author: Chris Graziul / IDEP. **NOT** a University of Chicago project.

## Key Files
| Lookup | Path |
|--------|------|
| Specification | `SPEC.md` |
| JSON Schema | `schema/vcite.schema.json` |
| JSON-LD Context | `schema/context.jsonld` |
| Test Vectors | `test-suite/vectors.yaml` |
| Python Ref Impl | `implementations/python/vcite/` |
| JavaScript Ref Impl | `implementations/javascript/src/` |
| Examples | `examples/` |
| Enhance CLI | `tools/enhance.py` |
| Verify CLI | `tools/verify.py` |
| Source Fetcher | `tools/source_fetch.py` |
| Strain Analysis | `tools/strain/` |
| Contributing | `CONTRIBUTING.md` |
| Changelog | `CHANGELOG.md` |

## BLOCKING Rules
1. **Hash algorithm FROZEN**: §5.2 changes require spec version bump + ALL implementation updates + new test vectors
2. **Interop gate**: All implementations MUST pass `test-suite/vectors.yaml` (4 mandatory SV1-SV4 + 19 additional)
3. **Normative language**: Spec changes use RFC 2119 (MUST/SHOULD/MAY)
4. **Relation vocabulary**: Only spec §4.4 values + `x-*` extension namespace
5. **`captured_by` values**: `"author"` | `"tool"` | `"model"` only (spec §4.1)
6. **JSON-LD namespace**: All properties map to `https://vcite.pub/ns/v1/` URIs

## Version Status
- Spec version: **0.1** (DRAFT — not for citation)
- Hash algorithm: **STABLE** (no breaking changes planned)
- Data model: **DRAFT** (additive changes only, no field removals)
- Serializations: **DRAFT** (feedback welcome)
- Namespace: `https://vcite.pub/ns/v1/` (domain registration pending)

## Running Tests
```bash
# Python reference impl (60 tests)
cd implementations/python && pip install -e ".[dev]" && pytest tests/ -v

# Python verification pipeline (41 tests)
pytest tools/tests/ -v

# JavaScript
cd implementations/javascript && npm test
```

## Conformance Levels
| Level | Required | Use case |
|-------|----------|----------|
| L1 | `text_exact` + `hash` | Minimal, offline, AI output |
| L2 | L1 + `text_before/after` + source URL/DOI | Standard web/academic |
| L3 | L2 + `archive_url` + `fragment_url` | Archival, permanent |

## Relation Vocabulary
`supports` | `contradicts` | `defines` | `quantifies` | `contextualizes` | `method` | `cautions` | `x-*` (extension)

## Standards Alignment
- Extends W3C Web Annotation TextQuoteSelector vocabulary
- JSON-LD compatible (W3C structured data)
- RFC 2119 normative language
- SHA-256 with NFC normalization (no custom crypto)

## Tools
- `tools/enhance.py` — CLI to upgrade existing HTML/MD citations to VCITE objects
- `tools/verify.py` — reverse-lookup verification: fetch source, locate passage, recompute hash
- `tools/source_fetch.py` — fetch source documents via URL/DOI/archive_url, extract plain text
- `tools/hashdb.py` — SQLite verification database: persist results, track source drift
- `tools/renderer.py` — inject VCITE evidence panels + highlighting into HTML
- `tools/parsers/` — HTML and Markdown citation extractors
- `tools/metadata.py` — DOI/CrossRef metadata resolution for source enrichment
- `tools/templates/` — CSS, JS, and panel HTML for rendered evidence displays
- `tools/strain/` — **RESEARCH PROTOTYPE**: citation strain measurement (lexical scoring, sheaf consistency, discipline calibration)

## Architecture
```
SPEC.md                    ← The authority (spec document)
schema/                    ← Machine-readable spec (JSON Schema + JSON-LD)
test-suite/                ← Canonical test vectors (YAML)
implementations/
  python/                  ← Reference implementation (pip-installable)
  javascript/              ← Cross-platform implementation (ESM)
tools/                     ← Enhancement, verification, and strain analysis
  strain/                  ← Research prototype: citation strain measurement
examples/                  ← Working examples in all formats
```

The spec is the single source of truth. Implementations conform to it; the spec does not conform to implementations. Test vectors are canonical — if an implementation disagrees with a vector, the implementation is wrong.
