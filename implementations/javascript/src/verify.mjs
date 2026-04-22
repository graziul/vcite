/**
 * VCITE in-browser verification helpers.
 *
 * Provides:
 *   - verifyCitationOffline(citation)
 *       Recomputes the SHA-256 passage fingerprint and compares it to
 *       the citation's captured hash. No network calls. This implements
 *       spec principle P3: any reader can independently confirm the
 *       snippet matches the captured fingerprint, without trusting the
 *       publisher or any central service.
 *
 *   - findCitationsInDocument(doc)
 *       Reads every <script type="application/ld+json"> block on the
 *       page, collects entries whose @type is "VCiteCitation", and
 *       returns them as parsed VCiteCitation objects.
 *
 *   - attachVerifyButtons({ document, onResult })
 *       Idempotent DOM helper. Finds every .vcite-panel on the page,
 *       matches it to a citation by id, injects a "Verify fingerprint"
 *       button inside the panel, and wires the click handler. Clicking
 *       runs the offline verify and renders pass/fail + recomputed hash
 *       into a .vcite-reverify-result child inside the panel. The new
 *       button is additive -- it does not interfere with toggleVcite.
 */

import { VCiteCitation } from './models.mjs';

/**
 * Recompute the hash and compare. No network, no DOM.
 * @param {VCiteCitation} citation
 * @returns {Promise<{status: string, internalHashValid: boolean,
 *                    recomputed: string, claimed: string, warnings: string[]}>}
 */
export async function verifyCitationOffline(citation) {
  const warnings = [];
  const claimed = citation.target.hash;
  const internalHashValid = await citation.verify();
  // Also capture the recomputed digest for UI display.
  const { computeHash } = await import('./hash.mjs');
  const recomputed = await computeHash(
    citation.target.text_exact,
    citation.target.text_before,
    citation.target.text_after,
  );
  if (!claimed) {
    warnings.push('Citation has no captured hash; cannot compare.');
  }
  return {
    status: internalHashValid ? 'verified' : 'internal-mismatch',
    internalHashValid,
    recomputed,
    claimed,
    warnings,
  };
}

/**
 * Parse all JSON-LD blocks and return VCiteCitation instances.
 * Tolerates three shapes inside a single <script> block:
 *   - a single VCiteCitation object
 *   - an array of VCiteCitation objects
 *   - an object containing nothing VCITE-typed (ignored)
 *
 * @param {Document} [doc=document]
 * @returns {VCiteCitation[]}
 */
export function findCitationsInDocument(doc) {
  if (!doc && typeof document !== 'undefined') doc = document;
  if (!doc) return [];
  const blocks = doc.querySelectorAll('script[type="application/ld+json"]');
  const out = [];
  for (const block of blocks) {
    let parsed;
    try {
      parsed = JSON.parse(block.textContent || '');
    } catch (_) {
      continue;
    }
    const items = Array.isArray(parsed) ? parsed : [parsed];
    for (const item of items) {
      if (!item || typeof item !== 'object') continue;
      if (item['@type'] !== 'VCiteCitation') continue;
      try {
        out.push(VCiteCitation.fromDict(item));
      } catch (_) {
        // Skip malformed entries silently; caller can inspect via
        // attachVerifyButtons' onResult callback instead.
      }
    }
  }
  return out;
}

/**
 * Inject "Verify fingerprint" buttons into each .vcite-panel. Idempotent:
 * calling repeatedly will not duplicate buttons.
 *
 * @param {object} opts
 * @param {Document} [opts.document]
 * @param {(result: object, citation: VCiteCitation, panel: Element) => void} [opts.onResult]
 *   Optional callback invoked after each click's verify completes. Useful
 *   for test harnesses or analytics.
 * @returns {number} Number of buttons newly attached.
 */
export function attachVerifyButtons({ document: doc, onResult } = {}) {
  if (!doc && typeof document !== 'undefined') doc = document;
  if (!doc) return 0;

  const citations = findCitationsInDocument(doc);
  const byId = new Map();
  for (const c of citations) byId.set(c.id, c);

  const panels = doc.querySelectorAll('.vcite-panel');
  let attached = 0;
  for (const panel of panels) {
    // Panel id is "panel-<citation-id>".
    const pid = panel.id || '';
    const cid = pid.startsWith('panel-') ? pid.slice('panel-'.length) : '';
    const citation = byId.get(cid);
    if (!citation) continue;

    // Idempotence guard -- skip if already attached.
    if (panel.querySelector('.vcite-reverify')) continue;

    const wrap = doc.createElement('div');
    wrap.className = 'vcite-reverify';

    const btn = doc.createElement('button');
    btn.type = 'button';
    btn.className = 'vcite-reverify-btn';
    btn.textContent = 'Verify fingerprint';

    const result = doc.createElement('div');
    result.className = 'vcite-reverify-result';
    result.hidden = true;

    btn.addEventListener('click', async (ev) => {
      // Prevent the click from bubbling up to any parent panel toggle.
      ev.stopPropagation();
      btn.disabled = true;
      btn.textContent = 'Verifying...';
      let res;
      try {
        res = await verifyCitationOffline(citation);
      } catch (err) {
        res = {
          status: 'error',
          internalHashValid: false,
          recomputed: '',
          claimed: citation.target.hash || '',
          warnings: [String(err && err.message ? err.message : err)],
        };
      }
      _renderResult(doc, result, res);
      btn.disabled = false;
      btn.textContent = 'Verify fingerprint';
      if (typeof onResult === 'function') {
        try { onResult(res, citation, panel); } catch (_) { /* swallow */ }
      }
    });

    wrap.appendChild(btn);
    wrap.appendChild(result);
    panel.appendChild(wrap);
    attached += 1;
  }
  return attached;
}

/**
 * Render a verify result into the provided container. Green on pass,
 * red on fail. The recomputed and claimed hashes are shown side-by-side
 * when they differ so the reader can inspect exactly what broke.
 * @param {Document} doc
 * @param {Element} container
 * @param {object} res
 */
function _renderResult(doc, container, res) {
  // Clear prior contents.
  while (container.firstChild) container.removeChild(container.firstChild);
  container.hidden = false;

  if (res.status === 'verified') {
    container.className = 'vcite-reverify-result vcite-reverify-result--ok';
    const msg = doc.createElement('span');
    msg.className = 'vcite-reverify-msg';
    // Emoji glyphs are DOM-rendered UI feedback, not code/comments --
    // permitted by the project rule.
    msg.textContent = `✓ Fingerprint re-verified in browser (${res.recomputed})`;
    container.appendChild(msg);
    return;
  }

  container.className = 'vcite-reverify-result vcite-reverify-result--fail';
  const head = doc.createElement('div');
  head.className = 'vcite-reverify-msg';
  head.textContent = '✗ Fingerprint mismatch';
  container.appendChild(head);

  const dl = doc.createElement('dl');
  dl.className = 'vcite-reverify-dl';

  const addRow = (label, value) => {
    const dt = doc.createElement('dt');
    dt.textContent = label;
    const dd = doc.createElement('dd');
    const code = doc.createElement('code');
    code.textContent = value || '(none)';
    dd.appendChild(code);
    dl.appendChild(dt);
    dl.appendChild(dd);
  };
  addRow('Claimed', res.claimed);
  addRow('Recomputed', res.recomputed);
  container.appendChild(dl);

  if (res.warnings && res.warnings.length > 0) {
    const ul = doc.createElement('ul');
    ul.className = 'vcite-reverify-warnings';
    for (const w of res.warnings) {
      const li = doc.createElement('li');
      li.textContent = w;
      ul.appendChild(li);
    }
    container.appendChild(ul);
  }
}
