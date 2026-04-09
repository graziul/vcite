/**
 * VCITE Hash Tests -- Node.js built-in test runner
 *
 * Run with: node --test tests/hash.test.mjs
 *
 * Tests against the 4 mandatory spec vectors (section 5.3), 3 appendix A
 * examples, and selected edge cases from the canonical test suite.
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  computeHash,
  normalizeSegment,
  padContext,
  buildHashInput,
} from '../src/hash.mjs';

// ── normalizeSegment ───────────────────────────────

describe('normalizeSegment', () => {
  it('applies NFC normalization', () => {
    // e + combining acute => precomposed e with acute
    const combining = 'caf\u0065\u0301';
    const precomposed = 'caf\u00e9';
    assert.equal(normalizeSegment(combining), normalizeSegment(precomposed));
  });

  it('collapses whitespace runs to single space', () => {
    assert.equal(normalizeSegment('  multiple   spaces  here  '), 'multiple spaces here');
  });

  it('collapses tabs and newlines', () => {
    assert.equal(normalizeSegment('before\n\twith\ttabs'), 'before with tabs');
  });

  it('trims leading and trailing whitespace', () => {
    assert.equal(normalizeSegment('  trimmed  '), 'trimmed');
  });

  it('handles empty string', () => {
    assert.equal(normalizeSegment(''), '');
  });

  it('preserves non-breaking space (U+00A0)', () => {
    const result = normalizeSegment('hello\u00a0world');
    assert.equal(result, 'hello\u00a0world');
    assert.notEqual(result, 'hello world');
  });
});

// ── padContext ──────────────────────────────────────

describe('padContext', () => {
  it('pads short strings with spaces to 50 chars', () => {
    const result = padContext('Hi');
    assert.equal(result.length, 50);
    assert.equal(result, 'Hi' + ' '.repeat(48));
  });

  it('truncates long strings to 50 chars', () => {
    const result = padContext('A'.repeat(100));
    assert.equal(result.length, 50);
    assert.equal(result, 'A'.repeat(50));
  });

  it('returns exact 50 chars unchanged', () => {
    const exact = 'X'.repeat(50);
    assert.equal(padContext(exact), exact);
  });

  it('pads empty string to 50 spaces', () => {
    const result = padContext('');
    assert.equal(result.length, 50);
    assert.equal(result, ' '.repeat(50));
  });

  it('handles multi-byte characters correctly', () => {
    const emoji = '\ud83c\udf89'.repeat(3); // 3 party popper emoji
    const result = padContext(emoji);
    assert.equal(Array.from(result).length, 50);
  });
});

// ── buildHashInput ─────────────────────────────────

describe('buildHashInput', () => {
  it('concatenates with pipe delimiters', () => {
    const result = buildHashInput('exact text', 'before', 'after');
    assert.ok(result.includes('|exact text|'));
  });

  it('pads context segments to 50 chars each', () => {
    const result = buildHashInput('middle', 'a', 'b');
    const parts = result.split('|');
    assert.equal(parts.length, 3);
    assert.equal(parts[0].length, 50);
    assert.equal(parts[2].length, 50);
  });
});

// ── Spec §5.3 Mandatory Vectors ────────────────────

describe('computeHash -- spec mandatory vectors', () => {
  it('SV1: basic ASCII passage', async () => {
    const hash = await computeHash('exactly 42%', 'The rate is ', ' as measured');
    assert.equal(hash, 'sha256:f2d30080cf6f2dd31c4e160673b427742c132bd7fe6b014e0b5026daea80bbf5');
  });

  it('SV2: Unicode NFC normalization', async () => {
    const hash = await computeHash('r\u00e9sum\u00e9 complet', 'caf\u00e9 au lait ', ' du rapport');
    assert.equal(hash, 'sha256:c9ac6f27318e7f3a7d27b85a9823ac7644e6a02d2f58c2abd1801ae99a9a53e4');
  });

  it('SV3: whitespace collapse', async () => {
    const hash = await computeHash('  spaces  here  ', '  multiple   ', '  trimmed  ');
    assert.equal(hash, 'sha256:ad4c8f44cc63c1d34451eab399094657961632d044a29c9c852d2bac064f3948');
  });

  it('SV4: minimal L1 -- no context', async () => {
    const hash = await computeHash('Only exact, no context', '', '');
    assert.equal(hash, 'sha256:d8ea2d1c308a3d38328362479c1a97dbdf5a9a87ca64a6a4b3fdd430853edd8b');
  });
});

// ── Appendix A Examples ────────────────────────────

describe('computeHash -- appendix A examples', () => {
  it('A1: academic source (Zittrain)', async () => {
    const textExact =
      'over 70% of the URLs provided in articles published in ' +
      'the Harvard Law Review did not lead to originally cited information';
    const hash = await computeHash(textExact, 'As documented by Zittrain et al., ',
      '. This rate of decay accelerates');
    assert.equal(hash, 'sha256:d2ba5887d4456199ce37a7860ce011485519925dc75c3564f50d1ffa1e1dc933');
  });

  it('A2: journalism source (CJR)', async () => {
    const textExact =
      'eight major AI search tools provided incorrect or inaccurate ' +
      'answers to more than 60% of 1,600 test queries';
    const hash = await computeHash(textExact, 'The CJR found that ',
      ', with error rates ranging');
    assert.equal(hash, 'sha256:26c71181069e54c4d776f2a03de838c81aab3eff1a64a71ecde920f629367707');
  });

  it('A3: plain text / AI output (no context)', async () => {
    const textExact =
      'AI-generated text often cannot be verified or retrieved by ' +
      'anyone other than the original author';
    const hash = await computeHash(textExact);
    assert.equal(hash, 'sha256:b8ba02cbee19230434c6a5b1431c0f8bfab8e00eb13b670875faa874959fb298');
  });
});

// ── Edge Cases ─────────────────────────────────────

describe('computeHash -- edge cases', () => {
  it('empty all inputs', async () => {
    const hash = await computeHash('', '', '');
    assert.equal(hash, 'sha256:da6f851a04676cd01c5e80335da666433c880012982d53cb022336bf565acfbd');
  });

  it('whitespace-only exact equals empty', async () => {
    const wsHash = await computeHash('   \t\n  ');
    const emptyHash = await computeHash('');
    assert.equal(wsHash, emptyHash);
  });

  it('pipe in exact text', async () => {
    const hash = await computeHash('a|b|c');
    assert.equal(hash, 'sha256:277e31e19888f6d24cd513dcd3b4850518c0fc55966ebc52dd87288863ca421a');
  });

  it('CJK characters count as code points', async () => {
    const hash = await computeHash('\u4f60\u597d\u4e16\u754c');
    assert.equal(hash, 'sha256:784d8327eb064ca62d2bfbfd5542f42336d154c885bfe98dda565b76606065ed');
  });

  it('emoji are single code points', async () => {
    const hash = await computeHash('\ud83d\ude00\ud83d\udca1');
    assert.equal(hash, 'sha256:313603505a6cde53ee7148c3bfadb403e10036c2612be9783dac874d4c70fc6d');
  });

  it('NFD/NFC equivalence', async () => {
    const nfd = await computeHash('cafe\u0301');
    const nfc = await computeHash('caf\u00e9');
    assert.equal(nfd, nfc);
    assert.equal(nfd, 'sha256:b433ffec5f0511a6d43881e4fb8bed86ba6616a16608477478c0cdd872b48285');
  });

  it('non-breaking space NOT collapsed', async () => {
    const nbspHash = await computeHash('hello\u00a0world');
    const spaceHash = await computeHash('hello world');
    assert.notEqual(nbspHash, spaceHash);
    assert.equal(nbspHash, 'sha256:2eceb2ef315fb702311c91140076a43159d6e99b5b738f035cff65d08daeab1f');
  });

  it('50-char context unchanged', async () => {
    const hash = await computeHash('test', 'A'.repeat(50), 'A'.repeat(50));
    assert.equal(hash, 'sha256:deb6e1e50d10560c7e65a4c48c1e7d7c58bf212935c091043b735fbefb317d4c');
  });

  it('100-char context truncated to 50', async () => {
    const hash = await computeHash('test', 'B'.repeat(100), 'B'.repeat(100));
    assert.equal(hash, 'sha256:86309984bf5222c0dbdb2611a75ad25df73e852f7f8d697414b880be6a97d4b4');
  });

  it('truncation equivalence', async () => {
    const hash100 = await computeHash('test', 'A'.repeat(100), 'A'.repeat(100));
    const hash50 = await computeHash('test', 'A'.repeat(50), 'A'.repeat(50));
    assert.equal(hash100, hash50);
  });

  it('short context padded', async () => {
    const hash = await computeHash('test', 'short', 'ctx');
    assert.equal(hash, 'sha256:a16f3204c5229ddd197e60ad3cfeefe38ce956ec586825f83671bcabbb329980');
  });

  it('Hello world with no context', async () => {
    const hash = await computeHash('Hello, world!');
    assert.equal(hash, 'sha256:cad437fb7351553fe2d565e4b67e59713e063222a2c65a2f768cce73352a1586');
  });
});

// ── Determinism ────────────────────────────────────

describe('computeHash -- determinism', () => {
  it('100 identical calls produce same hash', async () => {
    const results = new Set();
    for (let i = 0; i < 100; i++) {
      results.add(await computeHash('test', 'before', 'after'));
    }
    assert.equal(results.size, 1);
  });
});
