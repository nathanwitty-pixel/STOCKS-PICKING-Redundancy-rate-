/* chart_switcher.js — a chart-type menu on every Chart.js chart (spec: docs/chart-switcher.md).
   Load right after Chart.js, before the page creates its charts. It wraps the Chart class to keep
   each chart's original config, then redraws the SAME chart object in place when a type is
   picked, so the page's own references / destroy() / re-renders keep working. */
(function () {
  'use strict';
  var Base = window.Chart;
  if (!Base || Base.__chartSwitch) return;

  var TREEMAP_SRC = 'https://cdn.jsdelivr.net/npm/chartjs-chart-treemap@3/dist/chartjs-chart-treemap.min.js';
  var PALETTE = ['#06b6d4', '#f59e0b', '#8b5cf6', '#10b981', '#ec4899', '#3b82f6', '#ef4444', '#84cc16',
                 '#f97316', '#14b8a6', '#a78bfa', '#94a3b8'];
  var UP = '#10b981', DOWN = '#ef4444', TOTAL = '#3b82f6';

  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }
  };

  // Deep clone of plain objects/arrays; functions, gradients etc. are kept by reference.
  function clone(v) {
    if (Array.isArray(v)) return v.map(clone);
    if (v && typeof v === 'object' && Object.getPrototypeOf(v) === Object.prototype) {
      var o = {};
      for (var k in v) if (Object.prototype.hasOwnProperty.call(v, k)) o[k] = clone(v[k]);
      return o;
    }
    return v;
  }
  var num = function (v) { var n = Number(v); return isFinite(n) ? n : 0; };
  var first = function (c) { return Array.isArray(c) ? c[0] : c; };
  function alpha(col, a) {
    if (typeof col !== 'string') return col;
    var m = col.match(/^#([0-9a-f]{6})$/i);
    if (m) { var n = parseInt(m[1], 16); return 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')'; }
    return col;
  }
  function seriesColor(ds, i) {
    return first(ds.backgroundColor) || first(ds.borderColor) || PALETTE[i % PALETTE.length];
  }

  // ── What the data looks like ──
  function shape(orig) {
    var ds = (orig.data && orig.data.datasets) || [];
    var labels = (orig.data && orig.data.labels) || [];
    var points = ds.some(function (d) { return (d.data || []).some(function (v) { return v && typeof v === 'object'; }); });
    var vals = ds.map(function (d) { return (d.data || []).map(num); });
    var neg = vals.some(function (a) { return a.some(function (v) { return v < 0; }); });
    return { ds: ds, labels: labels, points: points, n: ds.length, nl: labels.length, neg: neg, vals: vals };
  }

  // Slices for pie-like views: 1 series → label × value; 2+ → one slice per series total.
  function slices(s) {
    if (s.n === 1) {
      var bg = s.ds[0].backgroundColor;
      return s.labels.map(function (l, i) {
        return { label: Array.isArray(l) ? l.join(' ') : String(l), v: s.vals[0][i] || 0,
                 c: (Array.isArray(bg) && bg[i]) || PALETTE[i % PALETTE.length] };
      });
    }
    return s.ds.map(function (d, i) {
      return { label: d.label || ('Series ' + (i + 1)), v: s.vals[i].reduce(function (a, b) { return a + b; }, 0),
               c: seriesColor(d, i) };
    });
  }

  var TYPES = [
    { key: 'column',  label: 'Column',         ok: function () { return true; } },
    { key: 'bar',     label: 'Bar',            ok: function () { return true; } },
    { key: 'stacked', label: 'Stacked column', ok: function (s) { return s.n >= 2; } },
    { key: 'line',    label: 'Line',           ok: function () { return true; } },
    { key: 'area',    label: 'Area',           ok: function () { return true; } },
    { key: 'sarea',   label: 'Stacked area',   ok: function (s) { return s.n >= 2; } },
    { key: 'combo',   label: 'Combo',          ok: function (s) { return s.n >= 2; } },
    { key: 'pie',     label: 'Pie',            ok: function (s) { return !s.neg; } },
    { key: 'doughnut',label: 'Doughnut',       ok: function (s) { return !s.neg; } },
    { key: 'polar',   label: 'Polar area',     ok: function (s) { return !s.neg; } },
    { key: 'radar',   label: 'Radar',          ok: function (s) { return s.nl >= 3; } },
    { key: 'funnel',  label: 'Funnel',         ok: function (s) { return !s.neg && slices(s).length >= 2; } },
    { key: 'waterfall', label: 'Waterfall',    ok: function (s) { return s.nl >= 2; } },
    { key: 'treemap', label: 'Treemap',        ok: function (s) { return !s.neg; } }
  ];

  // Value formatter: the chart's own value-axis tick format when it has one.
  function valueFmt(orig) {
    var sc = (orig.options && orig.options.scales) || {};
    var horiz = orig.options && orig.options.indexAxis === 'y';
    var ax = (horiz ? sc.x : sc.y) || sc.y || sc.x || {};
    var cb = ax.ticks && ax.ticks.callback;
    return function (v) {
      if (cb) { try { var r = cb.call({ getLabelForValue: function (x) { return x; } }, v, 0, []); if (r != null && r !== '') return r; } catch (e) {} }
      return Math.round(v).toLocaleString('en-US');
    };
  }
  function genericTooltip(opts, fmtOf) {
    opts.plugins = opts.plugins || {};
    opts.plugins.tooltip = Object.assign({}, opts.plugins.tooltip || {});
    opts.plugins.tooltip.callbacks = { label: function (c) { return ' ' + (c.dataset.label ? c.dataset.label + ': ' : '') + fmtOf(c); } };
  }
  function dropScales(opts) { delete opts.scales; delete opts.indexAxis; }
  function axisOpts(opts) {
    opts.scales = opts.scales || {};
    opts.scales.x = opts.scales.x || {};
    opts.scales.y = opts.scales.y || {};
    return opts.scales;
  }

  // ── Build a config of the chosen type from the ORIGINAL config ──
  function build(key, orig) {
    var o = clone(orig), s = shape(orig), fmt = valueFmt(orig);
    var data = o.data, opts = o.options || (o.options = {});
    var wasHoriz = opts.indexAxis === 'y';
    var cartesian = !orig.type || ['bar', 'line'].indexOf(orig.type) >= 0;
    if (!cartesian) delete opts.scales;               // pie/doughnut/polar/radar → fresh axes
    delete opts.cutout; delete opts.circumference; delete opts.rotation;
    if (wasHoriz && key !== 'bar' && key !== 'funnel') {  // back to vertical: swap the axes back
      var sc0 = opts.scales || {}; opts.scales = Object.assign({}, sc0, { x: sc0.y || {}, y: sc0.x || {} }); delete opts.indexAxis;
    }
    var plain = function (ds, i, t) {                   // one series as a plain bar/line
      delete ds.type; delete ds.stack; delete ds.fill; delete ds.yAxisID; delete ds.xAxisID;
      var col = seriesColor(orig.data.datasets[i], i);
      if (t === 'line') {
        ds.borderColor = first(ds.borderColor) || col;
        ds.backgroundColor = alpha(col, 0.25);
        ds.pointRadius = ds.pointRadius == null ? 3 : ds.pointRadius;
        ds.tension = ds.tension == null ? 0.3 : ds.tension;
        ds.borderWidth = 2;
      } else if (orig.type === 'line' || ds.backgroundColor == null) {
        ds.backgroundColor = alpha(col, 0.85);
      }
      return ds;
    };
    var sc;
    switch (key) {
      case 'column': case 'stacked': case 'bar':
        data.datasets.forEach(function (d, i) { plain(d, i, 'bar'); d.borderRadius = d.borderRadius == null ? 4 : d.borderRadius; });
        sc = axisOpts(opts);
        sc.x.stacked = sc.y.stacked = key === 'stacked';
        if (key === 'bar') {
          if (!wasHoriz) { var t = sc.x; sc.x = sc.y; sc.y = t; }
          opts.indexAxis = 'y';
          sc.x.stacked = sc.y.stacked = false;
        }
        if (key === 'bar') genericTooltip(opts, function (c) { return fmt(c.parsed.x); });
        return { type: 'bar', data: data, options: opts };
      case 'line': case 'area': case 'sarea':
        data.datasets.forEach(function (d, i) {
          plain(d, i, 'line');
          d.fill = key === 'line' ? false : (key === 'sarea' && i > 0 ? '-1' : 'origin');
        });
        sc = axisOpts(opts);
        sc.x.stacked = false; sc.y.stacked = key === 'sarea';
        return { type: 'line', data: data, options: opts };
      case 'combo':
        data.datasets.forEach(function (d, i) {
          plain(d, i, i === 0 ? 'bar' : 'line');
          d.type = i === 0 ? 'bar' : 'line';
          d.order = i === 0 ? 2 : 1;
          if (i > 0) d.fill = false;
        });
        sc = axisOpts(opts); sc.x.stacked = sc.y.stacked = false;
        return { type: 'bar', data: data, options: opts };
      case 'pie': case 'doughnut': case 'polar':
        var sl = slices(s);
        dropScales(opts);
        opts.plugins = opts.plugins || {};
        opts.plugins.legend = Object.assign({ display: true, position: 'right' }, opts.plugins.legend || {}, { display: true });
        genericTooltip(opts, function (c) {
          var tot = sl.reduce(function (a, x) { return a + x.v; }, 0) || 1;
          return fmt(c.raw) + ' (' + Math.round(c.raw / tot * 100) + '%)';
        });
        if (key === 'polar') opts.scales = { r: { grid: { color: 'rgba(148,163,184,0.2)' }, ticks: { display: false } } };
        if (key === 'doughnut') opts.cutout = '58%';
        return { type: key === 'polar' ? 'polarArea' : key,
                 data: { labels: sl.map(function (x) { return x.label; }),
                         datasets: [{ data: sl.map(function (x) { return x.v; }),
                                      backgroundColor: sl.map(function (x) { return key === 'polar' ? alpha(x.c, 0.7) : x.c; }),
                                      borderColor: 'rgba(15,17,23,0.9)', borderWidth: 2 }] },
                 options: opts };
      case 'radar':
        data.datasets.forEach(function (d, i) {
          plain(d, i, 'line'); d.fill = true; d.backgroundColor = alpha(seriesColor(orig.data.datasets[i], i), 0.2);
        });
        dropScales(opts);
        opts.scales = { r: { grid: { color: 'rgba(148,163,184,0.2)' }, angleLines: { color: 'rgba(148,163,184,0.2)' },
                             ticks: { display: false }, pointLabels: { font: { size: 11 } } } };
        genericTooltip(opts, function (c) { return fmt(c.raw); });
        return { type: 'radar', data: data, options: opts };
      case 'funnel':
        var fs = slices(s).slice().sort(function (a, b) { return b.v - a.v; });
        dropScales(opts);
        opts.indexAxis = 'y';
        opts.scales = { x: { display: false, stacked: false }, y: { grid: { display: false } } };
        opts.plugins = opts.plugins || {}; opts.plugins.legend = { display: false };
        genericTooltip(opts, function (c) { return fmt(fs[c.dataIndex].v); });
        return { type: 'bar',
                 data: { labels: fs.map(function (x) { return x.label; }),
                         datasets: [{ label: '', data: fs.map(function (x) { return [-x.v / 2, x.v / 2]; }),
                                      backgroundColor: fs.map(function (x) { return x.c; }),
                                      borderRadius: 4, barPercentage: 0.95, categoryPercentage: 1 }] },
                 options: opts };
      case 'waterfall':
        var tot = s.labels.map(function (_, j) { return s.vals.reduce(function (a, v) { return a + (v[j] || 0); }, 0); });
        var run = 0, bars = [], cols = [], steps = [];
        tot.forEach(function (v) { bars.push([run, run + v]); cols.push(v >= 0 ? UP : DOWN); steps.push(v); run += v; });
        bars.push([0, run]); cols.push(TOTAL); steps.push(run);
        sc = axisOpts(opts); sc.x.stacked = sc.y.stacked = false;
        opts.plugins = opts.plugins || {}; opts.plugins.legend = { display: false };
        genericTooltip(opts, function (c) { return (c.dataIndex === steps.length - 1 ? 'Total ' : '') + fmt(steps[c.dataIndex]); });
        return { type: 'bar',
                 data: { labels: s.labels.concat(['Total']),
                         datasets: [{ label: '', data: bars, backgroundColor: cols, borderRadius: 3 }] },
                 options: opts };
      case 'treemap':
        var ts = slices(s).filter(function (x) { return x.v > 0; });
        dropScales(opts);
        opts.plugins = opts.plugins || {}; opts.plugins.legend = { display: false };
        genericTooltip(opts, function (c) { return fmt(c.raw && c.raw.v); });
        opts.plugins.tooltip.callbacks.title = function (items) { var r = items[0] && items[0].raw; return r && r._data ? r._data.label : ''; };
        return { type: 'treemap',
                 data: { datasets: [{ tree: ts.map(function (x) { return { label: x.label, v: x.v, c: x.c }; }), key: 'v',
                                      borderWidth: 1, borderColor: 'rgba(15,17,23,0.9)', spacing: 1,
                                      backgroundColor: function (ctx) { return ctx.type === 'data' && ctx.raw && ctx.raw._data ? ctx.raw._data.c : 'transparent'; },
                                      labels: { display: true, color: '#fff', font: { size: 11, weight: '600' },
                                                formatter: function (ctx) { var d = ctx.raw && ctx.raw._data; return d ? [d.label, fmt(d.v)] : ''; } } }] },
                 options: opts };
    }
    return null;
  }

  // ── Treemap plugin, loaded on first use ──
  var treemapReady = null;
  function needTreemap() {
    if (Base.registry && (function () { try { return Base.registry.getController('treemap'); } catch (e) { return null; } })()) return Promise.resolve();
    if (!treemapReady) treemapReady = new Promise(function (res, rej) {
      var sEl = document.createElement('script');
      sEl.src = TREEMAP_SRC; sEl.onload = res; sEl.onerror = function () { treemapReady = null; rej(); };
      document.head.appendChild(sEl);
    });
    return treemapReady;
  }

  // The original's shape — a remembered type is only re-applied when the page redraws the SAME
  // kind of chart (e.g. a period change), not after the page's own type toggle changed it.
  function sig(orig) {
    var o = orig.options || {}, d0 = ((orig.data && orig.data.datasets) || [])[0] || {};
    return [orig.type || 'bar', o.indexAxis || 'x', d0.fill ? 'fill' : '', d0.type || ''].join('/');
  }

  // ── Apply / restore ──
  // The page's own inline plugins (value labels, centre text…) assume its original data shape,
  // so they only run on views with the same shape: the original and the vertical cartesian ones.
  var SAME_SHAPE = ['column', 'stacked', 'line', 'area', 'sarea', 'combo'];
  function setConfig(chart, cfg, key) {
    var raw = chart.config._config, orig = chart.$csOrig;
    var keep = key === 'original' || (SAME_SHAPE.indexOf(key) >= 0 && (!orig.type || orig.type === 'bar' || orig.type === 'line'));
    if (chart.$csPlugins === undefined) chart.$csPlugins = raw.plugins || [];
    raw.plugins = keep ? chart.$csPlugins : [];
    chart.config.type = cfg.type;
    chart.config.data = cfg.data;
    chart.config.options = cfg.options;
    chart.update();
  }
  function apply(chart, key, remember) {
    var orig = chart.$csOrig;
    if (!orig) return;
    if (remember) store.set(chart.$csKey, key === 'original' ? null : key + '|' + sig(orig));
    if (key === 'original') { chart.$csType = 'original'; setConfig(chart, clone(orig), 'original'); return; }
    var go = function () {
      if (!chart.canvas) return;                       // destroyed meanwhile
      var cfg = build(key, orig);
      if (!cfg) return;
      chart.$csType = key;
      try { setConfig(chart, cfg, key); } catch (e) {
        if (window.console) console.warn('chart_switcher: ' + key + ' failed, restoring original', e);
        chart.$csType = 'original'; setConfig(chart, clone(orig), 'original');
      }
    };
    if (key === 'treemap') needTreemap().then(go, function () { if (window.console) console.warn('chart_switcher: treemap plugin could not load'); });
    else go();
  }

  function eligible(chart) {
    var cv = chart.canvas, o = chart.$csOrig;
    if (!cv || !o) return false;
    if (cv.getAttribute('data-chart-switch') === 'off') return false;
    if (o.options && o.options.plugins && o.options.plugins.chartSwitch === false) return false;
    if (['bar', 'line', 'pie', 'doughnut', 'polarArea', 'radar'].indexOf(o.type || 'bar') < 0) return false;
    if (shape(o).points) return false;
    var w = cv.clientWidth || cv.width, h = cv.clientHeight || cv.height;
    return w >= 200 && h >= 120;
  }

  // ── UI ──
  var ICON = {
    btn: '<path d="M3 13h2v4H3zM8 9h2v8H8zM13 5h2v12h-2z"/><path d="M17 7l2 2 2-2" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    original: '<path d="M4 10a6 6 0 1 0 2-4.5M4 3v3h3" fill="none" stroke="currentColor" stroke-width="1.8"/>',
    column: '<path d="M3 11h3v6H3zM8.5 6h3v11h-3zM14 9h3v8h-3z"/>',
    bar: '<path d="M3 3h9v3H3zM3 8.5h13v3H3zM3 14h7v3H3z"/>',
    stacked: '<path d="M3 11h3v6H3zM8.5 6h3v11h-3zM14 9h3v8h-3z" opacity=".45"/><path d="M3 14h3v3H3zM8.5 11h3v6h-3zM14 13h3v4h-3z"/>',
    line: '<path d="M2 15l5-6 4 3 7-8" fill="none" stroke="currentColor" stroke-width="2"/>',
    area: '<path d="M2 17V13l5-5 4 3 7-7v13z" opacity=".8"/>',
    sarea: '<path d="M2 17v-6l5-4 4 2 7-5v13z" opacity=".4"/><path d="M2 17v-3l5-2 4 1 7-3v7z"/>',
    combo: '<path d="M3 11h3v6H3zM8.5 8h3v9h-3zM14 12h3v5h-3z" opacity=".6"/><path d="M2 8l6-4 5 3 6-4" fill="none" stroke="currentColor" stroke-width="1.8"/>',
    pie: '<path d="M10 2a8 8 0 1 0 8 8h-8z"/><path d="M12 0.5v7.5h7.5A7.5 7.5 0 0 0 12 .5z" opacity=".6"/>',
    doughnut: '<path d="M10 2a8 8 0 1 1-8 8h3.5a4.5 4.5 0 1 0 4.5-4.5z"/><path d="M9 2.1A8 8 0 0 0 2.1 9h3.5A4.5 4.5 0 0 1 9 5.6z" opacity=".55"/>',
    polar: '<path d="M10 10V1a9 9 0 0 1 8 5z"/><path d="M10 10l7 1a7 7 0 0 1-5 6z" opacity=".75"/><path d="M10 10l1 5a5 5 0 0 1-6-3z" opacity=".5"/><path d="M10 10L4 8a6 6 0 0 1 6-5z" opacity=".35"/>',
    radar: '<path d="M10 2l7.5 5.5-2.9 9H5.4l-2.9-9z" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M10 5l5 4-2 5H7.5L6 9.5z" opacity=".7"/>',
    funnel: '<path d="M2 3h16v3H2zM4.5 8.5h11v3h-11zM7 14h6v3H7z"/>',
    waterfall: '<path d="M2 12h3v5H2zM6 8h3v4H6zM10 5h3v3h-3z"/><path d="M14 5h3v12h-3z" opacity=".6"/>',
    treemap: '<path d="M2 2h9v10H2zM12 2h6v5h-6zM12 8h6v4h-6zM2 13h6v5H2zM9 13h9v5H9z"/>'
  };
  var svg = function (k) { return '<svg viewBox="0 0 20 20" width="15" height="15" fill="currentColor" aria-hidden="true">' + ICON[k] + '</svg>'; };

  var css = document.createElement('style');
  css.textContent =
    '.chartsw-btn{position:absolute;z-index:5;width:26px;height:24px;display:flex;align-items:center;justify-content:center;' +
    'background:rgba(30,33,48,.85);border:1px solid #2d3148;border-radius:6px;color:#94a3b8;cursor:pointer;opacity:.6;padding:0;' +
    'transition:opacity .15s,color .15s,border-color .15s}' +
    '.chartsw-btn:hover,.chartsw-btn:focus-visible,.chartsw-btn[aria-expanded="true"]{opacity:1;color:#e2e8f0;border-color:#6366f1;outline:none}' +
    '.chartsw-btn.chartsw-on{color:#a5b4fc;opacity:.95}' +
    '@media (hover:none){.chartsw-btn{opacity:.9}}' +
    '.chartsw-menu{position:fixed;z-index:9999;min-width:190px;max-height:70vh;overflow-y:auto;background:#1a1d2b;border:1px solid #2d3148;' +
    'border-radius:10px;padding:.35rem;box-shadow:0 12px 32px rgba(0,0,0,.45);font:13px "Segoe UI",system-ui,sans-serif}' +
    '.chartsw-menu .chartsw-h{font-size:10px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:#64748b;padding:.35rem .55rem .25rem}' +
    '.chartsw-menu button{display:flex;width:100%;align-items:center;gap:.55rem;background:none;border:0;color:#cbd5e1;padding:.38rem .55rem;' +
    'border-radius:6px;cursor:pointer;text-align:left;font:inherit}' +
    '.chartsw-menu button:hover,.chartsw-menu button:focus-visible{background:#252840;color:#f8fafc;outline:none}' +
    '.chartsw-menu button.chartsw-cur{background:rgba(99,102,241,.18);color:#c7d2fe}' +
    '.chartsw-menu button svg{flex:0 0 auto;color:#22d3ee}' +
    '.chartsw-menu .chartsw-sep{height:1px;background:#2d3148;margin:.3rem .2rem}';
  (document.head || document.documentElement).appendChild(css);

  var openMenu = null;
  function closeMenu(focusBtn) {
    if (!openMenu) return;
    var m = openMenu; openMenu = null;
    m.btn.setAttribute('aria-expanded', 'false');
    m.el.remove();
    document.removeEventListener('mousedown', m.outside, true);
    window.removeEventListener('scroll', m.close, true);
    window.removeEventListener('resize', m.close);
    if (focusBtn) m.btn.focus({ preventScroll: true });
  }
  function showMenu(chart) {
    var btn = chart.$csBtn;
    if (openMenu && openMenu.btn === btn) { closeMenu(true); return; }
    closeMenu();
    var s = shape(chart.$csOrig), cur = chart.$csType || 'original';
    var el = document.createElement('div');
    el.className = 'chartsw-menu'; el.setAttribute('role', 'menu'); el.setAttribute('aria-label', 'Chart type');
    var items = [{ key: 'original', label: 'Original' }].concat(TYPES.filter(function (t) { return t.ok(s); }));
    el.innerHTML = '<div class="chartsw-h">Chart type</div>' + items.map(function (t, i) {
      return (i === 1 ? '<div class="chartsw-sep"></div>' : '') +
        '<button type="button" role="menuitemradio" aria-checked="' + (t.key === cur) + '" data-k="' + t.key + '" class="' +
        (t.key === cur ? 'chartsw-cur' : '') + '">' + svg(t.key) + '<span>' + t.label + '</span></button>';
    }).join('');
    document.body.appendChild(el);
    var r = btn.getBoundingClientRect(), mw = el.offsetWidth, mh = el.offsetHeight;
    var left = Math.max(8, Math.min(r.right - mw, window.innerWidth - mw - 8));
    var top = r.bottom + 6 + mh > window.innerHeight - 8 ? Math.max(8, r.top - mh - 6) : r.bottom + 6;
    el.style.left = left + 'px'; el.style.top = top + 'px';
    var m = {
      el: el, btn: btn,
      outside: function (e) { if (!el.contains(e.target) && e.target !== btn && !btn.contains(e.target)) closeMenu(); },
      close: function (e) { if (!(e && e.target && e.target.nodeType === 1 && el.contains(e.target))) closeMenu(); }
    };
    openMenu = m;
    btn.setAttribute('aria-expanded', 'true');
    document.addEventListener('mousedown', m.outside, true);
    window.addEventListener('scroll', m.close, true);
    window.addEventListener('resize', m.close);
    el.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-k]'); if (!b) return;
      closeMenu(true);
      apply(chart, b.getAttribute('data-k'), true);
      mark(chart);
    });
    el.addEventListener('keydown', function (e) {
      var bs = Array.prototype.slice.call(el.querySelectorAll('button')), i = bs.indexOf(document.activeElement);
      if (e.key === 'Escape') { e.preventDefault(); closeMenu(true); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); bs[(i + 1) % bs.length].focus({ preventScroll: true }); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); bs[(i - 1 + bs.length) % bs.length].focus({ preventScroll: true }); }
      else if (e.key === 'Tab') closeMenu();
    });
    (el.querySelector('.chartsw-cur') || el.querySelector('button')).focus({ preventScroll: true });
  }
  function mark(chart) {
    if (!chart.$csBtn) return;
    var on = chart.$csType && chart.$csType !== 'original';
    chart.$csBtn.classList.toggle('chartsw-on', !!on);
    var t = TYPES.filter(function (x) { return x.key === chart.$csType; })[0];
    chart.$csBtn.title = 'Chart type' + (t ? ': ' + t.label : '');
  }
  function place(chart) {
    var b = chart.$csBtn, cv = chart.canvas;
    if (!b || !cv || !cv.parentNode) return;
    // A hidden chart (e.g. the other half of a Bars ⇄ Trend toggle) hides its button too.
    var shown = cv.offsetWidth > 0 && cv.offsetHeight > 0 && getComputedStyle(cv).display !== 'none';
    b.style.display = shown ? '' : 'none';
    if (!shown) return;
    b.style.top = (cv.offsetTop + 4) + 'px';
    b.style.left = Math.max(0, cv.offsetLeft + cv.offsetWidth - GUTTER + 4) + 'px';
  }
  function attach(chart) {
    if (chart.$csBtn || !eligible(chart)) return;
    var cv = chart.canvas, parent = cv.parentNode;
    if (getComputedStyle(parent).position === 'static') parent.style.position = 'relative';
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'chartsw-btn';
    b.setAttribute('aria-haspopup', 'menu'); b.setAttribute('aria-expanded', 'false');
    b.setAttribute('aria-label', 'Change chart type');
    if (cv.id) b.setAttribute('data-chart', cv.id);
    b.innerHTML = svg('btn');
    b.addEventListener('click', function (e) { e.stopPropagation(); showMenu(chart); });
    parent.appendChild(b);
    chart.$csBtn = b;
    if (window.ResizeObserver) {                      // follows the canvas being shown / hidden / resized
      chart.$csRO = new ResizeObserver(function () { place(chart); });
      chart.$csRO.observe(cv);
    }
    place(chart); mark(chart);
    chart.update('none');                             // re-lay out with the button's gutter
  }

  // An empty strip down the right edge of every chart with a button, so the button never covers
  // bars, lines, labels, the legend or the title. Added on top of the chart's own padding.
  var GUTTER = 34;
  function padOf(p) {
    if (typeof p === 'number') return { top: p, right: p, bottom: p, left: p };
    p = p || {};
    return { top: num(p.top != null ? p.top : p.y), right: num(p.right != null ? p.right : p.x),
             bottom: num(p.bottom != null ? p.bottom : p.y), left: num(p.left != null ? p.left : p.x) };
  }

  Base.register({
    id: 'chartSwitchUi',
    beforeLayout: function (chart) {
      if (!chart.$csBtn || !chart.options.layout) return;
      // chart.options writes through to chart.config.options, so the padding read here can be the
      // one WE set last layout. Re-adding the gutter to it on every update shrank the chart 34px per
      // redraw (scrolling in light mode redraws a lot). Keep the page's own padding and add to that.
      var cur = ((chart.config.options || {}).layout || {}).padding;
      if (!chart.$csPad || cur !== chart.$csPad.set) chart.$csPad = { base: padOf(cur) };
      var p = padOf(chart.$csPad.base);
      p.right += GUTTER;
      chart.options.layout.padding = p;
      chart.$csPad.set = ((chart.config.options || {}).layout || {}).padding;
    },
    afterInit: function (chart) { setTimeout(function () { attach(chart); }, 0); },
    resize: function (chart) { setTimeout(function () { if (chart.$csBtn) place(chart); else if (chart.$csOrig) attach(chart); }, 0); },
    afterDestroy: function (chart) {
      if (openMenu && openMenu.btn === chart.$csBtn) closeMenu();
      if (chart.$csRO) { chart.$csRO.disconnect(); chart.$csRO = null; }
      if (chart.$csBtn) { chart.$csBtn.remove(); chart.$csBtn = null; }
    }
  });

  // ── Week-on-week change on every week chart (docs/chart-switcher.md › Week change) ──
  // A bar / line chart whose x labels are weeks ("Wk 1", "Week 2", "W3", ["Wk 4 (now)", "dates"])
  // gets ▲ / ▼ % vs the week before above each week from the 2nd on: green up, red down, grey flat.
  // Stacked bars (or one series) → change of the total; 2–3 side-by-side series → one per series.
  // Opt out with options.plugins.weekChange = false.
  var WEEK_RE = /^\s*(?:wk|week|w)\s*\.?\s*(\d+)/i;
  function weekNo(l) { var m = String(Array.isArray(l) ? l[0] : l).match(WEEK_RE); return m ? +m[1] : null; }
  function valAt(v, horiz) { return v && typeof v === 'object' ? num(horiz ? v.x : v.y) : num(v); }
  function changeTxt(prev, cur) {
    if (!prev && !cur) return null;
    if (!prev) return { t: 'new', c: UP };
    var d = cur - prev, pc = Math.abs(d / Math.abs(prev) * 100);
    if (Math.round(pc) === 0) return { t: '0%', c: '#94a3b8' };
    return { t: (d > 0 ? '▲' : '▼') + (pc >= 10 ? Math.round(pc) : pc.toFixed(1)) + '%', c: d > 0 ? UP : DOWN };
  }
  function weekChart(chart) {
    var o = chart.options || (chart.config && chart.config.options) || {}, pl = o.plugins || {};
    if (pl.weekChange === false || (pl.valueLabels && pl.valueLabels.above)) return false;
    if (['bar', 'line'].indexOf(chart.config.type) < 0) return false;
    if (chart.$csType && chart.$csType !== 'original' && !/^(bar|line|stack|group|area)/.test(chart.$csType)) return false;
    var labels = (chart.data && chart.data.labels) || [];
    var nWk = labels.filter(function (l) { return weekNo(l) != null; }).length;
    return labels.length >= 2 && nWk >= 2 && nWk >= labels.length / 2;
  }
  // Headroom on the value axis so the label above the tallest bar isn't squeezed into the top edge.
  // Added to the config as the chart is created (Chart.js has read its axis options by the first plugin hook).
  function headroom(config) {
    var raw = config.options || (config.options = {}), pl = raw.plugins || {};
    if (['bar', 'line'].indexOf(config.type) < 0 || pl.weekChange === false || (pl.valueLabels && pl.valueLabels.above)) return;
    var labels = (config.data && config.data.labels) || [];
    var nWk = labels.filter(function (l) { return weekNo(l) != null; }).length;
    if (labels.length < 2 || nWk < 2 || nWk < labels.length / 2) return;
    var ax = raw.indexAxis === 'y' ? 'x' : 'y';
    var sc = (raw.scales = raw.scales || {}), a = (sc[ax] = sc[ax] || {});
    if (a.grace == null) a.grace = '14%';
  }
  // The ▲/▼ labels are drawn as pills (solid backing, coloured border, bright ink) so they read over
  // lines, fills and gridlines, and are placed clear of any text the chart or page drew — a page's own
  // value labels sit at the same spot above each point. While a chart renders, every fillText on its
  // canvas is recorded as a box; the pills are drawn last (just before the tooltip) in a free spot.
  // Solid fills with white text: the sharpest, most legible option on any background, both themes.
  var PILL = { up: '#059669', down: '#dc2626', flat: '#64748b', ink: '#ffffff', edge: 'rgba(0,0,0,0.35)' };
  function fontPx(f) { var m = /(\d+(?:\.\d+)?)px/.exec(f || ''); return m ? +m[1] : 12; }
  function textBox(ctx, text, x, y, dpr) {
    var t = ctx.getTransform ? ctx.getTransform() : null;
    if (t && (Math.abs(t.b) > 1e-6 || Math.abs(t.c) > 1e-6)) return null;    // rotated (axis titles)
    var s = t ? t.a / dpr : 1, w = ctx.measureText(String(text)).width * s, h = fontPx(ctx.font) * s;
    var cx = t ? (t.a * x + t.e) / dpr : x, cy = t ? (t.d * y + t.f) / dpr : y;
    var al = ctx.textAlign, bl = ctx.textBaseline;
    var x0 = al === 'center' ? cx - w / 2 : (al === 'right' || al === 'end') ? cx - w : cx;
    var y0 = (bl === 'top' || bl === 'hanging') ? cy : bl === 'middle' ? cy - h / 2 : cy - h * 0.85;
    return { x0: x0, y0: y0, x1: x0 + w, y1: y0 + h };
  }
  function startRecording(chart) {
    var ctx = chart.ctx; if (!ctx) return;
    chart.$csTexts = []; chart.$csPillsDone = false;
    var rec = ctx.$csRec;
    if (!rec) {
      rec = ctx.$csRec = {};
      var proto = Object.getPrototypeOf(ctx);
      ctx.fillText = function (text, x, y) {
        var r = rec.on && rec.chart && rec.chart.$csTexts;
        if (r) { var b = textBox(this, text, x, y, rec.chart.currentDevicePixelRatio || 1); if (b) r.push(b); }
        return proto.fillText.apply(this, arguments);     // looked up each time: v5_theme may patch it later
      };
    }
    rec.chart = chart; rec.on = true;
  }
  function overlaps(a, list) {
    for (var i = 0; i < list.length; i++) {
      var b = list[i];
      if (a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0) return true;
    }
    return false;
  }
  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath();
  }
  // White pill text, drawn straight onto the chart canvas so it stays crisp (copying it in from an
  // offscreen canvas resampled it and left it hazy). v5_theme.js (light mode) recolours fillText
  // whose fillStyle is a colour STRING; a one-colour gradient isn't one, so the ink stays white.
  function whiteText(ctx, text, cx, cy) {
    var g = ctx.createLinearGradient(0, 0, 0, 1);
    g.addColorStop(0, PILL.ink); g.addColorStop(1, PILL.ink);
    ctx.fillStyle = g; ctx.shadowColor = 'rgba(0,0,0,0)';
    ctx.fillText(text, cx, cy + 1);
  }
  function drawWeekPills(chart) {
    if (chart.$csPillsDone) return;
    chart.$csPillsDone = true;
    if (chart.ctx && chart.ctx.$csRec) chart.ctx.$csRec.on = false;
    if (!weekChart(chart)) return;
    var o = chart.options || {}, pl = o.plugins || {};
    var labels = chart.data.labels, wk = labels.map(weekNo);
    var horiz = o.indexAxis === 'y', sc = o.scales || {};
    var stacked = !!((sc.x && sc.x.stacked) || (sc.y && sc.y.stacked));
    var vis = chart.data.datasets.map(function (ds, di) { return di; }).filter(function (di) {
      var m = chart.getDatasetMeta(di); return chart.isDatasetVisible(di) && m && m.data && m.data.length;
    });
    if (!vis.length) return;
    var groups = (stacked || vis.length === 1) ? [vis] : (vis.length <= 3 ? vis.map(function (d) { return [d]; }) : null);
    if (!groups) return;
    var ctx = chart.ctx, area = chart.chartArea || { left: 0, top: 0, right: chart.width, bottom: chart.height };
    var fs = groups.length === 1 ? 12 : 11, padX = 6, h = 20;        // even sizes keep edges on whole pixels
    var lift = pl.valueLabels && pl.valueLabels.totals ? 24 : 10;             // clear of a page's own total label
    var taken = (chart.$csTexts || []).slice();
    ctx.save();
    ctx.font = '800 ' + fs + 'px "Segoe UI", system-ui, sans-serif';
    ctx.textBaseline = 'middle'; ctx.textAlign = 'center';
    groups.forEach(function (g) {
      var tot = labels.map(function (_, i) {
        return g.reduce(function (a, di) { return a + valAt(chart.data.datasets[di].data[i], horiz); }, 0);
      });
      // A week with no value at all (not reached yet) gets no label — not a "▼100%".
      var has = labels.map(function (_, i) {
        return g.some(function (di) {
          var v = chart.data.datasets[di].data[i];
          return v != null && !(typeof v === 'object' && (horiz ? v.x : v.y) == null);
        });
      });
      labels.forEach(function (_, i) {
        if (i === 0 || wk[i] == null || wk[i - 1] == null || !has[i] || !has[i - 1]) return;
        var ch = changeTxt(tot[i - 1], tot[i]); if (!ch) return;
        var els = g.map(function (di) { return chart.getDatasetMeta(di).data[i]; }).filter(Boolean);
        if (!els.length) return;
        var fill = ch.c === UP ? PILL.up : ch.c === DOWN ? PILL.down : PILL.flat;
        var w = Math.ceil(ctx.measureText(ch.t).width) + padX * 2, cands = [];
        w += w % 2;
        if (horiz) {
          var right = Math.max.apply(null, els.map(function (e) { return Math.max(e.x, e.base != null ? e.base : e.x); }));
          var y = els[0].y;
          [8, 8 + w + 4, 8 + 2 * (w + 4)].forEach(function (d) { cands.push({ cx: right + d + w / 2, cy: y }); });
          cands.push({ cx: right + 8 + w / 2, cy: y - h - 2 }, { cx: right + 8 + w / 2, cy: y + h + 2 });
        } else {
          var x = els.reduce(function (a, e) { return a + e.x; }, 0) / els.length;
          var top = Math.min.apply(null, els.map(function (e) { return Math.min(e.y, e.base != null ? e.base : e.y); }));
          var bottom = Math.max.apply(null, els.map(function (e) { return e.y; }));
          for (var k = 0; k < 4; k++) cands.push({ cx: x, cy: top - lift - k * (h + 3) });       // above, stepping up
          for (k = 0; k < 2; k++) cands.push({ cx: x, cy: bottom + lift + 4 + k * (h + 3) });   // then below
          cands.push({ cx: x + w / 2 + 10, cy: top }, { cx: x - w / 2 - 10, cy: top });          // then beside
        }
        var box = function (c) { return { x0: c.cx - w / 2, y0: c.cy - h / 2, x1: c.cx + w / 2, y1: c.cy + h / 2 }; };
        var inside = function (b) { return b.y0 >= 0 && b.y1 <= chart.height && b.x0 >= 0 && b.x1 <= chart.width; };
        var pick = null;
        for (var j = 0; j < cands.length && !pick; j++) { var b = box(cands[j]); if (inside(b) && !overlaps(b, taken)) pick = cands[j]; }
        if (!pick) {                                            // nowhere free: nearest spot above, kept on the canvas
          pick = cands[0];
          pick.cy = Math.max(pick.cy, h / 2 + 1);
        }
        // Snap to whole pixels so the edges and text don't blur across two pixels.
        pick = { cx: Math.round(pick.cx), cy: Math.round(pick.cy) };
        var bx = box(pick);
        taken.push(bx);
        roundRect(ctx, bx.x0, bx.y0, w, h, 4);
        ctx.fillStyle = fill; ctx.fill();
        roundRect(ctx, bx.x0 + 0.5, bx.y0 + 0.5, w - 1, h - 1, 4);    // 1px edge on whole pixels, not split across two
        ctx.lineWidth = 1; ctx.strokeStyle = PILL.edge; ctx.stroke();
        whiteText(ctx, ch.t, pick.cx, pick.cy);
      });
    });
    ctx.restore();
  }
  Base.register({
    id: 'weekChange',
    beforeDraw: function (chart) { startRecording(chart); },
    // Drawn after the page's own labels and just before the tooltip, so the tooltip still covers them.
    beforeTooltipDraw: function (chart) { drawWeekPills(chart); },
    afterRender: function (chart) { drawWeekPills(chart); }
  });

  // ── Wrap the Chart class: keep the pristine config, re-apply a remembered type ──
  var seq = 0;
  function Chart(item, config) {
    if (config) { try { headroom(config); } catch (e) {} }
    var orig = config ? clone({ type: config.type, data: config.data, options: config.options || {} }) : null;
    var chart = Reflect.construct(Base, [item, config], new.target || Chart);
    chart.$csOrig = orig;
    var cv = chart.canvas;
    if (cv) {
      var page = (location.pathname.split('/').pop() || 'page');
      chart.$csKey = 'cs:' + decodeURIComponent(page) + ':' + (cv.id || ('#' + (cv.$csIdx = cv.$csIdx || ++seq)));
      var parts = (store.get(chart.$csKey) || '').split('|'), saved = parts[0];
      if (saved && orig) {
        var t = TYPES.filter(function (x) { return x.key === saved; })[0];
        if (!t || parts.slice(1).join('|') !== sig(orig)) store.set(chart.$csKey, null);   // page changed the chart itself
        else if (eligible(chart) && t.ok(shape(orig))) setTimeout(function () { apply(chart, saved, false); mark(chart); }, 0);
      }
    }
    return chart;
  }
  Object.setPrototypeOf(Chart, Base);
  Chart.prototype = Base.prototype;
  Chart.__chartSwitch = true;
  window.Chart = Chart;
})();
