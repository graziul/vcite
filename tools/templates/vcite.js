/* VCITE toggle — expand/collapse evidence panels.
 *
 * Panels live in a container at the end of the document to avoid
 * <div>-inside-<p> nesting issues. When toggled, the panel is moved
 * to appear right after the paragraph containing the clicked citation.
 */
function toggleVcite(el) {
  var id = el.dataset.vcite;
  if (!id && el.previousElementSibling) {
    id = el.previousElementSibling.dataset.vcite;
  }
  var panel = document.getElementById('panel-' + id);
  if (!panel) return;

  // Close other open panels
  document.querySelectorAll('.vcite-panel.open').forEach(function (p) {
    if (p !== panel) p.classList.remove('open');
  });

  // If opening, move panel to appear after the enclosing block element
  if (!panel.classList.contains('open')) {
    var block = el.closest('p, li, blockquote, div:not(.vcite-panel):not(.vcite-panels-container):not(.vcite-banner)');
    if (block) {
      block.parentNode.insertBefore(panel, block.nextSibling);
    }
  }

  panel.classList.toggle('open');

  // Scroll panel into view if it opened
  if (panel.classList.contains('open')) {
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}
