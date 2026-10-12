/* top_nav.js — makes a horizontal pill-tab bar scroll left ↔ right (spec: docs/README.md › Where changes go).
   Used by streamlit_app.py (top bar, injected into the Streamlit page) and shell.html (.pillnav).

     TopNav.attach(track)   // track = the scrolling element holding the tabs; its parent gets the arrows
     TopNav.reveal(track)   // centre the active tab (.on / .active / [aria-current=page]) — after a rebuild

   Scrolling: mouse wheel (vertical wheel moves the tabs sideways), click-and-drag, touch swipe, a slim
   visible scroll bar, and ‹ › arrow buttons that appear only when there is more to see; the edges fade.
   Also defines .tn-glow — a light travelling round an element's border (the nav bar, the date pill).
   Idempotent: attaching the same track twice is a no-op. */
(function (root) {
  'use strict';

  var CSS = [
    '.tn-arrow { position:absolute; top:50%; z-index:3; width:28px; height:28px; margin-top:-14px; border-radius:50%;',
    '  border:none; display:none; align-items:center; justify-content:center; cursor:pointer; padding:0;',
    '  background:rgba(20,22,31,0.92); color:#e2e8f0; box-shadow:0 2px 8px rgba(0,0,0,0.35);',
    '  font:600 17px/1 system-ui, sans-serif; transition:background .16s, color .16s; }',
    '.tn-arrow:hover { background:#4f46e5; color:#fff; }',
    '.tn-arrow:focus-visible { outline:2px solid #818cf8; outline-offset:2px; }',
    '.tn-arrow.tn-prev { left:2px; } .tn-arrow.tn-next { right:2px; }',
    '.tn-can-l > .tn-prev, .tn-can-r > .tn-next { display:flex; }',
    '.tn-dragging, .tn-dragging * { cursor:grabbing !important; user-select:none !important; }',
    /* visible slim scroll bar under the tabs (only drawn when the tabs overflow) */
    '.tn-scrollable { scrollbar-width:thin; scrollbar-color:#6366f1 rgba(255,255,255,0.08); }',
    '.tn-scrollable::-webkit-scrollbar { display:block; height:5px; }',
    '.tn-scrollable::-webkit-scrollbar-track { background:rgba(255,255,255,0.08); border-radius:999px; margin:0 16px; }',
    '.tn-scrollable::-webkit-scrollbar-thumb { background:#6366f1; border-radius:999px; }',
    '.tn-scrollable::-webkit-scrollbar-thumb:hover { background:#818cf8; }',
    /* .tn-glow: a purple → pink light travelling round the element's border (nav bar, date pill) */
    '@property --tn-glow-a { syntax:"<angle>"; initial-value:0deg; inherits:false; }',
    '.tn-glow { position:relative; }',
    '.tn-glow::after { content:""; position:absolute; inset:0; border-radius:inherit; padding:1.5px; pointer-events:none; z-index:4;',
    '  background:conic-gradient(from var(--tn-glow-a), transparent 0deg 30deg, #a855f7 60deg, #ec4899 80deg, transparent 100deg 210deg,',
    '                            #a855f7 240deg, #ec4899 260deg, transparent 280deg);',
    '  -webkit-mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite:xor;',
    '  mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); mask-composite:exclude;',
    '  animation:tnGlowSpin 5s linear infinite; }',
    '@keyframes tnGlowSpin { to { --tn-glow-a:360deg; } }',
    '@media (prefers-reduced-motion: reduce) { .tn-glow::after { animation:none; } }'
  ].join('\n');

  function injectCss(doc) {
    if (doc.getElementById('tn-css')) return;
    var s = doc.createElement('style'); s.id = 'tn-css'; s.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(s);
  }

  function behaviour(win) {
    try { return win.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'; } catch (e) { return 'auto'; }
  }

  function reveal(track) {
    if (!track) return;
    var a = track.querySelector('.on, .active, [aria-current="page"]');
    if (!a) return;
    var target = a.offsetLeft - (track.clientWidth - a.offsetWidth) / 2;
    track.scrollLeft = Math.max(0, target);
    if (track.__tnUpdate) track.__tnUpdate();
  }

  function attach(track) {
    if (!track || track.__tn) return;
    track.__tn = true;
    var doc = track.ownerDocument, win = doc.defaultView, wrap = track.parentElement;
    injectCss(doc);
    if (win.getComputedStyle(wrap).position === 'static') wrap.style.position = 'relative';
    track.style.overflowX = 'auto';
    track.classList.add('tn-scrollable');   // slim visible scroll bar

    var prev = doc.createElement('button'), next = doc.createElement('button');
    prev.type = next.type = 'button';
    prev.className = 'tn-arrow tn-prev'; next.className = 'tn-arrow tn-next';
    prev.setAttribute('aria-label', 'Scroll tabs left'); next.setAttribute('aria-label', 'Scroll tabs right');
    prev.textContent = '‹'; next.textContent = '›';
    wrap.insertBefore(prev, track); wrap.appendChild(next);

    // Edge fades + arrow visibility follow the scroll position
    function update() {
      var max = track.scrollWidth - track.clientWidth;
      var l = track.scrollLeft > 2, r = track.scrollLeft < max - 2;
      wrap.classList.toggle('tn-can-l', l);
      wrap.classList.toggle('tn-can-r', r);
      var m = (l || r) ? 'linear-gradient(90deg,' + (l ? 'transparent 0,#000 40px' : '#000 0') + ',' +
                         (r ? '#000 calc(100% - 40px),transparent 100%' : '#000 100%') + ')' : '';
      track.style.webkitMaskImage = m; track.style.maskImage = m;
    }
    track.__tnUpdate = update;
    track.addEventListener('scroll', update, { passive: true });
    win.addEventListener('resize', update);

    function page(dir) { track.scrollBy({ left: dir * Math.max(120, track.clientWidth * 0.7), behavior: behaviour(win) }); }
    prev.addEventListener('click', function () { page(-1); });
    next.addEventListener('click', function () { page(1); });

    // Vertical mouse wheel scrolls the tabs sideways (only while there is room to move that way)
    track.addEventListener('wheel', function (e) {
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY) || !e.deltaY) return;   // trackpads already scroll sideways
      var before = track.scrollLeft;
      track.scrollLeft += e.deltaY;
      if (track.scrollLeft !== before) e.preventDefault();
    }, { passive: false });

    // Click-and-drag with the mouse (touch already swipes natively); a real drag cancels the click
    var down = null, dragged = false;
    track.addEventListener('pointerdown', function (e) {
      if (e.pointerType !== 'mouse' || e.button !== 0) return;
      down = { x: e.clientX, left: track.scrollLeft }; dragged = false;
    });
    win.addEventListener('pointermove', function (e) {
      if (!down) return;
      var dx = e.clientX - down.x;
      if (!dragged && Math.abs(dx) > 5) { dragged = true; doc.documentElement.classList.add('tn-dragging'); }
      if (dragged) { track.scrollLeft = down.left - dx; e.preventDefault(); }
    });
    win.addEventListener('pointerup', function () {
      if (!down) return;
      down = null;
      doc.documentElement.classList.remove('tn-dragging');
      if (dragged) setTimeout(function () { dragged = false; }, 0);
    });
    track.addEventListener('click', function (e) {
      if (dragged) { e.preventDefault(); e.stopPropagation(); dragged = false; }
    }, true);
    track.addEventListener('dragstart', function (e) { e.preventDefault(); });   // links would start a native drag

    reveal(track);
    update();
  }

  root.TopNav = { attach: attach, reveal: reveal, injectCss: injectCss };
})(window);
