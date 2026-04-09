/**
 * VCITE SHA-256 Hash -- Standalone ES Module Reference Implementation
 *
 * Computes passage fingerprints per VCITE spec section 5. The hash algorithm:
 * 1. Normalize each segment: NFC unicode, collapse whitespace, trim
 * 2. Pad context (text_before, text_after) to exactly 50 code points
 * 3. Concatenate: pad(before) + "|" + normalize(exact) + "|" + pad(after)
 * 4. SHA-256 the UTF-8 bytes, output as "sha256:" + lowercase hex
 *
 * Supports both Node.js (crypto module) and browsers (Web Crypto API).
 * Zero external dependencies.
 */

/** Context window size in Unicode code points (spec section 5.1). */
const CONTEXT_LEN = 50;

/**
 * NFC normalize and collapse ASCII whitespace runs to a single space.
 * Per spec: only U+0009 (tab), U+000A (LF), U+000D (CR), U+0020 (space)
 * are collapsed. Non-breaking space (U+00A0) and other Unicode whitespace
 * are intentionally preserved.
 *
 * @param {string} s
 * @returns {string}
 */
export function normalizeSegment(s) {
  let normalized = s.normalize('NFC');
  normalized = normalized.replace(/[\t\n\r ]+/g, ' ');
  return normalized.trim();
}

/**
 * Pad or truncate a context string to exactly `length` Unicode code points.
 * Uses Array.from() for multi-byte character safety (emoji, CJK, etc.).
 *
 * @param {string} s
 * @param {number} [length=50]
 * @returns {string}
 */
export function padContext(s, length = CONTEXT_LEN) {
  const chars = Array.from(s);
  if (chars.length >= length) {
    return chars.slice(0, length).join('');
  }
  return chars.join('') + ' '.repeat(length - chars.length);
}

/**
 * Build the canonical hash input string from the three segments.
 * Format: pad(normalize(before)) + "|" + normalize(exact) + "|" + pad(normalize(after))
 *
 * @param {string} textExact
 * @param {string} [textBefore='']
 * @param {string} [textAfter='']
 * @returns {string}
 */
export function buildHashInput(textExact, textBefore = '', textAfter = '') {
  const before = padContext(normalizeSegment(textBefore));
  const exact = normalizeSegment(textExact);
  const after = padContext(normalizeSegment(textAfter));
  return `${before}|${exact}|${after}`;
}

/**
 * Convert an ArrayBuffer to a lowercase hex string.
 * @param {ArrayBuffer} buffer
 * @returns {string}
 */
function bufferToHex(buffer) {
  const bytes = new Uint8Array(buffer);
  return Array.from(bytes)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Compute SHA-256 digest of a UTF-8 string.
 * Uses Web Crypto API (Node 18+ and browsers) with Node.js crypto fallback.
 *
 * @param {string} input - UTF-8 string to hash
 * @returns {Promise<string>} lowercase hex digest
 */
async function sha256(input) {
  // Prefer Web Crypto API (available in browsers and Node 18+)
  if (typeof globalThis.crypto !== 'undefined' && globalThis.crypto.subtle) {
    const encoded = new TextEncoder().encode(input);
    const hashBuffer = await globalThis.crypto.subtle.digest('SHA-256', encoded);
    return bufferToHex(hashBuffer);
  }

  // Fall back to Node.js crypto module
  const { createHash } = await import('node:crypto');
  return createHash('sha256').update(input, 'utf8').digest('hex');
}

/**
 * Compute the VCITE passage fingerprint (async, cross-platform).
 *
 * @param {string} textExact - The verbatim cited passage
 * @param {string} [textBefore=''] - Up to 50 chars before the passage
 * @param {string} [textAfter=''] - Up to 50 chars after the passage
 * @returns {Promise<string>} "sha256:" + hex digest
 */
export async function computeHash(textExact, textBefore = '', textAfter = '') {
  const input = buildHashInput(textExact, textBefore, textAfter);
  const digest = await sha256(input);
  return `sha256:${digest}`;
}
