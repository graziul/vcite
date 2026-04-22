/**
 * VCITE data model (spec section 4) -- JavaScript port of the Python
 * reference implementation in implementations/python/vcite/models.py.
 *
 * Provides VCiteSource, VCiteTarget, VCiteCitation. The Citation class
 * offers verify(), conformanceLevel, toDict(), toJsonld(), fromDict().
 *
 * Zero external dependencies. Uses hash.mjs for passage fingerprinting.
 */

import { computeHash } from './hash.mjs';

/** Controlled relation vocabulary (spec section 4.4). */
export const VALID_RELATIONS = new Set([
  'supports',
  'contradicts',
  'defines',
  'quantifies',
  'contextualizes',
  'method',
  'cautions',
]);

/** JSON-LD context URI (spec section 6.1). */
export const JSONLD_CONTEXT = 'https://vcite.pub/ns/v1/';

/**
 * Bibliographic source metadata (spec section 4.2).
 */
export class VCiteSource {
  /**
   * @param {object} fields
   * @param {string} fields.title
   * @param {string[]} [fields.authors=[]]
   * @param {number|null} [fields.year=null]
   * @param {string|null} [fields.doi=null]
   * @param {string|null} [fields.url=null]
   * @param {string|null} [fields.archive_url=null]
   * @param {string|null} [fields.venue=null]
   * @param {string|null} [fields.source_type=null]
   */
  constructor({
    title,
    authors = [],
    year = null,
    doi = null,
    url = null,
    archive_url = null,
    venue = null,
    source_type = null,
  } = {}) {
    this.title = title;
    this.authors = authors;
    this.year = year;
    this.doi = doi;
    this.url = url;
    this.archive_url = archive_url;
    this.venue = venue;
    this.source_type = source_type;
  }

  /**
   * Return a plain object with null/undefined fields dropped.
   * Matches Python's asdict() + _strip_none behavior.
   * @returns {object}
   */
  toDict() {
    return _stripNone({
      title: this.title,
      authors: this.authors,
      year: this.year,
      doi: this.doi,
      url: this.url,
      archive_url: this.archive_url,
      venue: this.venue,
      source_type: this.source_type,
    });
  }
}

/**
 * Passage location and verification data (spec section 4.3).
 *
 * The hash is computed automatically when not provided. Use the async
 * factory create() to build a target with auto-computed hash; the
 * constructor itself cannot be async, so a blank hash remains blank
 * unless create() is used.
 */
export class VCiteTarget {
  /**
   * @param {object} fields
   * @param {string} fields.text_exact
   * @param {string} [fields.hash=''] - computed by create() if empty
   * @param {string} [fields.text_before='']
   * @param {string} [fields.text_after='']
   * @param {number|null} [fields.char_start=null]
   * @param {number|null} [fields.char_end=null]
   * @param {string|null} [fields.page_ref=null]
   * @param {string|null} [fields.section=null]
   * @param {string|null} [fields.fragment_url=null]
   */
  constructor({
    text_exact,
    hash = '',
    text_before = '',
    text_after = '',
    char_start = null,
    char_end = null,
    page_ref = null,
    section = null,
    fragment_url = null,
  } = {}) {
    this.text_exact = text_exact;
    this.hash = hash;
    this.text_before = text_before;
    this.text_after = text_after;
    this.char_start = char_start;
    this.char_end = char_end;
    this.page_ref = page_ref;
    this.section = section;
    this.fragment_url = fragment_url;
  }

  /**
   * Async factory. Auto-computes hash if not provided, matching the
   * Python __post_init__ behavior.
   * @param {object} fields - same shape as constructor
   * @returns {Promise<VCiteTarget>}
   */
  static async create(fields) {
    const t = new VCiteTarget(fields);
    if (!t.hash) {
      t.hash = await computeHash(t.text_exact, t.text_before, t.text_after);
    }
    return t;
  }

  toDict() {
    return _stripNone({
      text_exact: this.text_exact,
      hash: this.hash,
      text_before: this.text_before,
      text_after: this.text_after,
      char_start: this.char_start,
      char_end: this.char_end,
      page_ref: this.page_ref,
      section: this.section,
      fragment_url: this.fragment_url,
    });
  }
}

/**
 * A single VCITE citation object (spec section 4.1).
 */
export class VCiteCitation {
  /**
   * @param {object} fields
   * @param {string} fields.vcite - spec version, e.g. "1.0"
   * @param {string} fields.id
   * @param {VCiteSource|object} fields.source
   * @param {VCiteTarget|object} fields.target
   * @param {string} fields.relation
   * @param {string} fields.captured_at - ISO 8601 string
   * @param {string} fields.captured_by - "author" | "tool" | "model" (SPEC §4.1)
   * @param {object|null} [fields.enrichment=null]
   */
  constructor({
    vcite,
    id,
    source,
    target,
    relation,
    captured_at,
    captured_by,
    enrichment = null,
  } = {}) {
    // Coerce plain objects to class instances (matches Python from_dict).
    this.vcite = vcite;
    this.id = id;
    this.source = source instanceof VCiteSource ? source : new VCiteSource(source);
    this.target = target instanceof VCiteTarget ? target : new VCiteTarget(target);
    this.relation = relation;
    this.captured_at = captured_at;
    this.captured_by = captured_by;
    this.enrichment = enrichment;

    // Validate relation (same rule as Python).
    if (!VALID_RELATIONS.has(this.relation) && !this.relation.startsWith('x-')) {
      throw new Error(`Invalid relation: ${this.relation}`);
    }
    // Validate captured_by (SPEC §4.1: author | tool | model).
    if (
      this.captured_by !== 'author' &&
      this.captured_by !== 'tool' &&
      this.captured_by !== 'model'
    ) {
      throw new Error(
        `captured_by must be 'author', 'tool', or 'model'; got: ${this.captured_by}`,
      );
    }
  }

  /**
   * Serialize to a plain object with null/undefined fields stripped.
   * Mirrors Python to_dict().
   * @returns {object}
   */
  toDict() {
    return _stripNone({
      vcite: this.vcite,
      id: this.id,
      source: this.source.toDict(),
      target: this.target.toDict(),
      relation: this.relation,
      captured_at: this.captured_at,
      captured_by: this.captured_by,
      enrichment: this.enrichment,
    });
  }

  /** JSON string form. */
  toJson(indent = 2) {
    return JSON.stringify(this.toDict(), null, indent);
  }

  /** JSON-LD form with @context and @type. */
  toJsonld() {
    const d = this.toDict();
    d['@context'] = JSONLD_CONTEXT;
    d['@type'] = 'VCiteCitation';
    return d;
  }

  /**
   * Deserialize from a plain object (e.g. parsed JSON or JSON-LD).
   * Strips JSON-LD keys (@context, @type) if present. Tolerates both
   * VCiteObject and VCiteCitation @type values.
   * @param {object} data
   * @returns {VCiteCitation}
   */
  static fromDict(data) {
    const {
      '@context': _ctx,
      '@type': _type,
      source: sourceData,
      target: targetData,
      vcite,
      id,
      relation,
      captured_at,
      captured_by,
      enrichment = null,
    } = data;
    return new VCiteCitation({
      vcite,
      id,
      source: new VCiteSource(sourceData || {}),
      target: new VCiteTarget(targetData || {}),
      relation,
      captured_at,
      captured_by,
      enrichment,
    });
  }

  static fromJson(jsonStr) {
    return VCiteCitation.fromDict(JSON.parse(jsonStr));
  }

  /**
   * Recompute the hash over target.text_before/exact/after and compare
   * against target.hash. Async because the underlying SHA-256 uses
   * Web Crypto (subtle.digest is async).
   * @returns {Promise<boolean>}
   */
  async verify() {
    const expected = await computeHash(
      this.target.text_exact,
      this.target.text_before,
      this.target.text_after,
    );
    return this.target.hash === expected;
  }

  /**
   * Conformance level (1, 2, or 3), mirroring Python conformance_level.
   *   L1: text_exact + hash (minimal)
   *   L2: L1 + text_before or text_after + source URL/DOI
   *   L3: L2 + archive_url + fragment_url
   * @returns {number}
   */
  get conformanceLevel() {
    const hasL3 =
      Boolean(this.source.archive_url) && Boolean(this.target.fragment_url);
    const hasContext =
      Boolean(this.target.text_before) || Boolean(this.target.text_after);
    const hasSourceUrl = Boolean(this.source.doi) || Boolean(this.source.url);
    const hasL2 = hasContext && hasSourceUrl;

    if (hasL2 && hasL3) return 3;
    if (hasL2) return 2;
    return 1;
  }
}

/**
 * Recursively drop keys whose value is null or undefined. Arrays are
 * preserved (including empty arrays) to match Python behavior for
 * default_factory=list fields like authors.
 * @param {any} obj
 * @returns {any}
 */
function _stripNone(obj) {
  if (obj === null || obj === undefined) return obj;
  if (Array.isArray(obj)) {
    return obj.map(_stripNone);
  }
  if (typeof obj === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(obj)) {
      if (v === null || v === undefined) continue;
      out[k] = _stripNone(v);
    }
    return out;
  }
  return obj;
}
