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
