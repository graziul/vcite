/**
 * VCITE models tests -- Node.js built-in test runner.
 *
 * Mirrors the key shape of implementations/python/tests/test_models.py.
 * Covers auto-hash, round-trip serialization, verify(), conformance
 * levels, and validation errors.
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
  VCiteCitation,
  VCiteSource,
  VCiteTarget,
  VALID_RELATIONS,
  JSONLD_CONTEXT,
} from '../src/models.mjs';
import { computeHash } from '../src/hash.mjs';

async function makeCitation(overrides = {}) {
  const defaults = {
    vcite: '1.0',
    id: 'test-001',
    source: new VCiteSource({
      title: 'Test Paper',
      authors: ['Author, A.'],
      year: 2025,
      doi: '10.1234/test',
      url: 'https://example.com/paper',
    }),
    target: await VCiteTarget.create({
      text_exact: 'exactly 42%',
      text_before: 'The rate is ',
      text_after: ' as measured',
    }),
    relation: 'supports',
    captured_at: '2026-04-08T12:00:00Z',
    captured_by: 'author',
  };
  return new VCiteCitation({ ...defaults, ...overrides });
}

describe('VCiteTarget', () => {
  it('auto-computes hash via create()', async () => {
    const t = await VCiteTarget.create({
      text_exact: 'exactly 42%',
      text_before: 'The rate is ',
      text_after: ' as measured',
    });
    const expected = await computeHash(
      'exactly 42%',
      'The rate is ',
      ' as measured',
    );
    assert.equal(t.hash, expected);
  });

  it('preserves explicit hash', async () => {
    const t = await VCiteTarget.create({
      text_exact: 'test',
      hash: 'sha256:explicit',
    });
    assert.equal(t.hash, 'sha256:explicit');
  });

  it('constructor alone does not compute hash', () => {
    const t = new VCiteTarget({ text_exact: 'x' });
    assert.equal(t.hash, '');
  });
});

describe('VCiteCitation validation', () => {
  it('accepts all seven spec relations', async () => {
    for (const rel of VALID_RELATIONS) {
      const c = await makeCitation({ relation: rel });
      assert.equal(c.relation, rel);
    }
  });

  it('accepts x- extension relation', async () => {
    const c = await makeCitation({ relation: 'x-legal:exhibit' });
    assert.equal(c.relation, 'x-legal:exhibit');
  });

  it('rejects invalid relation', async () => {
    await assert.rejects(
      async () => makeCitation({ relation: 'approves' }),
      /Invalid relation/,
    );
  });

  it('rejects invalid captured_by', async () => {
    await assert.rejects(
      async () => makeCitation({ captured_by: 'robot' }),
      /captured_by must be/,
    );
  });

  it('accepts all three captured_by values from SPEC §4.1', async () => {
    for (const value of ['author', 'tool', 'model']) {
      const c = await makeCitation({ captured_by: value });
      assert.equal(c.captured_by, value);
    }
  });
});

describe('Serialization round-trip', () => {
  it('toDict strips null enrichment', async () => {
    const c = await makeCitation();
    const d = c.toDict();
    assert.ok(!('enrichment' in d));
  });

  it('toDict preserves core values', async () => {
    const c = await makeCitation();
    const d = c.toDict();
    assert.equal(d.vcite, '1.0');
    assert.equal(d.id, 'test-001');
    assert.equal(d.source.title, 'Test Paper');
    assert.equal(d.target.text_exact, 'exactly 42%');
  });

  it('toJson -> fromJson round-trip', async () => {
    const original = await makeCitation();
    const restored = VCiteCitation.fromJson(original.toJson());
    assert.equal(restored.id, original.id);
    assert.equal(restored.vcite, original.vcite);
    assert.equal(restored.source.title, original.source.title);
    assert.equal(restored.target.text_exact, original.target.text_exact);
    assert.equal(restored.target.hash, original.target.hash);
    assert.equal(restored.relation, original.relation);
    assert.equal(restored.captured_at, original.captured_at);
    assert.equal(restored.captured_by, original.captured_by);
  });

  it('fromDict builds a working citation', () => {
    const d = {
      vcite: '1.0',
      id: 'from-dict-001',
      source: { title: 'Dict Source', authors: ['B, C.'] },
      target: {
        text_exact: 'test passage',
        hash: 'sha256:abc',
        text_before: '',
        text_after: '',
      },
      relation: 'defines',
      captured_at: '2026-01-01T00:00:00Z',
      captured_by: 'model',
    };
    const c = VCiteCitation.fromDict(d);
    assert.equal(c.id, 'from-dict-001');
    assert.equal(c.source.title, 'Dict Source');
    assert.equal(c.target.hash, 'sha256:abc');
  });

  it('fromDict tolerates JSON-LD @context / @type keys', () => {
    const d = {
      '@context': JSONLD_CONTEXT,
      '@type': 'VCiteCitation',
      vcite: '1.0',
      id: 'jsonld-001',
      source: { title: 'x' },
      target: { text_exact: 'y', hash: 'sha256:z' },
      relation: 'supports',
      captured_at: '2026-04-08T12:00:00Z',
      captured_by: 'author',
    };
    const c = VCiteCitation.fromDict(d);
    assert.equal(c.id, 'jsonld-001');
  });

  it('toJsonld adds @context and @type', async () => {
    const c = await makeCitation();
    const ld = c.toJsonld();
    assert.equal(ld['@context'], JSONLD_CONTEXT);
    assert.equal(ld['@type'], 'VCiteCitation');
    assert.equal(ld.id, 'test-001');
  });
});

describe('verify()', () => {
  it('returns true for untampered citation', async () => {
    const c = await makeCitation();
    assert.equal(await c.verify(), true);
  });

  it('returns false after text_exact tamper', async () => {
    const c = await makeCitation();
    c.target.text_exact = 'exactly 43%';
    assert.equal(await c.verify(), false);
  });

  it('returns false after context tamper', async () => {
    const c = await makeCitation();
    c.target.text_before = 'The rate was ';
    assert.equal(await c.verify(), false);
  });

  it('returns false when stored hash is zeroed', async () => {
    const c = await makeCitation();
    c.target.hash =
      'sha256:0000000000000000000000000000000000000000000000000000000000000000';
    assert.equal(await c.verify(), false);
  });
});

describe('conformanceLevel', () => {
  it('L1 for minimal citation (no context, no source url)', async () => {
    const c = await makeCitation({
      source: new VCiteSource({ title: 'Minimal' }),
      target: await VCiteTarget.create({ text_exact: 'test' }),
    });
    assert.equal(c.conformanceLevel, 1);
  });

  it('L2 with context + url', async () => {
    const c = await makeCitation({
      source: new VCiteSource({
        title: 'Standard',
        url: 'https://example.com',
      }),
      target: await VCiteTarget.create({
        text_exact: 'test',
        text_before: 'before ',
        text_after: ' after',
      }),
    });
    assert.equal(c.conformanceLevel, 2);
  });

  it('L2 with context + DOI (no url)', async () => {
    const c = await makeCitation({
      source: new VCiteSource({
        title: 'Standard DOI',
        doi: '10.1234/test',
      }),
      target: await VCiteTarget.create({
        text_exact: 'test',
        text_before: 'before ',
        text_after: ' after',
      }),
    });
    assert.equal(c.conformanceLevel, 2);
  });

  it('L3 with archive_url + fragment_url', async () => {
    const c = await makeCitation({
      source: new VCiteSource({
        title: 'Enhanced',
        url: 'https://example.com',
        archive_url: 'https://web.archive.org/web/2025/https://example.com',
      }),
      target: await VCiteTarget.create({
        text_exact: 'test',
        text_before: 'before ',
        text_after: ' after',
        fragment_url: 'https://example.com#:~:text=test',
      }),
    });
    assert.equal(c.conformanceLevel, 3);
  });

  it('L1 when context present but no source url/DOI', async () => {
    const c = await makeCitation({
      source: new VCiteSource({ title: 'No URL' }),
      target: await VCiteTarget.create({
        text_exact: 'test',
        text_before: 'before ',
        text_after: ' after',
      }),
    });
    assert.equal(c.conformanceLevel, 1);
  });

  it('L2 when archive present but fragment_url missing', async () => {
    const c = await makeCitation({
      source: new VCiteSource({
        title: 'Has Archive',
        url: 'https://example.com',
        archive_url: 'https://web.archive.org/web/2025/https://example.com',
      }),
      target: await VCiteTarget.create({
        text_exact: 'test',
        text_before: 'before ',
        text_after: ' after',
      }),
    });
    assert.equal(c.conformanceLevel, 2);
  });
});
