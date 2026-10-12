/* v5_theme.js — "Dashboard V5" theme engine for the dashboard pages.
   shell.html loads this and calls V5Theme.apply(frame.contentDocument, mode) on every iframe load,
   so each generated page gets the V5 look without regenerating it:
     - both modes: v5_theme.css (Inter, rounded cards, soft shadows, hover lift, indigo pill controls)
     - 'light':    the page's own dark colours are remapped in place — every <style> rule and inline
                   style is rewritten through the CSSOM (so :hover / .active states keep working and
                   the export clone matches the screen), Chart.js charts are recoloured, and a
                   MutationObserver themes anything the page renders later (tabs, popovers, charts).
     - 'dark':     the page's native colours, plus the V5 shape layer.
   Going light → dark needs a page reload (the shell does that); the remap is idempotent, so
   applying 'light' twice is harmless. */
(function (root) {
  'use strict';

  var CSS_HREF = 'v5_theme.css';
  var FONT_HREF = 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap';

  // ── Colour maths ────────────────────────────────────────────
  var NAMED = { white: [255, 255, 255], black: [0, 0, 0] };

  function parseColor(tok) {
    tok = tok.trim().toLowerCase();
    if (NAMED[tok]) return { r: NAMED[tok][0], g: NAMED[tok][1], b: NAMED[tok][2], a: 1 };
    var m = tok.match(/^#([0-9a-f]{3,8})$/);
    if (m) {
      var h = m[1];
      if (h.length === 3 || h.length === 4) h = h.split('').map(function (c) { return c + c; }).join('');
      if (h.length !== 6 && h.length !== 8) return null;
      return { r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16), b: parseInt(h.slice(4, 6), 16),
               a: h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1 };
    }
    m = tok.match(/^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+%?))?\s*\)$/);
    if (m) {
      var a = m[4] === undefined ? 1 : (m[4].slice(-1) === '%' ? parseFloat(m[4]) / 100 : +m[4]);
      return { r: +m[1], g: +m[2], b: +m[3], a: a };
    }
    return null;
  }

  function toHsl(c) {
    var r = c.r / 255, g = c.g / 255, b = c.b / 255;
    var mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    var h = 0, s = 0, l = (mx + mn) / 2;
    if (d) {
      s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
      if (mx === r) h = (g - b) / d + (g < b ? 6 : 0);
      else if (mx === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      h *= 60;
    }
    return { h: Math.round(h), s: Math.round(s * 100), l: Math.round(l * 100), a: c.a };
  }

  function hsl(h, s, l, a) {
    return a === undefined || a >= 1 ? 'hsl(' + h + ',' + s + '%,' + l + '%)'
                                     : 'hsla(' + h + ',' + s + '%,' + l + '%,' + (+a.toFixed(3)) + ')';
  }

  // Map ONE colour to the V5 light palette. kind: 'bg' | 'text' | 'border'.
  // Every branch is idempotent (a mapped colour maps to itself), so re-runs are safe.
  function mapColor(c, kind) {
    var x = toHsl(c);
    if (x.a < 0.02) return null;
    // Neutral = low chroma. (HSL saturation alone misreads slate tints like #f8fafc as "40%".)
    var chroma = Math.max(c.r, c.g, c.b) - Math.min(c.r, c.g, c.b);
    var neutral = chroma < 28 || (chroma < 48 && x.s < 35) || x.l < 4;
    if (kind === 'bg') {
      if (neutral) {
        if (x.l >= 40) return null;                        // already light
        if (x.a < 0.6) {
          if (x.l < 4) return 'rgba(0,0,0,' + (+Math.min(0.35, x.a).toFixed(3)) + ')';  // scrim / backdrop
          return 'rgba(255,255,255,0.88)';                 // translucent "glass" card → white glass
        }
        // Soft greys, not pure white — a white page glares and washes the ink out.
        if (x.l < 9)  return '#e9ebf0';                    // page canvas
        if (x.l < 13) return '#f1f3f6';                    // table heads, inset strips
        if (x.l < 18) return '#f9fafb';                    // cards
        return '#e3e6ec';                                  // raised / hovered rows, chips
      }
      if (x.l < 30 && x.a >= 0.6) return hsl(x.h, Math.min(x.s, 70), 94, x.a); // deep tint → pale tint
      return null;                                         // vivid fills + soft rgba tints read fine
    }
    if (kind === 'border') {
      if (neutral && x.l < 45) return x.a < 0.6 ? 'rgba(15,23,42,0.12)' : '#d9dde5';
      return null;
    }
    // text — always solid ink: faded light text (rgba(255,255,255,.5)) turned into faded DARK
    // text reads as pale grey on the light canvas, so fold the alpha into the lightness first.
    var a = x.a;
    if (a < 1 && x.l > 57) { x.l = Math.round(a * x.l + (1 - a) * 11); a = 1; }   // as seen on a dark card
    if (neutral) {
      // Bright ink (primary text) → near-black; dimmer ink → a bit lighter, but never past 40%
      // lightness (≈ 6:1 on the canvas), so muted labels and small numbers stay readable.
      var nl = x.l > 57 ? Math.round(12 + (100 - x.l) * 0.55) : Math.min(x.l, 40);
      if (nl === x.l && a === x.a) return null;            // already dark enough
      return hsl(x.h, Math.min(x.s, 25), nl, a);
    }
    // Accent ink: keep the hue, darken until it reads on the light canvas (≥ 5.5:1).
    if (contrastOnCanvas(x.h, x.s, x.l) >= 5.5) return a === x.a ? null : hsl(x.h, x.s, x.l, a);
    var s = Math.min(x.s, 85);
    var h = x.h >= 40 && x.h <= 65 ? 32 : x.h;              // darkened yellow turns olive — use amber instead
    for (var l = Math.min(x.l, 50); l > 12; l -= 2) {
      if (contrastOnCanvas(h, s, l) >= 5.5) return hsl(h, s, l, a);
    }
    return hsl(h, s, 12, a);
  }

  function hslToRgb(h, s, l) {
    s /= 100; l /= 100;
    var k = function (n) { return (n + h / 30) % 12; };
    var a = s * Math.min(l, 1 - l);
    var f = function (n) { return l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1))); };
    return [f(0) * 255, f(8) * 255, f(4) * 255];
  }
  function luminance(rgb) {
    var c = rgb.map(function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  var CANVAS_LUM = luminance([233, 235, 240]);            // #e9ebf0, the darkest light surface
  function contrastOnCanvas(h, s, l) {
    return (CANVAS_LUM + 0.05) / (luminance(hslToRgb(h, s, l)) + 0.05);
  }

  var TOKEN_RE = /#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\b(?:white|black)\b/g;

  function mapValue(value, kind) {
    if (!value) return value;
    return value.replace(TOKEN_RE, function (tok) {
      var c = parseColor(tok);
      if (!c) return tok;
      var out = mapColor(c, kind);
      return out || tok;
    });
  }

  var PROPS = [
    ['background', 'bg'], ['background-color', 'bg'], ['background-image', 'bg'],
    ['color', 'text'], ['fill', 'text'], ['stroke', 'text'], ['caret-color', 'text'],
    ['-webkit-text-fill-color', 'text'], ['text-decoration-color', 'text'],
    ['border', 'border'], ['border-color', 'border'],
    ['border-top', 'border'], ['border-right', 'border'], ['border-bottom', 'border'], ['border-left', 'border'],
    ['border-top-color', 'border'], ['border-right-color', 'border'],
    ['border-bottom-color', 'border'], ['border-left-color', 'border'],
    ['outline', 'border'], ['outline-color', 'border'], ['column-rule-color', 'border']
  ];

  // Is this declaration block painting a vivid (saturated, opaque) background? Then its light
  // text is "text on a colour chip" and must stay light.
  function vividBg(style) {
    var v = (style.getPropertyValue('background-color') || '') + ' ' +
            (style.getPropertyValue('background-image') || '') + ' ' +
            (style.getPropertyValue('background') || '');
    var toks = v.match(TOKEN_RE) || [];
    for (var i = 0; i < toks.length; i++) {
      var c = parseColor(toks[i]);
      if (!c) continue;
      var x = toHsl(c);
      if (x.a >= 0.6 && x.s >= 35 && x.l >= 22 && x.l <= 75) return true;
    }
    return false;
  }

  // Rewrite one CSSStyleDeclaration in place. Returns true if anything changed.
  function mapDecl(style) {
    var changed = false;
    var keepText = vividBg(style);
    var clipText = /text/.test((style.getPropertyValue('-webkit-background-clip') || '') +
                               (style.getPropertyValue('background-clip') || ''));
    for (var i = 0; i < PROPS.length; i++) {
      var prop = PROPS[i][0], kind = PROPS[i][1];
      var val = style.getPropertyValue(prop);
      if (!val) continue;
      if (kind === 'text' && keepText) continue;
      if (kind === 'bg' && clipText) kind = 'text';        // gradient text: treat stops as ink
      var next = mapValue(val, kind);
      if (next !== val) {
        style.setProperty(prop, next, style.getPropertyPriority(prop));
        changed = true;
      }
    }
    // Custom properties (--bg-card: #1e2130 …): the name says what the colour is for.
    for (var n = 0; n < style.length; n++) {
      var name = style[n];
      if (name.slice(0, 2) !== '--') continue;
      var vk = /bg|surface|card|page|panel|app|sidebar|content|inset|raised|head/i.test(name) ? 'bg'
             : /border|line|grid|divider|rule/i.test(name) ? 'border'
             : /text|ink|fg|muted|label|dim|hi$|mid$|lo$/i.test(name) ? 'text' : null;
      if (!vk) continue;                                   // accents (--green, --cyan) stay
      var cv = style.getPropertyValue(name), nv = mapValue(cv, vk);
      if (nv !== cv) { style.setProperty(name, nv, style.getPropertyPriority(name)); changed = true; }
    }
    // Dark shadows are fine on white, but big black "lift" shadows look muddy — soften them.
    var sh = style.getPropertyValue('box-shadow');
    if (sh && /rgba\(\s*0\s*,\s*0\s*,\s*0/.test(sh)) {
      var soft = sh.replace(/rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*([\d.]+)\s*\)/g, function (_, a) {
        return 'rgba(16,24,40,' + (+Math.min(0.12, a * 0.3).toFixed(3)) + ')';
      });
      if (soft !== sh) { style.setProperty('box-shadow', soft, style.getPropertyPriority('box-shadow')); changed = true; }
    }
    return changed;
  }

  function mapRules(rules) {
    var changed = false;
    for (var i = 0; i < rules.length; i++) {
      var r = rules[i];
      if (r.style) changed = mapDecl(r.style) || changed;
      if (r.cssRules) changed = mapRules(r.cssRules) || changed;   // @media, @supports, @keyframes
    }
    return changed;
  }

  function serialize(sheet) {
    var out = [];
    for (var i = 0; i < sheet.cssRules.length; i++) out.push(sheet.cssRules[i].cssText);
    return out.join('\n');
  }

  // Rewrite every page <style> (not ours) and write the result back as text, so the style
  // element, the live CSSOM and any cloneNode() export all agree.
  function themeStyles(doc) {
    var els = doc.querySelectorAll('style:not([data-v5])');
    for (var i = 0; i < els.length; i++) {
      var el = els[i], sheet = el.sheet;
      if (!sheet) continue;
      var rules;
      try { rules = sheet.cssRules; } catch (e) { continue; }
      if (mapRules(rules)) el.textContent = serialize(sheet);
      el.setAttribute('data-v5-light', '');
    }
  }

  function themeInline(rootEl) {
    var list = [];
    if (rootEl.nodeType === 1 && rootEl.hasAttribute('style')) list.push(rootEl);
    if (rootEl.querySelectorAll) {
      var found = rootEl.querySelectorAll('[style]');
      for (var i = 0; i < found.length; i++) list.push(found[i]);
    }
    for (var j = 0; j < list.length; j++) {
      var el = list[j];
      if (el.closest && el.closest('[data-v5-keep]')) continue;
      mapDecl(el.style);
    }
  }

  // Text that inherits light ink from a parent but sits on its own vivid chip set by a
  // *different* rule (e.g. .pill{color:#fff} + .pill-kenya{background:#10b981}).
  function fixChipText(doc, rootEl) {
    var view = doc.defaultView;
    var list = rootEl.querySelectorAll ? rootEl.querySelectorAll('span,div,button,a,td,th,b,strong,em,small,label,p,li') : [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      var cs = view.getComputedStyle(el);
      if (cs.display === 'none') continue;
      var bgTok = cs.backgroundColor + ' ' + (cs.backgroundImage !== 'none' && !/text/.test(cs.webkitBackgroundClip || cs.backgroundClip) ? cs.backgroundImage : '');
      var toks = bgTok.match(TOKEN_RE) || [], vivid = false, pale = false;
      for (var t = 0; t < toks.length; t++) {
        var c = parseColor(toks[t]); if (!c) continue;
        var x = toHsl(c);
        if (x.a >= 0.6 && x.s >= 35 && x.l >= 22 && x.l <= 62) vivid = true;
        if (x.a >= 0.6 && x.l > 62) pale = true;
      }
      if (!vivid || pale) continue;
      var ink = parseColor(cs.color);
      if (!ink) continue;
      var ix = toHsl(ink);
      if (ix.s < 35 && ix.l < 57) el.style.setProperty('color', '#ffffff');
    }
  }

  // ── Chart.js ────────────────────────────────────────────────
  var SKIP_KEYS = { tooltip: 1, datasets: 1, data: 1, _proxy: 1 };

  function walkOptions(obj, path, depth, seen) {
    if (!obj || typeof obj !== 'object' || depth > 7 || seen.indexOf(obj) !== -1) return false;
    seen.push(obj);
    var changed = false;
    for (var k in obj) {
      if (!Object.prototype.hasOwnProperty.call(obj, k) || SKIP_KEYS[k]) continue;
      var v = obj[k];
      if (typeof v === 'string' && /color$/i.test(k)) {
        var lineish = /grid|angleLines|border/.test(path) || /^border/i.test(k);
        var bgish = /^backgroundColor$/.test(k) && !/labels/.test(path);
        var next = mapValue(v, bgish ? 'bg' : (lineish ? 'border' : 'text'));
        if (next !== v) { obj[k] = next; changed = true; }
      } else if (v && typeof v === 'object' && !Array.isArray(v)) {
        changed = walkOptions(v, path + '.' + k, depth + 1, seen) || changed;
      }
    }
    return changed;
  }

  // Point rings / doughnut separators drawn in the old card colour so they "cut out" of a dark
  // tile — on white they must become white too.
  var CUT_KEYS = ['borderColor', 'pointBorderColor', 'pointHoverBorderColor', 'hoverBorderColor'];
  function cutColor(v) {
    if (typeof v !== 'string') return v;
    var c = parseColor(v);
    if (!c) return v;
    var x = toHsl(c);
    return x.s < 35 && x.l < 22 && x.a > 0.5 ? '#ffffff' : v;
  }
  function themeDatasets(chart) {
    var changed = false;
    var ds = (chart.config && chart.config.data && chart.config.data.datasets) || [];
    for (var i = 0; i < ds.length; i++) {
      for (var j = 0; j < CUT_KEYS.length; j++) {
        var k = CUT_KEYS[j], v = ds[i][k];
        if (Array.isArray(v)) {
          var arr = v.map(cutColor);
          if (arr.some(function (a, n) { return a !== v[n]; })) { ds[i][k] = arr; changed = true; }
        } else if (typeof v === 'string') {
          var nv = cutColor(v);
          if (nv !== v) { ds[i][k] = nv; changed = true; }
        }
      }
    }
    return changed;
  }

  function themeChart(chart) {
    if (!chart || !chart.config) return false;
    var a = walkOptions(chart.config.options, 'options', 0, []);
    var b = themeDatasets(chart);
    return a || b;
  }

  // Pages draw their own chart labels with ctx.fillText in pale inks meant for a dark tile.
  // Remap the ink of TEXT draws only (bar/area fills are untouched) and drop the dark halo.
  function patchCanvasText(win) {
    var proto = win.CanvasRenderingContext2D && win.CanvasRenderingContext2D.prototype;
    if (!proto || proto.__v5text) return;
    proto.__v5text = true;
    var orig = proto.fillText, cache = {};
    proto.fillText = function () {
      var fs = this.fillStyle;
      if (typeof fs === 'string') {
        var m = cache[fs];
        if (m === undefined) m = cache[fs] = mapValue(fs, 'text');
        if (m !== fs) {
          var sh = this.shadowColor;
          this.fillStyle = m; this.shadowColor = 'rgba(0,0,0,0)';
          try { return orig.apply(this, arguments); }
          finally { this.fillStyle = fs; this.shadowColor = sh; }
        }
      }
      return orig.apply(this, arguments);
    };
  }

  function themeCharts(win) {
    patchCanvasText(win);
    var Chart = win.Chart;
    if (!Chart) return;
    var fresh = !Chart.__v5;                             // new defaults → every chart redraws once
    if (!Chart.__v5) {
      Chart.__v5 = true;
      try {
        Chart.defaults.color = '#334155';
        Chart.defaults.borderColor = '#d9dde5';
        if (Chart.defaults.font) Chart.defaults.font.family = "'Inter', 'Segoe UI', system-ui, sans-serif";
        if (Chart.defaults.scale && Chart.defaults.scale.grid) Chart.defaults.scale.grid.color = '#e3e6ec';
      } catch (e) {}
      // Charts built (or rebuilt by chart_switcher.js) after this point get themed too.
      try {
        Chart.register({
          id: 'v5theme',
          beforeUpdate: function (chart) {
            if (themeChart(chart)) win.requestAnimationFrame(function () { try { chart.update('none'); } catch (e) {} });
          }
        });
      } catch (e) {}
    }
    var inst = Chart.instances || {};
    Object.keys(inst).forEach(function (id) {
      var ch = inst[id];
      // Redraw only when something was recoloured: the observer calls this on every style change
      // (the page sidebar moves itself on each scroll), and redrawing every chart each time is slow.
      try { if (themeChart(ch) || fresh) ch.update('none'); } catch (e) {}
    });
  }

  // ── Wiring ──────────────────────────────────────────────────
  function ensureLink(doc, id, href) {
    if (doc.getElementById(id)) return;
    var l = doc.createElement('link');
    l.id = id; l.rel = 'stylesheet'; l.href = href;
    l.setAttribute('data-v5', '');
    (doc.head || doc.documentElement).appendChild(l);
  }

  function observe(doc) {
    var win = doc.defaultView;
    if (doc.__v5obs || !win.MutationObserver) return;
    var busy = false, pending = [], timer = null;
    var obs = new win.MutationObserver(function (records) {
      if (busy) return;
      for (var i = 0; i < records.length; i++) {
        var r = records[i];
        if (r.type === 'attributes') pending.push(r.target);
        else for (var j = 0; j < r.addedNodes.length; j++) {
          var n = r.addedNodes[j];
          if (n.nodeType === 1) pending.push(n);
          else if (n.parentNode && n.parentNode.nodeName === 'STYLE') pending.push(n.parentNode);
        }
      }
      if (!timer) timer = win.setTimeout(flush, 30);
    });
    function flush() {
      timer = null;
      var nodes = pending; pending = [];
      busy = true;
      try {
        var restyle = false, roots = [];
        nodes.forEach(function (n) {
          if (!n.isConnected) return;
          if (n.nodeName === 'STYLE' || (n.querySelector && n.querySelector('style:not([data-v5])'))) restyle = true;
          themeInline(n);
          var r = n.parentNode || n;
          if (roots.indexOf(r) < 0) roots.push(r);
        });
        // Chip-text pass once per affected subtree, not once per added node: a table that
        // renders 500 rows used to rescan its whole <tbody> 500 times (≈80 s frozen on Posting
        // when the theme was applied before the page finished rendering).
        roots.filter(function (r) {
          return !roots.some(function (o) { return o !== r && o.contains && o.contains(r); });
        }).forEach(function (r) { fixChipText(doc, r); });
        if (restyle) themeStyles(doc);
        themeCharts(win);
      } finally {
        obs.takeRecords();
        busy = false;
      }
    }
    obs.observe(doc.documentElement, { childList: true, subtree: true, characterData: true,
                                       attributes: true, attributeFilter: ['style'] });
    doc.__v5obs = obs;
  }

  function apply(doc, mode) {
    if (!doc || !doc.documentElement || !doc.body) return;
    mode = mode === 'dark' ? 'dark' : 'light';
    var html = doc.documentElement;
    html.setAttribute('data-v5', mode);
    ensureLink(doc, 'v5-font', FONT_HREF);
    ensureLink(doc, 'v5-css', CSS_HREF);
    var win = doc.defaultView;
    try { if (win.Chart && win.Chart.defaults && win.Chart.defaults.font)
            win.Chart.defaults.font.family = "'Inter', 'Segoe UI', system-ui, sans-serif"; } catch (e) {}
    if (mode !== 'light') return;
    if (doc.__v5obs) doc.__v5obs.disconnect(), doc.__v5obs = null;
    themeStyles(doc);
    themeInline(doc.body);
    fixChipText(doc, doc.body);
    themeCharts(win);
    observe(doc);
  }

  root.V5Theme = { apply: apply, mapColor: function (s, kind) { var c = parseColor(s); return c ? (mapColor(c, kind) || s) : s; } };
})(window);
