/**
 * VCITE verify tests -- in-browser verification logic.
 *
 * Uses the Node test runner and a tiny hand-rolled DOM stub -- we do
 * not pull in jsdom (no external deps). The stub only implements the
 * subset of DOM surface attachVerifyButtons touches.
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  VCiteCitation,
  VCiteSource,
  VCiteTarget,
} from '../src/models.mjs';
import {
  verifyCitationOffline,
  findCitationsInDocument,
  attachVerifyButtons,
} from '../src/verify.mjs';
import { computeHash } from '../src/hash.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const VECTORS_PATH = path.join(REPO_ROOT, 'test-suite', 'vectors.yaml');

// Minimal DOM stub -- implements only the surface verify.mjs uses.

class El {
  constructor(tag) {
    this.tagName = (tag || '').toUpperCase();
    this.children = [];
    this.parent = null;
    this.attrs = {};
    this.className = '';
    this.id = '';
    this._textContent = '';
    this.hidden = false;
    this.disabled = false;
    this.listeners = {};
    this.type = '';
  }
  get firstChild() { return this.children[0] || null; }
  appendChild(child) {
    child.parent = this;
    this.children.push(child);
    return child;
  }
  removeChild(child) {
    const i = this.children.indexOf(child);
    if (i >= 0) this.children.splice(i, 1);
    child.parent = null;
    return child;
  }
  get textContent() {
    if (this._textContent) return this._textContent;
    return this.children.map(c => c.textContent).join('');
  }
  set textContent(v) {
    this._textContent = v;
    this.children = [];
  }
  addEventListener(type, handler) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(handler);
  }
  async dispatch(type, ev = {}) {
    const handlers = this.listeners[type] || [];
    for (const h of handlers) {
      const event = { ...ev, stopPropagation: () => {} };
      await h(event);
    }
  }
  _matches(selector) {
    if (selector.startsWith('.')) {
      const cls = selector.slice(1);
      return this.className && this.className.split(/\s+/).includes(cls);
    }
    const bracket = /^([a-zA-Z]+)\[([a-zA-Z-]+)="([^"]+)"\]$/.exec(selector);
    if (bracket) {
      const [, tag, attr, val] = bracket;
      return (
        this.tagName === tag.toUpperCase() &&
        (this.attrs[attr] === val || (attr === 'type' && this.type === val))
      );
    }
    const tagCls = /^([a-zA-Z]+)\.(.+)$/.exec(selector);
    if (tagCls) {
      const [, tag, cls] = tagCls;
      return (
        this.tagName === tag.toUpperCase() &&
        this.className.split(/\s+/).includes(cls)
      );
    }
    return this.tagName === selector.toUpperCase();
  }
  _walk() {
    const out = [];
    const stack = [...this.children];
    while (stack.length) {
      const el = stack.shift();
      out.push(el);
      stack.unshift(...el.children);
    }
    return out;
  }
  querySelectorAll(selector) {
    return this._walk().filter(el => el._matches(selector));
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
}

class DocStub extends El {
  constructor() {
    super('document');
    this.body = new El('body');
    this.appendChild(this.body);
  }
  createElement(tag) {
    return new El(tag);
  }
}

function scriptBlock(doc, jsonText) {
  const s = new El('script');
  s.type = 'application/ld+json';
  s.attrs.type = 'application/ld+json';
  s._textContent = jsonText;
  doc.body.appendChild(s);
  return s;
}

function panelEl(doc, citationId) {
  const p = new El('div');
  p.className = 'vcite-panel';
  p.id = `panel-${citationId}`;
  doc.body.appendChild(p);
  return p;
}

async function makeCitation(overrides = {}) {
  const defaults = {
    vcite: '1.0',
    id: 'test-verify-001',
    source: new VCiteSource({
      title: 'Test Paper',
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

describe('verifyCitationOffline', () => {
  it('returns verified status for a valid citation', async () => {
    const c = await makeCitation();
    const res = await verifyCitationOffline(c);
    assert.equal(res.status, 'verified');
    assert.equal(res.internalHashValid, true);
    assert.equal(res.claimed, c.target.hash);
    assert.equal(res.recomputed, c.target.hash);
  });

  it('returns internal-mismatch for tampered text', async () => {
    const c = await makeCitation();
    c.target.text_exact = 'exactly 43%';
    const res = await verifyCitationOffline(c);
    assert.equal(res.status, 'internal-mismatch');
    assert.equal(res.internalHashValid, false);
    assert.notEqual(res.recomputed, res.claimed);
  });

  it('returns internal-mismatch for zeroed claimed hash', async () => {
    const c = await makeCitation();
    c.target.hash =
      'sha256:0000000000000000000000000000000000000000000000000000000000000000';
    const res = await verifyCitationOffline(c);
    assert.equal(res.status, 'internal-mismatch');
  });
});

describe('findCitationsInDocument', () => {
  it('parses a single VCiteCitation object', async () => {
    const doc = new DocStub();
    const c = await makeCitation();
    scriptBlock(doc, JSON.stringify(c.toJsonld()));
    const found = findCitationsInDocument(doc);
    assert.equal(found.length, 1);
    assert.equal(found[0].id, c.id);
  });

  it('parses an array of VCiteCitations', async () => {
    const doc = new DocStub();
    const c1 = await makeCitation({ id: 'a' });
    const c2 = await makeCitation({ id: 'b' });
    scriptBlock(doc, JSON.stringify([c1.toJsonld(), c2.toJsonld()]));
    const found = findCitationsInDocument(doc);
    assert.deepEqual(found.map(f => f.id).sort(), ['a', 'b']);
  });

  it('ignores non-VCite JSON-LD blocks', () => {
    const doc = new DocStub();
    scriptBlock(doc, JSON.stringify({ '@type': 'Article', headline: 'x' }));
    assert.equal(findCitationsInDocument(doc).length, 0);
  });

  it('skips malformed JSON without throwing', () => {
    const doc = new DocStub();
    scriptBlock(doc, '{not-valid-json');
    assert.equal(findCitationsInDocument(doc).length, 0);
  });
});

describe('attachVerifyButtons', () => {
  it('attaches one button per matched panel', async () => {
    const doc = new DocStub();
    const c = await makeCitation({ id: 'cc-1' });
    scriptBlock(doc, JSON.stringify(c.toJsonld()));
    panelEl(doc, 'cc-1');
    const n = attachVerifyButtons({ document: doc });
    assert.equal(n, 1);
    const panel = doc.querySelector('.vcite-panel');
    assert.ok(panel.querySelector('.vcite-reverify'));
    assert.ok(panel.querySelector('.vcite-reverify-btn'));
  });

  it('is idempotent -- calling twice does not duplicate', async () => {
    const doc = new DocStub();
    const c = await makeCitation({ id: 'cc-2' });
    scriptBlock(doc, JSON.stringify(c.toJsonld()));
    panelEl(doc, 'cc-2');
    attachVerifyButtons({ document: doc });
    attachVerifyButtons({ document: doc });
    const panel = doc.querySelector('.vcite-panel');
    const wraps = panel.querySelectorAll('.vcite-reverify');
    assert.equal(wraps.length, 1);
  });

  it('skips panels without a matching citation', async () => {
    const doc = new DocStub();
    const c = await makeCitation({ id: 'cc-3' });
    scriptBlock(doc, JSON.stringify(c.toJsonld()));
    panelEl(doc, 'cc-3');
    panelEl(doc, 'orphan');
    const n = attachVerifyButtons({ document: doc });
    assert.equal(n, 1);
  });

  it('click renders a verified result', async () => {
    const doc = new DocStub();
    const c = await makeCitation({ id: 'cc-4' });
    scriptBlock(doc, JSON.stringify(c.toJsonld()));
    panelEl(doc, 'cc-4');
    let received;
    attachVerifyButtons({
      document: doc,
      onResult: (res) => { received = res; },
    });
    const btn = doc.querySelector('.vcite-reverify-btn');
    await btn.dispatch('click');
    assert.equal(received.status, 'verified');
    const result = doc.querySelector('.vcite-reverify-result');
    assert.equal(result.hidden, false);
    assert.ok(result.className.includes('vcite-reverify-result--ok'));
    assert.ok(result.textContent.includes('Fingerprint re-verified'));
  });

  it('click on tampered citation renders mismatch', async () => {
    const doc = new DocStub();
    const c = await makeCitation({ id: 'cc-5' });
    const bad = c.toJsonld();
    bad.target.text_exact = 'exactly 43%';
    scriptBlock(doc, JSON.stringify(bad));
    panelEl(doc, 'cc-5');
    let received;
    attachVerifyButtons({
      document: doc,
      onResult: (res) => { received = res; },
    });
    const btn = doc.querySelector('.vcite-reverify-btn');
    await btn.dispatch('click');
    assert.equal(received.status, 'internal-mismatch');
    const result = doc.querySelector('.vcite-reverify-result');
    assert.ok(result.className.includes('vcite-reverify-result--fail'));
    assert.ok(result.textContent.includes('Fingerprint mismatch'));
  });
});

// Test-vector interop (spec section 5.3, SV1-SV4).
// Parses test-suite/vectors.yaml with a tiny stdlib-only reader -- no
// yaml dependency. The reader handles the subset actually used in the
// spec_vectors block: sequence of maps with double-quoted string scalars.

function loadSpecVectors(yamlText) {
  const lines = yamlText.split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length && !lines[i].startsWith('spec_vectors:')) i++;
  i++;
  let current = null;
  while (i < lines.length) {
    const line = lines[i];
    if (/^[A-Za-z_]/.test(line)) break;
    const itemMatch = line.match(/^\s+-\s+id:\s*(\S+)\s*$/);
    if (itemMatch) {
      if (current) out.push(current);
      current = { id: itemMatch[1] };
      i++;
      continue;
    }
    if (!current) { i++; continue; }
    const kv = line.match(/^\s+([a-z_]+):\s*(.*)$/);
    if (kv) {
      const key = kv[1];
      let raw = kv[2].trim();
      if (raw.startsWith('"') && raw.endsWith('"')) {
        raw = JSON.parse(raw);
      }
      current[key] = raw;
    }
    i++;
  }
  if (current) out.push(current);
  return out;
}

describe('Test-vector interop (spec section 5.3)', () => {
  it('parses SV1-SV4 from test-suite/vectors.yaml', () => {
    const yaml = fs.readFileSync(VECTORS_PATH, 'utf8');
    const vectors = loadSpecVectors(yaml);
    const ids = vectors.map(v => v.id);
    assert.deepEqual(ids.slice(0, 4), ['SV1', 'SV2', 'SV3', 'SV4']);
  });

  it('computeHash matches every SV1-SV4 expected hash', async () => {
    const yaml = fs.readFileSync(VECTORS_PATH, 'utf8');
    const vectors = loadSpecVectors(yaml).slice(0, 4);
    for (const v of vectors) {
      const h = await computeHash(v.text_exact, v.text_before, v.text_after);
      assert.equal(
        h,
        v.expected_hash,
        `${v.id}: got ${h} expected ${v.expected_hash}`,
      );
    }
  });

  it('VCiteTarget.create() auto-hash matches SV1-SV4', async () => {
    const yaml = fs.readFileSync(VECTORS_PATH, 'utf8');
    const vectors = loadSpecVectors(yaml).slice(0, 4);
    for (const v of vectors) {
      const t = await VCiteTarget.create({
        text_exact: v.text_exact,
        text_before: v.text_before,
        text_after: v.text_after,
      });
      assert.equal(t.hash, v.expected_hash, `${v.id}`);
    }
  });

  it('VCiteCitation.verify() returns true for SV1-SV4', async () => {
    const yaml = fs.readFileSync(VECTORS_PATH, 'utf8');
    const vectors = loadSpecVectors(yaml).slice(0, 4);
    for (const v of vectors) {
      const t = await VCiteTarget.create({
        text_exact: v.text_exact,
        text_before: v.text_before,
        text_after: v.text_after,
      });
      const c = new VCiteCitation({
        vcite: '1.0',
        id: `spec-${v.id}`,
        source: new VCiteSource({ title: `spec vector ${v.id}` }),
        target: t,
        relation: 'supports',
        captured_at: '2026-04-22T00:00:00Z',
        captured_by: 'author',
      });
      assert.equal(await c.verify(), true, `${v.id} verify`);
      const res = await verifyCitationOffline(c);
      assert.equal(res.status, 'verified', `${v.id} verifyOffline`);
    }
  });
});
