# VCITE Test Suite

Canonical test vectors for the VCITE passage fingerprinting algorithm (SPEC.md, Section 5).

## Test vectors

`vectors.yaml` contains 23 test vectors organized in three categories:

| Category | Count | Conformance |
|----------|-------|-------------|
| `spec_vectors` | 4 | **Mandatory** -- every conforming implementation MUST reproduce these |
| `appendix_vectors` | 3 | Hashes for the Appendix A example objects |
| `edge_case_vectors` | 16 | Unicode, whitespace, context padding, empty inputs, delimiters |

## How to use

1. Load `vectors.yaml` in your test framework
2. For each vector, call your `compute_hash(text_exact, text_before, text_after)` function
3. Assert the result equals `expected_hash`
4. All 4 `spec_vectors` MUST pass for conformance
5. All 23 vectors SHOULD pass for full interoperability

## Invariants

The vectors file includes an `invariants` section with 4 cross-vector assertions:

- **INV1**: NFC equivalence -- decomposed and precomposed inputs produce identical hashes
- **INV2**: Whitespace normalization -- whitespace-only exact text equals empty exact text
- **INV3**: Truncation equivalence -- 100-char context truncated to 50 equals explicit 50-char context
- **INV4**: Determinism -- 1000 identical calls produce identical output

## Adding test vectors

To propose a new test vector, open a GitHub issue with the tag `test-vector`.
Include: description, all three input fields, expected hash, and which edge case it covers.

## Implementation status

| Language | Tests | Status |
|----------|-------|--------|
| Python | 60/60 | Passing |
| JavaScript | 33/33 | Passing |
