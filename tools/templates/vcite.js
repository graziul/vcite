/* VCITE toggle — expand/collapse evidence panels.
 *
 * Only one panel is open at a time (accordion behavior).
 * Called from onclick handlers on .vcite-mark and .vcite-badge elements.
 */
function toggleVcite(el) {
  var id = el.dataset.vcite;
  if (!id && el.previousElementSibling) {
    id = el.previousElementSibling.dataset.vcite;
  }
  var panel = document.getElementById('panel-' + id);
  if (!panel) return;
  document.querySelectorAll('.vcite-panel.open').forEach(function (p) {
    if (p !== panel) p.classList.remove('open');
  });
  panel.classList.toggle('open');
}
