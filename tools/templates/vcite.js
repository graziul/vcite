/* Bundled as an IIFE (option a) because this file is injected inline via
 * <script>; ESM imports are unavailable. The IIFE below mirrors the ESM
 * modules at implementations/javascript/src/{hash,models,verify}.mjs. */

/* VCITE toggle — expand/collapse evidence panels.
 *
 * Panels live in a container at the end of the document to avoid
 * <div>-inside-<p> nesting issues. When toggled, panels are moved
 * to appear right after the paragraph containing the clicked citation.
 *
 * Multi-cite groups: a single <span class="vcite-mark"> carries
 * data-vcite-ids="id1,id2,id3". Clicking the span opens all panels
 * for the group, stacked. Clicking a specific badge opens that badge's
 * panel alongside any other panels in the group that are already open.
 */
function toggleVcite(el) {
  // Determine which IDs this click should toggle.
  // A span wrapper carries data-vcite-ids (all group members).
  // A badge carries data-vcite (its own id) — clicking it should still
  // open the whole group so the reader sees every cited source together.
  var ids = [];
  if (el.dataset.vciteIds) {
    ids = el.dataset.vciteIds.split(',').map(function (s) { return s.trim(); });
  } else if (el.dataset.vcite) {
    // If this is a badge inside a group wrapper, use the group's ids list.
    var groupWrap = el.parentElement && el.parentElement.dataset && el.parentElement.dataset.vciteIds
      ? el.parentElement
      : el.previousElementSibling;
    if (groupWrap && groupWrap.dataset && groupWrap.dataset.vciteIds) {
      ids = groupWrap.dataset.vciteIds.split(',').map(function (s) { return s.trim(); });
    } else {
      ids = [el.dataset.vcite];
    }
  }
  if (ids.length === 0) return;

  var panels = ids
    .map(function (id) { return document.getElementById('panel-' + id); })
    .filter(function (p) { return p; });
  if (panels.length === 0) return;

  // Close any other open panels that aren't in this group
  var selected = {};
  panels.forEach(function (p) { selected[p.id] = true; });
  document.querySelectorAll('.vcite-panel.open').forEach(function (p) {
    if (!selected[p.id]) p.classList.remove('open');
  });

  // If any panel in the group is closed, open all. Otherwise close all.
  var anyClosed = panels.some(function (p) { return !p.classList.contains('open'); });

  if (anyClosed) {
    // Move panels to appear stacked after the enclosing block element
    var block = el.closest('p, li, blockquote, div:not(.vcite-panel):not(.vcite-panels-container):not(.vcite-banner)');
    if (block) {
      var anchor = block;
      panels.forEach(function (p) {
        block.parentNode.insertBefore(p, anchor.nextSibling);
        anchor = p;
      });
    }
    panels.forEach(function (p) { p.classList.add('open'); });
    panels[0].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } else {
    panels.forEach(function (p) { p.classList.remove('open'); });
  }
}

/* ─── VCITE browser-side verify bundle ──────────────────────────────
 *
 * IIFE mirroring src/hash.mjs + src/models.mjs + src/verify.mjs enough
 * to recompute the passage fingerprint in the reader's browser. No
 * network, no trust of the publisher. Attaches a "Verify fingerprint"
 * button to every .vcite-panel on DOMContentLoaded.
 */
(function () {
  var CONTEXT_LEN = 50;

  function normalizeSegment(s) {
    var n = s.normalize('NFC');
    n = n.replace(/[\t\n\r ]+/g, ' ');
    return n.replace(/^\s+|\s+$/g, '');
  }

  function padContext(s, len) {
    len = len || CONTEXT_LEN;
    var chars = Array.from(s);
    if (chars.length >= len) return chars.slice(0, len).join('');
    return chars.join('') + ' '.repeat(len - chars.length);
  }

  function buildHashInput(exact, before, after) {
    return (
      padContext(normalizeSegment(before || '')) +
      '|' +
      normalizeSegment(exact) +
      '|' +
      padContext(normalizeSegment(after || ''))
    );
  }

  function bufferToHex(buffer) {
    var bytes = new Uint8Array(buffer);
    var hex = '';
    for (var i = 0; i < bytes.length; i++) {
      var h = bytes[i].toString(16);
      if (h.length < 2) h = '0' + h;
      hex += h;
    }
    return hex;
  }

  async function computeHash(exact, before, after) {
    var raw = buildHashInput(exact, before || '', after || '');
    if (!(globalThis.crypto && globalThis.crypto.subtle)) {
      throw new Error('Web Crypto API is required for VCITE verification.');
    }
    var enc = new TextEncoder().encode(raw);
    var digest = await globalThis.crypto.subtle.digest('SHA-256', enc);
    return 'sha256:' + bufferToHex(digest);
  }

  function findCitations(doc) {
    var blocks = doc.querySelectorAll('script[type="application/ld+json"]');
    var out = {};
    blocks.forEach(function (b) {
      var parsed;
      try { parsed = JSON.parse(b.textContent || ''); } catch (e) { return; }
      var items = Array.isArray(parsed) ? parsed : [parsed];
      items.forEach(function (item) {
        if (item && typeof item === 'object' && item['@type'] === 'VCiteCitation' && item.id) {
          out[item.id] = item;
        }
      });
    });
    return out;
  }

  async function verifyCitationData(citation) {
    var claimed = (citation.target && citation.target.hash) || '';
    var recomputed = await computeHash(
      citation.target.text_exact,
      citation.target.text_before || '',
      citation.target.text_after || ''
    );
    return {
      status: (claimed && recomputed === claimed) ? 'verified' : 'internal-mismatch',
      recomputed: recomputed,
      claimed: claimed
    };
  }

  function renderResult(container, res) {
    while (container.firstChild) container.removeChild(container.firstChild);
    container.hidden = false;
    if (res.status === 'verified') {
      container.className = 'vcite-reverify-result vcite-reverify-result--ok';
      var msg = document.createElement('span');
      msg.className = 'vcite-reverify-msg';
      msg.textContent = '✓ Fingerprint re-verified in browser (' + res.recomputed + ')';
      container.appendChild(msg);
      return;
    }
    container.className = 'vcite-reverify-result vcite-reverify-result--fail';
    var head = document.createElement('div');
    head.className = 'vcite-reverify-msg';
    head.textContent = '✗ Fingerprint mismatch';
    container.appendChild(head);
    var dl = document.createElement('dl');
    dl.className = 'vcite-reverify-dl';
    function row(label, value) {
      var dt = document.createElement('dt');
      dt.textContent = label;
      var dd = document.createElement('dd');
      var code = document.createElement('code');
      code.textContent = value || '(none)';
      dd.appendChild(code);
      dl.appendChild(dt);
      dl.appendChild(dd);
    }
    row('Claimed', res.claimed);
    row('Recomputed', res.recomputed);
    container.appendChild(dl);
  }

  function attachVerifyButtons(doc) {
    doc = doc || document;
    var citations = findCitations(doc);
    var panels = doc.querySelectorAll('.vcite-panel');
    var attached = 0;
    panels.forEach(function (panel) {
      var pid = panel.id || '';
      var cid = pid.indexOf('panel-') === 0 ? pid.slice('panel-'.length) : '';
      var citation = citations[cid];
      if (!citation) return;
      if (panel.querySelector('.vcite-reverify')) return;

      var wrap = doc.createElement('div');
      wrap.className = 'vcite-reverify';

      var btn = doc.createElement('button');
      btn.type = 'button';
      btn.className = 'vcite-reverify-btn';
      btn.textContent = 'Verify fingerprint';

      var result = doc.createElement('div');
      result.className = 'vcite-reverify-result';
      result.hidden = true;

      btn.addEventListener('click', async function (ev) {
        // Clicking the button must not bubble up to the panel toggle.
        ev.stopPropagation();
        btn.disabled = true;
        var original = btn.textContent;
        btn.textContent = 'Verifying...';
        var res;
        try {
          res = await verifyCitationData(citation);
        } catch (err) {
          res = {
            status: 'internal-mismatch',
            recomputed: '(error)',
            claimed: (citation.target && citation.target.hash) || ''
          };
        }
        renderResult(result, res);
        btn.disabled = false;
        btn.textContent = original;
      });

      wrap.appendChild(btn);
      wrap.appendChild(result);
      panel.appendChild(wrap);
      attached += 1;
    });
    return attached;
  }

  function onReady() { attachVerifyButtons(document); }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }

  // Expose for debugging / re-invocation on dynamically injected panels.
  window.VCITE = window.VCITE || {};
  window.VCITE.attachVerifyButtons = attachVerifyButtons;
  window.VCITE.computeHash = computeHash;
})();
