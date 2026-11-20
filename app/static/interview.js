// Interview prep: tabs, peer filters, and the request dialog. No inline scripts (CSP).
(function () {
  var root = document.querySelector('[data-interview]');
  if (!root) return;

  // Tabs: links work without JavaScript; this just switches instantly.
  var tabs = [].slice.call(root.querySelectorAll('[role="tab"]'));
  var panels = [].slice.call(root.querySelectorAll('[role="tabpanel"]'));
  function show(id) {
    panels.forEach(function (p) { p.hidden = p.id !== id; });
    tabs.forEach(function (t) {
      var on = t.getAttribute('aria-controls') === id;
      t.classList.toggle('on', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
    });
  }
  tabs.forEach(function (t) {
    t.addEventListener('click', function (e) {
      e.preventDefault();
      show(t.getAttribute('aria-controls'));
      if (history.replaceState) history.replaceState(null, '', t.getAttribute('href'));
    });
  });

  // Filters are only shown when JavaScript can run them.
  var bar = root.querySelector('.filters');
  if (bar) {
    bar.hidden = false;
    var peers = [].slice.call(root.querySelectorAll('.peer'));
    var empty = root.querySelector('#no-match');
    bar.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-filter]');
      if (!btn) return;
      var f = btn.getAttribute('data-filter');
      var shown = 0;
      [].forEach.call(bar.querySelectorAll('[data-filter]'), function (b) {
        b.classList.toggle('on', b === btn);
        b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
      });
      peers.forEach(function (p) {
        var ok = f === 'all' || p.getAttribute('data-' + f) === '1';
        p.hidden = !ok;
        if (ok) shown++;
      });
      if (empty) empty.hidden = shown !== 0;
    });
  }

  // Request dialog.
  var dlg = root.querySelector('#request-dialog');
  if (dlg) {
    root.addEventListener('click', function (e) {
      var open = e.target.closest('.req');
      if (open) {
        dlg.querySelector('#req-partner').value = open.getAttribute('data-partner');
        dlg.querySelector('#req-name').textContent = open.getAttribute('data-name');
        if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
        return;
      }
      if (e.target.closest('[data-close]')) {
        if (dlg.close) dlg.close(); else dlg.removeAttribute('open');
      }
    });
  }
})();
