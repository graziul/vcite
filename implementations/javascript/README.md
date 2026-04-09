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

## Usage

### Node.js (ESM)

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

### Browser

```html
<script type="module">
  import { computeHash } from './src/hash.mjs';

  const hash = await computeHash('passage text', 'before ', ' after');
  console.log(hash);
</script>
```

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
node --test tests/hash.test.mjs
```

Uses the Node.js built-in test runner -- no framework dependencies.

## Spec

See the [VCITE specification](https://github.com/graziul/vcite) for the full standard.
