/* page_sidebar.js — the shared page sidebar (spec: docs/README.md › "Page sidebar").
   A sticky frosted panel beside the page: an optional picker on top (Months on History,
   Regions on the Kenya / Sinza / Uganda pages), then "In this report" — numbered section
   links whose highlight follows the section on screen (scroll-spy) — and Back to top.

     PageSidebar.init({
       content:  '.wrap',                       // the page's main container (gets wrapped)
       picker:   null | { label: 'Regions', items: [{ id, label, sub, pct, color, tile }],
                          active: id, onSelect: function (id) {} },
       sections: function () { return [{ el, name, num, color, sub }]; },
       collapseSubs: false   // true: only the current group's sub-items (sub: true) are listed
     });
     PageSidebar.setActive(id);   // picker highlight (e.g. after the page changed region itself)
     PageSidebar.refresh();       // rebuild the section list after the page re-renders
     PageSidebar.headings(sel, wrapSel)  // helper: sections from headings, e.g. ('h2', '.section')

   Styles are injected as a <style> element (not a <link>) on purpose: v5_theme.js only remaps
   in-page <style> rules, so the page's dark palette used here turns light with everything else.
   The aside carries data-export-hide, so the shell's Word/PDF export leaves it out. */
(function (root) {
  'use strict';

  var PALETTE = ['#facc15', '#22d3ee', '#a78bfa', '#fb923c', '#f59e0b', '#34d399', '#f472b6', '#818cf8'];
  var NARROW = '(max-width: 980px)';

  var CSS = [
    '.psb-layout { width: 100%; margin: 0 auto; display: grid; grid-template-columns: 248px minmax(0, 1fr); gap: 1.6rem; align-items: start; }',
    '.psb-layout > .psb-main { margin: 0 !important; max-width: none !important; min-width: 0; }',
    '.psb-target { scroll-margin-top: 1rem; }',
    '.psb-embedded .hsb { position: relative; top: 0; }   /* pinned by transform — the parent page scrolls */',
    '.hsb {',
    '  position: sticky; top: 1rem; z-index: 20; max-height: calc(100vh - 2rem); overflow-y: auto; scrollbar-width: none;',
    '  background-color: rgba(24,27,40,0.52); border: 1px solid #2d3148; border-radius: 18px; padding: 1rem 0.7rem 0.8rem;',
    '  backdrop-filter: blur(16px) saturate(1.15); -webkit-backdrop-filter: blur(16px) saturate(1.15);',
    '  box-shadow: 0 14px 34px rgba(0,0,0,0.32); font-family: inherit; line-height: 1.4; text-align: left;',
    '}',
    '.hsb::-webkit-scrollbar { display: none; }',
    '.hsb[hidden], .hsb-sec[hidden], .hsb-secs-wrap[hidden] { display: none !important; }',
    '.hsb-lbl { font-size: 0.62rem; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; color: #64748b; padding: 0 0.55rem; margin: 0.15rem 0 0.5rem; }',
    '.hsb-div { height: 1px; background: #2d3148; margin: 0.8rem 0.5rem 0.9rem; }',
    '.hsb button { font-family: inherit; border: none; background: transparent; cursor: pointer; text-align: left; margin: 0; }',
    '.hsb button:focus-visible { outline: 2px solid #34d399; outline-offset: -2px; }',
    '.hsb-month {',
    '  display: flex; align-items: center; gap: 0.7rem; width: 100%; padding: 0.55rem; border-radius: 12px; color: #cbd5e1;',
    '  transition: background-color 160ms cubic-bezier(0.16, 1, 0.3, 1), color 160ms cubic-bezier(0.16, 1, 0.3, 1);',
    '}',
    '.hsb-month + .hsb-month { margin-top: 2px; }',
    '.hsb-month:hover { background: #252840; color: #f8fafc; }',
    '.hsb-month.active { background: #252840; color: #f8fafc; box-shadow: inset 0 0 0 1px rgba(148,163,184,0.28); }',
    '.hsb-cal {',
    '  width: 36px; height: 36px; border-radius: 10px; flex-shrink: 0; display: flex; flex-direction: column; align-items: center; justify-content: center;',
    '  background: #171a27; border: 1px solid #2d3148; color: #94a3b8; font-size: 0.6rem; font-weight: 800; line-height: 1.1; letter-spacing: 0.04em;',
    '}',
    '.hsb-cal small { font-size: 0.54rem; font-weight: 700; opacity: 0.75; }',
    '.hsb-month.active .hsb-cal { background: #10b981; border-color: transparent; color: #fff; }',
    '.hsb-m-body { flex: 1; min-width: 0; }',
    '.hsb-m-name { display: block; font-size: 0.86rem; font-weight: 600; }',
    '.hsb-m-sub { display: block; font-size: 0.7rem; color: #64748b; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }',
    '.hsb-meter { display: block; height: 4px; border-radius: 999px; background: #2d3148; margin-top: 0.35rem; overflow: hidden; }',
    '.hsb-meter i { display: block; height: 100%; border-radius: inherit; }',
    '.hsb-secs { position: relative; }',
    '.hsb-ind {',
    '  position: absolute; left: 0; right: 0; top: 0; height: 0; border-radius: 10px; background: #252840; box-shadow: inset 3px 0 0 #34d399;',
    '  transition: transform 320ms cubic-bezier(0.16, 1, 0.3, 1), height 320ms cubic-bezier(0.16, 1, 0.3, 1), opacity 200ms; opacity: 0; pointer-events: none;',
    '}',
    '.hsb-sec {',
    '  position: relative; display: flex; align-items: center; gap: 0.65rem; width: 100%; padding: 0.5rem 0.55rem; border-radius: 10px;',
    '  color: #94a3b8; font-size: 0.82rem; font-weight: 500; transition: color 160ms cubic-bezier(0.16, 1, 0.3, 1);',
    '}',
    '.hsb-sec:hover { color: #e2e8f0; }',
    '.hsb-sec.active { color: #f8fafc; font-weight: 600; }',
    '.hsb-num {',
    '  width: 22px; height: 22px; border-radius: 7px; flex-shrink: 0; display: flex; align-items: center; justify-content: center;',
    '  font-size: 0.68rem; font-weight: 800; color: #0b0d16; opacity: 0.55; transition: opacity 160ms;',
    '}',
    '.hsb-sec.active .hsb-num, .hsb-sec:hover .hsb-num { opacity: 1; }',
    '.hsb-sec-name { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }',
    '.hsb-sec.hsb-sub { padding-left: 1.2rem; font-size: 0.78rem; }',
    '.hsb-sec.hsb-sub .hsb-num { width: 18px; height: 18px; font-size: 0.6rem; border-radius: 6px; }',
    '.hsb-top {',
    '  display: flex; align-items: center; justify-content: center; gap: 0.4rem; width: 100%; margin-top: 0.8rem !important; padding: 0.55rem;',
    '  border-radius: 10px; background: #171a27 !important; border: 1px solid #2d3148 !important; color: #94a3b8; font-size: 0.74rem; font-weight: 600;',
    '}',
    '.hsb-top:hover { color: #f8fafc; border-color: #3d4a5c !important; }',
    '@media (max-width: 980px) {',
    '  .psb-layout { grid-template-columns: minmax(0, 1fr); gap: 1rem; }',
    '  .hsb { top: 0; display: flex; align-items: center; gap: 0.35rem; overflow-x: auto; overflow-y: hidden; max-height: none; padding: 0.45rem; border-radius: 14px; }',
    '  .hsb-lbl, .hsb-m-sub, .hsb-meter, .hsb-ind, .hsb-top, .hsb-cal { display: none; }',
    '  .hsb-div { width: 1px; height: 22px; margin: 0 0.25rem; flex-shrink: 0; }',
    '  .hsb-months, .hsb-secs { display: flex; gap: 0.25rem; flex-shrink: 0; }',
    '  .hsb-month, .hsb-sec { width: auto; flex-shrink: 0; padding: 0.45rem 0.7rem; white-space: nowrap; }',
    '  .hsb-sec.hsb-sub { padding-left: 0.7rem; }',
    '  .hsb-month + .hsb-month { margin-top: 0; }',
    '  .hsb-month.active { background: #10b981; box-shadow: none; color: #fff; }',
    '  .hsb-sec.active { background: #252840; }',
    '  .hsb-sec-name { overflow: visible; }',
    '  .psb-target { scroll-margin-top: 4.2rem; }',
    '}',
    '@media print { .hsb { display: none !important; } .psb-layout { display: block; } }',
    '@media (prefers-reduced-transparency: reduce) { .hsb { background-color: #141824; backdrop-filter: none; -webkit-backdrop-filter: none; } }'
  ].join('\n');

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  var st = { opts: null, aside: null, items: [], spyActive: null, frame: null };

  function injectCss() {
    if (document.getElementById('psb-css')) return;
    var s = document.createElement('style');
    s.id = 'psb-css';
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  // ── Picker (Months / Regions) ──────────────────────────────
  function renderPicker() {
    var p = st.opts.picker, host = st.aside.querySelector('.hsb-months');
    if (!p || !host) return;
    host.innerHTML = p.items.map(function (it) {
      var tile = it.tile || [String(it.label).slice(0, 3).toUpperCase(), ''];
      var pct = Number(it.pct);
      return '<button type="button" class="hsb-month" data-id="' + esc(it.id) + '" aria-pressed="false" title="' + esc(it.title || it.label) + '">'
        + '<span class="hsb-cal">' + esc(tile[0]) + (tile[1] ? '<small>' + esc(tile[1]) + '</small>' : '') + '</span>'
        + '<span class="hsb-m-body"><span class="hsb-m-name">' + esc(it.label) + '</span>'
        + (it.sub ? '<span class="hsb-m-sub">' + esc(it.sub) + '</span>' : '')
        + (isFinite(pct) && it.pct != null
            ? '<span class="hsb-meter"><i style="width:' + Math.max(0, Math.min(100, pct)) + '%;background:' + (it.color || '#34d399') + '"></i></span>' : '')
        + '</span></button>';
    }).join('');
    setActive(p.active);
  }

  function setActive(id) {
    if (!st.aside) return;
    if (st.opts.picker) st.opts.picker.active = id;
    st.aside.querySelectorAll('.hsb-month').forEach(function (b) {
      var on = b.getAttribute('data-id') === String(id);
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  // ── "In this report" + scroll-spy ─────────────────────────
  function refresh() {
    if (!st.aside) return;
    var nav = st.aside.querySelector('.hsb-secs');
    nav.querySelectorAll('.hsb-sec').forEach(function (b) { b.remove(); });
    st.items = []; st.spyActive = null;
    var list = [];
    try { list = (st.opts.sections && st.opts.sections()) || []; } catch (e) { console.error('PageSidebar sections:', e); }
    var n = 0, group = -1;
    list.forEach(function (t) {
      if (!t || !t.el) return;
      var num = t.num != null ? t.num : String(++n);
      var col = t.color || PALETTE[(st.items.length) % PALETTE.length];
      t.el.classList.add('psb-target');
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'hsb-sec' + (t.sub ? ' hsb-sub' : '');
      b.title = t.name;
      b.innerHTML = '<span class="hsb-num" style="background:' + col + '">' + esc(num) + '</span><span class="hsb-sec-name">' + esc(t.name) + '</span>';
      b.addEventListener('click', function () { scrollToEl(t.el); });
      nav.appendChild(b);
      if (!t.sub) group++;
      st.items.push({ btn: b, el: t.el, sub: !!t.sub, group: group });
    });
    st.aside.querySelector('.hsb-secs-wrap').hidden = !st.items.length;
    spy();
  }

  // ── Embedded mode (Streamlit) ──────────────────────────────
  // streamlit_app.py stretches the page's iframe to its full height, so the PARENT page scrolls
  // and this window never does. Then sticky can't pin, and window scroll never fires: measure
  // against the parent's viewport instead, pin the aside with a transform, scroll the parent.
  function embedHost() {
    if (!st.frame) return null;
    if (document.documentElement.scrollHeight > window.innerHeight + 2) return null;   // the page scrolls itself
    try {
      // The host's sticky top bar (Streamlit's .tn-bar) covers the top of the viewport: stay below it.
      var bar = window.parent.document.querySelector('.tn-bar'), inset = bar ? Math.max(0, bar.getBoundingClientRect().bottom) : 0;
      return { frameTop: st.frame.getBoundingClientRect().top, vh: window.parent.innerHeight, inset: inset };
    } catch (e) { return null; }
  }
  function parentScroller() {
    try {
      for (var n = st.frame.parentElement; n; n = n.parentElement) {
        var oy = window.parent.getComputedStyle(n).overflowY;
        if ((oy === 'auto' || oy === 'scroll') && n.scrollHeight > n.clientHeight + 1) return n;
      }
      return window.parent.document.scrollingElement;
    } catch (e) { return null; }
  }
  function pin(host) {   // keep the aside 16px below the top of the parent's viewport, inside its column
    var a = st.aside, lay = a.parentElement;
    var want = -host.frameTop + host.inset + 16 - lay.getBoundingClientRect().top;
    var max = Math.max(0, lay.offsetHeight - a.offsetHeight);
    a.style.transform = 'translateY(' + Math.round(Math.max(0, Math.min(max, want))) + 'px)';
  }
  // Smooth unless the viewer asked for reduced motion.
  function behaviour() { return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'; }
  function scrollToEl(el) {
    var host = embedHost(), sc = host && parentScroller();
    if (!sc) { el.scrollIntoView({ behavior: behaviour(), block: 'start' }); return; }
    sc.scrollBy({ top: host.frameTop + el.getBoundingClientRect().top - host.inset - 16, behavior: behaviour() });
  }

  // The section whose top has passed the upper third of the view is current; at the very
  // bottom the last one wins, so short final sections still light up. Bound DIRECTLY to scroll
  // (a handful of rect reads) — no requestAnimationFrame, which some hosts never run.
  function spy() {
    var items = st.items;
    if (!items.length) return;
    var host = embedHost();
    document.documentElement.classList.toggle('psb-embedded', !!host);
    if (host) pin(host); else if (st.aside.style.transform) st.aside.style.transform = '';
    var vh = host ? host.vh : window.innerHeight, off = host ? host.frameTop : 0;
    var inset = host ? host.inset : 0, line = inset + (vh - inset) * 0.33, cur = items[0];
    items.forEach(function (it) {
      if (it.el.offsetParent !== null && off + it.el.getBoundingClientRect().top <= line) cur = it;
    });
    var atBottom = host ? off + document.documentElement.scrollHeight <= vh + 4
                        : window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
    if (atBottom) {
      for (var i = items.length - 1; i >= 0; i--) if (items[i].el.offsetParent !== null) { cur = items[i]; break; }
    }
    if (cur === st.spyActive && cur.btn.classList.contains('active')) return;
    st.spyActive = cur;
    items.forEach(function (it) {
      if (st.opts.collapseSubs && it.sub) it.btn.hidden = it.group !== cur.group;   // fold other groups' sub-items
      it.btn.classList.toggle('active', it === cur);
      if (it === cur) it.btn.setAttribute('aria-current', 'true'); else it.btn.removeAttribute('aria-current');
    });
    var ind = st.aside.querySelector('.hsb-ind');
    ind.style.transform = 'translateY(' + cur.btn.offsetTop + 'px)';
    ind.style.height = cur.btn.offsetHeight + 'px';
    ind.style.opacity = '1';
    if (window.matchMedia(NARROW).matches) {   // strip layout: keep the active chip in view
      var a = st.aside, bl = cur.btn.offsetLeft, br = bl + cur.btn.offsetWidth;
      if (bl < a.scrollLeft || br > a.scrollLeft + a.clientWidth) a.scrollLeft = bl - 12;
    }
  }

  // Sections from headings: each heading's closest `wrapSel` block (or the heading itself).
  // Names are trimmed at the first " — " so long titles stay short.
  function headings(sel, wrapSel, scope) {
    return Array.prototype.map.call((scope || document).querySelectorAll(sel), function (h) {
      var el = (wrapSel && h.closest(wrapSel)) || h;
      return { el: el, name: h.textContent.replace(/\s+/g, ' ').trim().split(' — ')[0] };
    }).filter(function (t) { return t.name && t.el.offsetParent !== null; });
  }

  function init(opts) {
    if (st.aside) return;   // once per page
    st.opts = opts || {};
    var c = st.opts.content;
    var els = Array.prototype.filter.call(typeof c === 'string' ? document.querySelectorAll(c) : (c && c.nodeType ? [c] : (c || [])), Boolean);
    if (!els.length || !els[0].parentNode) return;
    var content = els[0];
    if (els.length > 1) {   // pages whose sections sit straight in <body>: gather them into one column
      var gap = getComputedStyle(content.parentNode).rowGap, mw0 = getComputedStyle(content).maxWidth;
      content = document.createElement('div');
      content.className = 'psb-wrap';
      content.style.cssText = 'display:flex;flex-direction:column;width:100%;gap:' + (gap && gap !== 'normal' ? gap : '2rem') +
                              (mw0 && mw0 !== 'none' ? ';max-width:' + mw0 : '');
      els[0].parentNode.insertBefore(content, els[0]);
      els.forEach(function (e) { content.appendChild(e); });
    }
    injectCss();

    var layout = document.createElement('div');
    layout.className = 'psb-layout';
    var mw = getComputedStyle(content).maxWidth;   // keep the page's own content width beside the sidebar
    if (mw && mw !== 'none' && /px$/.test(mw)) layout.style.maxWidth = 'calc(' + mw + ' + 248px + 1.6rem)';
    content.parentNode.insertBefore(layout, content);

    var aside = document.createElement('aside');
    aside.className = 'hsb';
    aside.id = 'hsb';
    aside.setAttribute('data-export-hide', '');
    aside.setAttribute('aria-label', st.opts.label || 'Page navigation');
    var p = st.opts.picker;
    aside.innerHTML =
        (p ? '<div class="hsb-lbl">' + esc(p.label) + '</div>'
           + '<div class="hsb-months" role="group" aria-label="' + esc(p.label) + '"></div><div class="hsb-div"></div>' : '')
      + '<div class="hsb-secs-wrap"><div class="hsb-lbl">In this report</div>'
      + '<nav class="hsb-secs" aria-label="Report sections"><span class="hsb-ind"></span></nav></div>'
      + '<button type="button" class="hsb-top">↑ Back to top</button>';
    layout.appendChild(aside);
    layout.appendChild(content);
    content.classList.add('psb-main');
    st.aside = aside;

    aside.querySelector('.hsb-top').addEventListener('click', function () {
      var sc = embedHost() && parentScroller();
      (sc || window).scrollTo({ top: 0, behavior: behaviour() });
    });
    if (p) {
      renderPicker();
      aside.querySelector('.hsb-months').addEventListener('click', function (e) {
        var b = e.target.closest('.hsb-month'); if (!b) return;
        var id = b.getAttribute('data-id');
        setActive(id);
        if (p.onSelect) p.onSelect(id);
      });
    }
    refresh();
    window.addEventListener('scroll', spy, { passive: true });
    try { if (window.frameElement && window.parent !== window) st.frame = window.frameElement; } catch (e) {}
    if (st.frame) {   // embedded (Streamlit): the parent scrolls — capture any scroll in its document
      try {
        window.parent.document.addEventListener('scroll', spy, { capture: true, passive: true });
        window.parent.addEventListener('resize', function () { st.spyActive = null; spy(); });
      } catch (e) {}
    }
    window.addEventListener('resize', function () { st.spyActive = null; spy(); });
  }

  root.PageSidebar = { init: init, refresh: refresh, setActive: setActive, headings: headings, spy: spy,
                       setItems: function (items) { if (st.opts && st.opts.picker) { st.opts.picker.items = items; renderPicker(); } } };
})(window);
