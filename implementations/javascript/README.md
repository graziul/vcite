# VCITE JavaScript Reference Implementation

JavaScript/ES module reference implementation for the [VCITE (Verified Citation with Inline Text Evidence)](https://github.com/graziul/vcite) specification.

## Requirements

- Node.js 18+ (uses Web Crypto API and ES modules)
- Zero external dependencies

## Install

```bash
npm install vcite
# or link locally:
npm link
```

## Modules

| Module | Purpose |
|--------|---------|
| `vcite` (`./src/hash.mjs`) | `computeHash()` and low-level helpers (spec section 5) |
| `vcite/models` (`./src/models.mjs`) | `VCiteSource`, `VCiteTarget`, `VCiteCitation` (spec section 4) |
| `vcite/verify` (`./src/verify.mjs`) | `verifyCitationOffline()`, `findCitationsInDocument()`, `attachVerifyButtons()` |

## Usage

### Compute a passage fingerprint

```javascript
import { computeHash } from 'vcite';

const hash = await computeHash(
  'exactly 42%',         // text_exact
  'The rate is ',        // text_before
  ' as measured'         // text_after
);
console.log(hash);
// sha256:f2d30080cf6f2dd31c4e160673b427742c132bd7fe6b014e0b5026daea80bbf5
```

### Build and verify a citation object

```javascript
import {
  VCiteCitation,
  VCiteSource,
  VCiteTarget,
} from 'vcite/models';

const citation = new VCiteCitation({
  vcite: '1.0',
  id: 'vcite-001',
  source: new VCiteSource({
    title: 'Perma: Scoping and Addressing the Problem of Link Rot',
    url: 'https://example.com/paper',
  }),
  target: await VCiteTarget.create({
    text_exact: 'exactly 42%',
    text_before: 'The rate is ',
    text_after: ' as measured',
  }),
  relation: 'supports',
  captured_at: '2026-04-22T12:00:00Z',
  captured_by: 'author',
});

await citation.verify();          // true
citation.conformanceLevel;        // 2
JSON.stringify(citation.toJsonld());
```

`VCiteTarget.create()` auto-computes the hash when one is not supplied.
The plain constructor leaves the hash blank, matching the Python
reference's two-phase shape (used when loading a persisted hash).

### Verify citations in-browser

A published VCITE article embeds every citation as JSON-LD in `<head>`.
A reader with no trust in the publisher can load `src/verify.mjs` in the
page and recompute each hash locally:

```html
<script type="module">
  import { attachVerifyButtons } from './implementations/javascript/src/verify.mjs';

  attachVerifyButtons({ document });
</script>
```

This finds every `.vcite-panel`, matches it to a JSON-LD citation by id,
and injects a "Verify fingerprint" button that re-runs the SHA-256 using
the reader's Web Crypto. On success the panel shows
`Fingerprint re-verified in browser (sha256:...)` in green. On tampering
it shows the claimed and recomputed hashes side-by-side in red.

The renderer in `tools/templates/vcite.js` bundles the same logic as an
IIFE for inline injection in rendered VCITE-enhanced HTML; the ESM entry
points above are for readers or tools that prefer a module boundary.

### Helper functions

```javascript
import { normalizeSegment, padContext, buildHashInput } from 'vcite';

// NFC normalize + whitespace collapse
normalizeSegment('  tabs\tand  spaces  ');  // "tabs and spaces"

// Pad/truncate to 50 code points
padContext('short');  // "short" + 45 spaces

// Build the raw hash input string
buildHashInput('exact', 'before', 'after');
```

## Running Tests

```bash
npm test
```

Runs every file under `tests/` with Node's built-in test runner. 72 tests
cover the hash algorithm, data model, in-browser verification, and
interop against the mandatory spec vectors SV1-SV4 from
`test-suite/vectors.yaml`.

## Spec

See the [VCITE specification](https://github.com/graziul/vcite) for the full standard.
