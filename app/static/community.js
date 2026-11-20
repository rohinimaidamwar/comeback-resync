// Community: story filter and the post character counter. No inline scripts (CSP).
(function () {
  var root = document.querySelector('[data-community]');
  if (!root) return;

  // The filter bar only appears when JavaScript can run it.
  var bar = root.querySelector('.filters');
  if (bar) {
    bar.hidden = false;
    var stories = [].slice.call(root.querySelectorAll('.story'));
    var empty = root.querySelector('#no-stories');
    bar.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-filter]');
      if (!btn) return;
      var f = btn.getAttribute('data-filter');
      var shown = 0;
      [].forEach.call(bar.querySelectorAll('[data-filter]'), function (b) {
        b.classList.toggle('on', b === btn);
        b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
      });
      stories.forEach(function (s) {
        var ok = f === 'all' || s.getAttribute('data-circle') === f;
        s.hidden = !ok;
        if (ok) shown++;
      });
      if (empty) empty.hidden = shown !== 0;
    });
  }

  var box = root.querySelector('#post-body');
  var count = root.querySelector('#post-count');
  if (box && count) {
    var max = parseInt(box.getAttribute('maxlength'), 10);
    var update = function () { count.textContent = (max - box.value.length) + ' characters left'; };
    box.addEventListener('input', update);
    update();
  }
})();
