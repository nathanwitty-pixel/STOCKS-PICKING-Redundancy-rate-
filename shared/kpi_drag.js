/* kpi_drag.js — drag any KPI, chart or panel to reorder it within its row / section,
 * remembered per browser. streamlit_app.py inlines this into every dashboard page.
 *
 * Items: elements whose class looks like a block (card, panel, kpi, tile, stat, sec, section,
 * block, chart-wrap, offer, grid …) or that hold a chart <canvas>. Any container with 2+ such
 * children becomes sortable (SortableJS, mouse + touch). Containers can nest: KPI cards move
 * within their row, and the row moves within its section.
 *
 * Left alone: the page sidebar (#hsb), hover popovers, chart menus, <template> content and
 * fixed / absolute overlays. Buttons, links, selects, inputs, tables and the chart canvas
 * itself never start a drag (chart tooltips, sorting and copying keep working). Pressing on text
 * (a value, a name, a title) selects it instead — grab a card by its padding / empty space.
 * On touch, hold briefly to pick up, so swiping still scrolls.
 *
 * Order is saved in localStorage per page + container, keyed by each item's id or title, so
 * a regenerated page keeps the viewer's layout; content a page rebuilds in JS is re-sorted
 * when it reappears. "↺ Reset order" under a container appears once it's been rearranged.
 */
(function () {
  if (window.__kpiDrag) return;
  window.__kpiDrag = true;

  var SORTABLE_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/Sortable/1.15.2/Sortable.min.js';
  var ITEM_TOKEN = /(^|-)(card|panel|kpi|kpis|tile|stat|stats|sec|section|block|chart-wrap|charts|offer|grid\d?)$/;
  var SKIP = '#hsb, .hsb, .sales-popover, .chartsw-menu, template, nav, header, footer';
  var NO_DRAG = 'a, button, select, input, textarea, label, summary, canvas, table, [contenteditable], .chartsw-btn, .kpi-reset';
  var TITLE = 'h1, h2, h3, h4, .card-label, .chart-cap, .block-title, .sec-head, .panel-title, .title, summary';

  // A mouse press right on a word (a KPI value, a shop / bag name, a title) selects text instead of
  // picking the card up — grab cards by their padding / empty space. Touch keeps hold-to-pick-up.
  function onText(evt) {
    if (evt.pointerType === 'touch' || /^touch/.test(evt.type || '')) return false;
    var x = evt.clientX, y = evt.clientY, node, off;
    if (document.caretPositionFromPoint) {
      var p = document.caretPositionFromPoint(x, y); if (!p) return false;
      node = p.offsetNode; off = p.offset;
    } else if (document.caretRangeFromPoint) {
      var c = document.caretRangeFromPoint(x, y); if (!c) return false;
      node = c.startContainer; off = c.startOffset;
    } else return false;
    if (!node || node.nodeType !== 3 || !node.textContent.trim()) return false;
    var r = document.createRange(), len = node.textContent.length;
    for (var i = Math.max(0, off - 1); i <= Math.min(len - 1, off); i++) {   // the characters either side of the caret
      r.setStart(node, i); r.setEnd(node, i + 1);
      var rects = r.getClientRects();
      for (var j = 0; j < rects.length; j++) {
        var b = rects[j];
        if (x >= b.left - 1 && x <= b.right + 1 && y >= b.top - 1 && y <= b.bottom + 1) return true;
      }
    }
    return false;
  }

  function store(key, val) {
    try {
      if (val === undefined) return JSON.parse(localStorage.getItem(key) || 'null');
      if (val === null) localStorage.removeItem(key); else localStorage.setItem(key, JSON.stringify(val));
    } catch (e) { return null; }
  }

  function hash(s) {
    var h = 5381;
    for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
    return (h >>> 0).toString(36);
  }

  function isItem(el) {
    if (el.nodeType !== 1 || /^(SCRIPT|STYLE|LINK|BR|HR|TEMPLATE|BUTTON|CANVAS)$/.test(el.tagName)) return false;
    var hit = false;
    for (var i = 0; i < el.classList.length && !hit; i++) hit = ITEM_TOKEN.test(el.classList[i]);
    if (!hit && !el.querySelector('canvas')) return false;
    if (el.matches(SKIP)) return false;
    var pos = getComputedStyle(el).position;
    return pos !== 'fixed' && pos !== 'absolute';
  }

  function itemKey(el) {
    if (el.id) return '#' + el.id;
    var t = el.querySelector(TITLE);
    var txt = t ? t.textContent.replace(/\s+/g, ' ').trim().toLowerCase().slice(0, 60) : '';
    if (txt) return 'T:' + txt;
    var c = el.querySelector('canvas[id]');
    return c ? 'C:' + c.id : '';
  }

  function items(box) {
    return Array.prototype.filter.call(box.children, function (c) { return c.classList.contains('dnd-item'); });
  }

  // Each item's key; duplicates / blanks fall back to position so the order still restores.
  function keysOf(list) {
    var keys = list.map(itemKey), seen = {};
    var ok = keys.every(function (k) { if (!k || seen[k]) return false; seen[k] = 1; return true; });
    return ok ? keys : list.map(function (_, i) { return 'i' + i; });
  }

  function css() {
    var st = document.createElement('style');
    st.id = 'kpi-drag-css';
    st.textContent =
      '.dnd-box > .dnd-item { cursor: grab; }' +
      '.dnd-box > .dnd-item:active { cursor: grabbing; }' +
      '.dnd-box > .dnd-item table, .dnd-box > .dnd-item canvas { cursor: auto; }' +
      '.dnd-box > .dnd-item :is(h1,h2,h3,h4,p,b,span,td,th,div):not(:has(*)) { cursor: text; }' +
      '.kpi-ghost { opacity: 0.35; outline: 2px dashed rgba(99,102,241,0.7); outline-offset: -2px; }' +
      '.kpi-chosen { box-shadow: 0 12px 32px rgba(0,0,0,0.45) !important; }' +
      'body.kpi-dragging .sales-popover { display: none !important; }' +
      'body.kpi-dragging, body.kpi-dragging * { user-select: none !important; }' +
      '.kpi-reset { display: none; margin: 0.35rem 0; font-family: inherit; font-size: 0.68rem; font-weight: 600;' +
      '  color: #64748b; background: none; border: 0; padding: 0; cursor: pointer; }' +
      '.kpi-reset:hover { color: #a5b4fc; text-decoration: underline; }' +
      '.kpi-reset.on { display: block; }';
    document.head.appendChild(st);
  }

  var boxes = [];   // {el, key, original, sig, reset}

  function setupBox(el, list) {
    list.forEach(function (c) { c.classList.add('dnd-item'); });
    var keys = keysOf(list);
    var b = { el: el, original: keys.slice(), sig: keys.slice().sort().join('|') };
    b.key = 'dnd:' + (document.title || 'page') + ':' + hash((el.id || el.className || el.tagName) + '§' + b.sig);
    b.reset = document.createElement('button');
    b.reset.type = 'button';
    b.reset.className = 'kpi-reset';
    b.reset.textContent = '↺ Reset order';
    b.reset.title = 'Put these back in their original order';
    el.parentNode.insertBefore(b.reset, el.nextSibling);
    b.reset.addEventListener('click', function () { apply(b, b.original); store(b.key, null); sync(b); });
    el.classList.add('dnd-box');
    el.__dnd = b;
    boxes.push(b);
    var saved = store(b.key);
    if (saved && saved.length) apply(b, saved);
    sync(b);

    window.Sortable.create(el, {
      draggable: '.dnd-item',
      animation: 160,
      delay: 180, delayOnTouchOnly: true,
      filter: function (evt, target) {
        var m = target && target.closest ? target.closest(NO_DRAG) : null;
        return !!(m && el.contains(m)) || onText(evt);
      },
      preventOnFilter: false,
      ghostClass: 'kpi-ghost', chosenClass: 'kpi-chosen',
      onStart: function () { document.body.classList.add('kpi-dragging'); },
      onEnd: function () {
        document.body.classList.remove('kpi-dragging');
        store(b.key, keysOf(items(el)));
        sync(b);
        try { window.dispatchEvent(new Event('resize')); } catch (e) {}   // charts + frame height re-fit
      }
    });
  }

  function apply(b, order) {
    var list = items(b.el), keys = keysOf(list), byKey = {};
    list.forEach(function (c, i) { byKey[keys[i]] = c; });
    var anchor = list.length ? list[list.length - 1].nextSibling : null;   // keep non-items (headers) in place
    order.forEach(function (k) { if (byKey[k]) { b.el.insertBefore(byKey[k], anchor); delete byKey[k]; } });
    Object.keys(byKey).forEach(function (k) { b.el.insertBefore(byKey[k], anchor); });
  }

  function sync(b) {
    b.reset.classList.toggle('on', keysOf(items(b.el)).join('|') !== b.original.join('|'));
  }

  function scan() {
    var seen = new Set();
    Array.prototype.forEach.call(document.body.querySelectorAll('*'), function (el) {
      if (seen.has(el.parentElement) || !el.parentElement) return;
      var box = el.parentElement;
      seen.add(box);
      if (/^(TABLE|THEAD|TBODY|TFOOT|TR|UL|OL|SELECT|svg)$/.test(box.tagName)) return;   // rows / lists aren't layout
      if (box.matches(SKIP) || box.closest(SKIP)) return;
      var list = Array.prototype.filter.call(box.children, isItem);
      if (box.__dnd) {                                      // known box: new children → re-mark, re-sort
        list.forEach(function (c) { c.classList.add('dnd-item'); });
        var sig = keysOf(list).slice().sort().join('|');
        if (sig !== box.__dnd.lastSig) {
          box.__dnd.lastSig = sig;
          var saved = store(box.__dnd.key);
          if (saved && sig === box.__dnd.sig) { apply(box.__dnd, saved); sync(box.__dnd); }
        }
        return;
      }
      if (list.length >= 2) setupBox(box, list);
    });
  }

  function init() {
    css();
    scan();
    var t = null;
    new MutationObserver(function (muts) {
      if (document.body.classList.contains('kpi-dragging')) return;
      if (muts.every(function (m) { return m.target.closest && m.target.closest('.dnd-box') && !m.addedNodes.length; })) return;
      clearTimeout(t);
      t = setTimeout(scan, 400);
    }).observe(document.body, { childList: true, subtree: true });
  }

  function boot() {
    // Let the page build its own content (charts, JS-rendered sections) first.
    var go = function () { setTimeout(window.Sortable ? init : load, 300); };
    function load() {
      var s = document.createElement('script');
      s.src = SORTABLE_SRC;
      s.onload = init;
      document.head.appendChild(s);
    }
    if (document.readyState === 'complete') go(); else window.addEventListener('load', go);
  }
  boot();
})();
