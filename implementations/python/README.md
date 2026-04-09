# VCITE Python Reference Implementation

Python reference implementation for the [VCITE (Verified Citation with Inline Text Evidence)](https://github.com/graziul/vcite) specification.

## Install

```bash
pip install -e .
# With dev dependencies (for running tests):
pip install -e ".[dev]"
```

Requires Python 3.10+. No runtime dependencies (stdlib only).

## Usage

```python
from vcite import compute_hash, VCiteCitation, VCiteSource, VCiteTarget

# Compute a passage fingerprint
h = compute_hash(
    text_exact="exactly 42%",
    text_before="The rate is ",
    text_after=" as measured",
)
print(h)
# sha256:f2d30080cf6f2dd31c4e160673b427742c132bd7fe6b014e0b5026daea80bbf5

# Create a citation object (hash auto-computed)
citation = VCiteCitation(
    vcite="1.0",
    id="example-001",
    source=VCiteSource(
        title="Example Paper",
        authors=["Author, A."],
        year=2025,
        doi="10.1234/example",
    ),
    target=VCiteTarget(
        text_exact="exactly 42%",
        text_before="The rate is ",
        text_after=" as measured",
    ),
    relation="quantifies",
    captured_at="2026-04-08T12:00:00Z",
    captured_by="author",
)

# Verify the hash
assert citation.verify()

# Serialize to JSON
print(citation.to_json())

# Round-trip
restored = VCiteCitation.from_json(citation.to_json())
assert restored.verify()

# JSON-LD output
ld = citation.to_jsonld()
assert ld["@context"] == "https://vcite.pub/ns/v1/"

# Conformance level
print(citation.conformance_level)  # 2 (has context + DOI)
```

## Running Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Spec

See the [VCITE specification](https://github.com/graziul/vcite) for the full standard.
