// Comeback Buddy: the chat screen. Everything the model says is added with textContent,
// never as HTML, and there are no inline scripts (CSP).
(function () {
  var root = document.querySelector('[data-ask]');
  if (!root) return;
  var log = root.querySelector('#chat-log');
  var form = root.querySelector('#chat-form');
  var input = root.querySelector('#chat-input');
  var send = root.querySelector('#chat-send');
  var suggest = root.querySelector('#suggest');

  function bubble(kind, text) {
    var d = document.createElement('div');
    d.className = 'msg ' + kind;
    d.textContent = text;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }

  function post(url, body) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) {
      if (r.status === 401) { window.location = '/login'; throw new Error('login'); }
      if (!r.ok) throw new Error('http ' + r.status);
      return r.json();
    });
  }

  function steps(list) {
    (list || []).forEach(function (s) {
      var d = document.createElement('div');
      d.className = 'step';
      d.textContent = '✓ ' + s.label;
      log.appendChild(d);
    });
  }

  function confirmCard(p) {
    var card = document.createElement('div');
    card.className = 'confirm-card';
    var title = document.createElement('b');
    title.textContent = 'Add this to your journal?';
    var text = document.createElement('p');
    text.textContent = p.text;
    var row = document.createElement('div');
    row.className = 'actions';
    var yes = document.createElement('button');
    yes.type = 'button'; yes.className = 'terra'; yes.textContent = 'Confirm';
    var no = document.createElement('button');
    no.type = 'button'; no.className = 'ghost'; no.textContent = 'Cancel';
    row.appendChild(yes); row.appendChild(no);
    card.appendChild(title); card.appendChild(text); card.appendChild(row);
    log.appendChild(card);
    log.scrollTop = log.scrollHeight;

    function done(msg) {
      card.replaceChildren();
      var d = document.createElement('p');
      d.className = 'note';
      d.textContent = msg;
      card.appendChild(d);
    }
    yes.addEventListener('click', function () {
      yes.disabled = no.disabled = true;
      post('/ask/confirm', { id: p.id }).then(function (r) {
        done(r.ok ? 'Saved to your journal: ' + r.line : (r.error || 'Could not save that.'));
      }).catch(function () { done('Something went wrong. Please try again.'); });
    });
    no.addEventListener('click', function () {
      yes.disabled = no.disabled = true;
      post('/ask/cancel', { id: p.id }).then(function () { done('Okay, nothing was saved.'); })
        .catch(function () { done('Okay, nothing was saved.'); });
    });
  }

  function ask(text) {
    text = text.trim();
    if (!text) return;
    if (suggest) suggest.hidden = true;
    bubble('user', text);
    input.value = '';
    input.disabled = send.disabled = true;
    var wait = bubble('bot wait', 'Thinking…');
    post('/ask/send', { message: text }).then(function (r) {
      wait.remove();
      steps(r.steps);
      bubble('bot', r.reply);
      if (r.pending) confirmCard(r.pending);
    }).catch(function () {
      wait.remove();
      bubble('bot', 'Something went wrong. Please try again in a moment.');
    }).then(function () {
      input.disabled = send.disabled = false;
      input.focus();
    });
  }

  form.addEventListener('submit', function (e) { e.preventDefault(); ask(input.value); });
  if (suggest) {
    suggest.addEventListener('click', function (e) {
      var b = e.target.closest('[data-q]');
      if (b) ask(b.getAttribute('data-q'));
    });
  }
})();
