"""streamlit_app.py — STOCKS PICKING (Redundancy rate): its own Streamlit app, its own GitHub repo.

Streamlit Cloud: this repo, main file = streamlit_app.py, Secrets = the Odoo database (DB_HOST, DB_PORT, DB_NAME,
DB_USER, DB_PASSWORD, or DATABASE_URL). Spec: README.md › Streamlit app.

Shows colour_comparison.html and keeps it fresh from Odoo, like the Marketing dashboard's app:
  • Refresh rebuilds the page now (colour_comparison.py, bypassing the Odoo cache);
  • the page rebuilds by itself when it is older than AUTO_REFRESH_MIN minutes (checked on every view and
    every minute while a tab is open);
  • a rebuild runs in the background (one at a time, shared by every viewer) and the last build stays on
    screen until the new one is ready.
The top looks like the dashboard's: the brand bar (tab with its travelling light, Light / Dark switch, contact,
owner), the title strip with the live clock pill and Refresh, and the page in the dashboard's V5 theme. The
look files (v5_theme.css / .js, top_nav.js, kpi_drag.js) and the owner (dashboard_pages.json) come from the Marketing
dashboard folder next to this one when it is there, else from the copies in shared/.

Run:  python streamlit_app.py   (or VS Code ▶ / double-click "Stocks Picking app.bat"; port 8502)
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from html import escape as _esc

# ── Auto-launch: plain `python streamlit_app.py` re-launches itself via `streamlit run` ──
# Started on this PC (VS Code ▶ / python streamlit_app.py): port 8502 (the dashboard has 8501) and open the browser.
# Streamlit Cloud runs `streamlit run` itself, so it keeps .streamlit/config.toml (headless, its port 8501).
_LOCAL_ARGS = ["--server.port", "8502", "--server.headless", "false"]
_FALLBACK_PYTHON = r"C:\ProgramData\anaconda3\python.exe"     # the Marketing dashboard's Python
try:
    import streamlit as st
except ImportError:
    if os.path.exists(_FALLBACK_PYTHON) and os.path.normcase(sys.executable) != os.path.normcase(_FALLBACK_PYTHON):
        sys.exit(subprocess.run([_FALLBACK_PYTHON, "-m", "streamlit", "run", os.path.abspath(__file__), *_LOCAL_ARGS, *sys.argv[1:]]).returncode)
    print("Streamlit isn't installed for " + sys.executable + " — run: pip install streamlit")
    input("Press Enter to close...")
    sys.exit(1)


def _under_streamlit():
    try:
        from streamlit.runtime import exists
        return exists()
    except Exception:                                        # noqa: BLE001
        return False


if __name__ == "__main__" and not _under_streamlit():
    sys.exit(subprocess.run([sys.executable, "-m", "streamlit", "run", os.path.abspath(__file__), *_LOCAL_ARGS, *sys.argv[1:]]).returncode)

BASE = os.path.dirname(os.path.abspath(__file__))
_SIBLING = os.path.join(os.path.dirname(BASE), "Marketing_dashboard")
DASHBOARD = (os.environ.get("DASHBOARD_DIR")                  # the look files + owner: the dashboard next door, else shared/
             or (_SIBLING if os.path.isfile(os.path.join(_SIBLING, "v5_theme.js")) else os.path.join(BASE, "shared")))
HTML = os.path.join(BASE, "colour_comparison.html")
BUILDER = os.path.join(BASE, "colour_comparison.py")
TITLE = "Stocks Picking (Redundancy rate)"
PURPOSE = "Each bag's colours: redundancy rate, and units sold ÷ stock at the start beside stock now and on / not on offer"
AUTO_REFRESH_MIN = 60
_AUTO_SECS = AUTO_REFRESH_MIN * 60
BUILD_TIMEOUT = 600
# SPR_NO_AUTOREFRESH=1 (testing): never rebuild on a page view, no idle-tab reload.
NO_AUTOREFRESH = os.environ.get("SPR_NO_AUTOREFRESH") == "1"
# Streamlit's header with its Deploy button is shown (Streamlit itself shows Deploy only when run on this PC, never to
# Streamlit Cloud viewers). SPR_HIDE_DEPLOY=1 hides the header and starts the page at the very top.
SHOW_DEPLOY = os.environ.get("SPR_HIDE_DEPLOY") != "1"

st.set_page_config(page_title="Denri · " + TITLE, page_icon="📦", layout="wide", initial_sidebar_state="collapsed")


def _read(name, folder=DASHBOARD):
    try:
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


# ── Secrets → environment (Streamlit Cloud), so the dashboard's lib/db.py connects unchanged ──
def _load_secrets_into_env():
    try:
        secrets = st.secrets
        keys = list(secrets.keys())
    except Exception:                                        # noqa: BLE001  (no secrets.toml locally)
        return
    for key in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "DATABASE_URL", "SUPABASE_DB_URL",
                "SERVICE_ACCOUNT_JSON", "SERVICE_ACCOUNT_B64"):
        if key in keys and str(secrets[key]).strip():
            os.environ[key] = str(secrets[key])
    for tkey in ("gcp_service_account", "service_account"):        # a TOML table → the JSON lib/ expects
        if tkey in keys and not os.environ.get("SERVICE_ACCOUNT_JSON"):
            os.environ["SERVICE_ACCOUNT_JSON"] = json.dumps(dict(secrets[tkey]))
    os.environ.setdefault("DENRI_LAUNCHER", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


_load_secrets_into_env()


# ── Background rebuild: one job, shared by every session ──
@st.cache_resource
def _job():
    return {"lock": threading.Lock(), "running": False, "started": None, "ended": None, "kind": None,
            "ok": None, "log": "", "last_try": 0.0, "secs": None}


def _page_age_secs():
    try:
        return time.time() - os.path.getmtime(HTML)
    except OSError:
        return float("inf")


def _run_build(kind):
    j = _job()
    env = {**os.environ, "DENRI_LAUNCHER": "1", "PYTHONIOENCODING": "utf-8"}
    if kind == "manual":
        env["DENRI_FORCE_FRESH"] = "1"                       # bypass the Odoo cache
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, BUILDER], cwd=BASE, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=BUILD_TIMEOUT)
        ok, log = r.returncode == 0, (r.stdout + "\n" + r.stderr).strip()
    except subprocess.TimeoutExpired:
        ok, log = False, f"timed out after {BUILD_TIMEOUT}s"
    except Exception as e:                                   # noqa: BLE001
        ok, log = False, str(e)
    with j["lock"]:
        j.update(running=False, ended=time.time(), ok=ok, log=log[-1500:], secs=(time.time() - t0) if ok else j["secs"])


def start_build(kind):
    """Start a rebuild unless one is running. kind: "manual" (Refresh) or "auto" (page older than the interval;
    tried at most once per interval, so a failing build doesn't loop)."""
    j = _job()
    with j["lock"]:
        if j["running"]:
            return False
        if kind == "auto" and time.time() - j["last_try"] < _AUTO_SECS:
            return False
        j.update(running=True, started=time.time(), ended=None, kind=kind, ok=None, log="", last_try=time.time())
    threading.Thread(target=_run_build, args=(kind,), daemon=True).start()
    return True


def _ago(secs):
    if secs == float("inf"):
        return "Not built yet"
    m = int(secs // 60)
    return "Updated " + ("just now" if m < 1 else (f"{m} min ago" if m < 60 else f"{m // 60}h {m % 60}m ago")) \
        + f" · auto {AUTO_REFRESH_MIN} min"


def _run_js(html):
    """Run script-only HTML in an invisible frame (same origin, so it can reach window.parent)."""
    st.iframe("<script>try{var c=window.frameElement.closest('[data-testid=\"stElementContainer\"],.element-container');"
              "if(c){c.style.display='none';}}catch(e){}</script>" + html, height=1)


if not hasattr(st, "iframe"):                                 # older Streamlit
    import streamlit.components.v1 as _components
    st.iframe = lambda html, height=None: _components.html(html, height=height)

# ── Theme: "Dashboard V5" — light by default, dark on request (?theme=, like the dashboard) ──
_qp_theme = st.query_params.get("theme")
if _qp_theme in ("light", "dark"):
    st.session_state.theme = _qp_theme
THEME = st.session_state.setdefault("theme", "light")
_V5 = {
    "light": dict(bg="#e9ebf0", bar="#f9fafb", raised="#f9fafb", border="#d9dde5",
                  hi="#0f172a", mid="#334155", lo="#475569", track="#14161f"),
    "dark":  dict(bg="#0b0d14", bar="#11131c", raised="#1a1d2b", border="#232738",
                  hi="#f1f5f9", mid="#aab4c3", lo="#8a97a8", track="#1c1f2d"),
}[THEME]
_OWN = {"light": dict(own_a="#4f46e5", own_b="#0e7490", own_c="#047857", glow="rgba(79,70,229,0.28)", ring_gap="#ffffff"),
        "dark": dict(own_a="#818cf8", own_b="#22d3ee", own_c="#34d399", glow="rgba(99,102,241,0.45)", ring_gap="#11131c")}[THEME]
try:
    OWNER = json.loads(_read("dashboard_pages.json") or "{}").get("owner", {})
except ValueError:
    OWNER = {}

# ── Styling (the dashboard's streamlit_app.py look): hide Streamlit chrome, V5 top bar, title strip, buttons ──
_css = """<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,500,0,0&display=block');
  :root { --v5-bg:__bg__; --v5-bar:__bar__; --v5-raised:__raised__; --v5-border:__border__;
          --v5-hi:__hi__; --v5-mid:__mid__; --v5-lo:__lo__; --v5-track:__track__;
          --v5-indigo:#4f46e5; --v5-indigo-hi:#6366f1; }
  #MainMenu, footer {visibility: hidden;}
  [data-testid="stAppDeployButton"], .stAppDeployButton, [data-testid="stMainMenu"] {display:none !important;}
  section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"],
  [data-testid="stSidebarCollapseButton"], header[data-testid="stHeader"], [data-testid="stToolbar"],
  [data-testid="stDecoration"] {display:none !important;}
  .block-container {padding: 0.6rem 1.25rem 0 1.25rem !important; max-width: 100%;}
  .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {background: var(--v5-bg) !important;}
  .stApp, .stApp p, .stApp label, .stApp span:not([data-testid="stIconMaterial"]) {font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;}
  .st-key-refresh_btn [data-testid="stIconMaterial"] {font-size: 1rem !important;}
  .stApp .stMarkdown, .stApp .stMarkdown p {color: var(--v5-hi);}
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color: var(--v5-lo) !important;}
  [data-testid="stAlert"] p {color: var(--v5-hi) !important;}
  [data-testid="stProgress"] p {color: var(--v5-mid) !important;}
  /* Invisible helpers (style-only blocks, zero-height frames) must not add the row gap each */
  [data-testid="stElementContainer"][height="0px"],
  [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child) {display:none !important;}
  [data-testid="stElementContainer"]:has(> iframe[data-dash-page]) {height:auto !important;}

  /* ── Top bar ── */
  [data-testid="stElementContainer"]:has(.tn-bar), .element-container:has(.tn-bar) {position:sticky; top:0; z-index:999;}
  .tn-bar {display:flex; align-items:center; gap:1rem; padding:0.6rem 0.9rem; margin:0 0 0.2rem; min-width:0;
    background:var(--v5-bar); border:1px solid var(--v5-border); border-radius:16px; box-shadow:0 6px 18px rgba(16,24,40,0.06);}
  .tn-brand {display:flex; align-items:center; gap:0.6rem; flex-shrink:0;}
  .tn-mark {width:36px; height:36px; border-radius:11px; flex-shrink:0; display:flex; align-items:center; justify-content:center;
    background:linear-gradient(135deg,#4f46e5,#06b6d4); color:#fff; font-weight:800; font-size:0.78rem; box-shadow:0 4px 12px rgba(79,70,229,0.35);}
  .tn-nm {font-weight:800; font-size:0.92rem; color:var(--v5-hi); line-height:1.15;}
  .tn-sb {font-size:0.64rem; color:var(--v5-lo);}
  .tn-scroller {flex:1; min-width:0; display:flex; justify-content:center;}
  .tn-frame {display:flex; min-width:0; max-width:100%; border-radius:999px;}
  .tn-track {display:flex; align-items:center; gap:2px; max-width:100%; padding:4px; border-radius:999px; overflow-x:auto;
    background:var(--v5-track); box-shadow:0 6px 18px rgba(16,24,40,0.12);}
  .tn-item {display:inline-flex; align-items:center; gap:0.4rem; padding:0.46rem 0.85rem; border-radius:999px; flex-shrink:0;
    font-size:0.74rem; font-weight:600; white-space:nowrap; color:#a1a7bb !important; text-decoration:none !important; transition:background .2s, color .2s;}
  .tn-item:hover {color:#fff !important; background:rgba(255,255,255,0.07);}
  .tn-item.on {background:var(--v5-indigo); color:#fff !important; box-shadow:0 4px 14px rgba(79,70,229,0.5);}
  .tn-ic {font-family:'Material Symbols Rounded' !important; font-size:16px; line-height:1; font-weight:normal; font-style:normal;
    letter-spacing:normal; text-transform:none; white-space:nowrap; -webkit-font-feature-settings:'liga'; font-feature-settings:'liga';}
  .tn-right {display:flex; align-items:center; gap:0.6rem; flex-shrink:0;}
  .tn-theme {display:inline-flex; padding:3px; border-radius:999px; background:var(--v5-track);}
  .tn-th {display:inline-flex; align-items:center; gap:0.3rem; padding:0.36rem 0.7rem; border-radius:999px;
    font-size:0.7rem; font-weight:600; color:#a1a7bb !important; text-decoration:none !important;}
  .tn-th:hover {color:#fff !important;}
  .tn-th.on {background:var(--v5-indigo); color:#fff !important;}
  .tn-icon {width:36px; height:36px; border-radius:11px; display:inline-flex; align-items:center; justify-content:center;
    background:var(--v5-raised); border:1px solid var(--v5-border); color:var(--v5-mid) !important; text-decoration:none !important;}
  .tn-icon:hover {border-color:var(--v5-indigo); color:var(--v5-indigo) !important;}
  .tn-item:focus-visible, .tn-th:focus-visible, .tn-icon:focus-visible {outline:2px solid #818cf8; outline-offset:2px;}
  @media (max-width: 1100px) {.tn-bar {flex-wrap:wrap; row-gap:0.55rem;} .tn-scroller {order:3; flex-basis:100%;} .tn-right {margin-left:auto;}}
  @media (max-width: 640px) {.tn-sb, .tn-th .lbl, .tn-bar .v5-user .rl {display:none;} .tn-bar {padding:0.5rem 0.6rem; gap:0.6rem;}}

  /* Owner credit */
  .v5-user {display:flex; align-items:center; gap:0.55rem; margin:0; --own-a:__own_a__; --own-b:__own_b__; --own-c:__own_c__;}
  .v5-user .av {width:32px; height:32px; border-radius:50%; flex-shrink:0; background:linear-gradient(135deg,#1e1b4b,#4f46e5);
    color:#fff; font-size:0.68rem; font-weight:700; display:flex; align-items:center; justify-content:center;}
  .v5-user .nm {font-size:0.78rem; font-weight:700; color:var(--v5-hi); line-height:1.2;}
  .v5-user .rl {font-size:0.62rem; color:var(--v5-lo);}
  @property --own-spin {syntax:'<angle>'; initial-value:0deg; inherits:false;}
  .v5-user .av.owner-avatar {position:relative; isolation:isolate; box-shadow:0 0 0 2px __ring_gap__, 0 0 16px __glow__;}
  .v5-user .av.owner-avatar::before {content:''; position:absolute; inset:-4px; border-radius:50%; z-index:-1;
    background:conic-gradient(from var(--own-spin), var(--own-a), var(--own-b), var(--own-c), var(--own-a)); animation:ownSpin 6s linear infinite;}
  .v5-user .nm.owner-name {font-weight:800; background:linear-gradient(90deg,var(--own-a),var(--own-b),var(--own-c),var(--own-b),var(--own-a));
    background-size:200% auto; -webkit-background-clip:text; background-clip:text; color:transparent !important; animation:ownShimmer 6s linear infinite;}
  .v5-user .owner-spark {display:inline-block; margin-left:0.3rem; font-size:0.9em; color:#f59e0b; -webkit-text-fill-color:#f59e0b;
    animation:ownTwinkle 2.4s ease-in-out infinite;}
  .v5-user .rl.owner-role {display:inline-block; margin-top:3px; padding:0.12rem 0.5rem; border-radius:999px; font-weight:700;
    color:var(--v5-mid) !important; border:1px solid transparent;
    background:linear-gradient(var(--v5-raised),var(--v5-raised)) padding-box, linear-gradient(90deg,var(--own-a),var(--own-b),var(--own-c)) border-box;}
  @keyframes ownSpin {to {--own-spin:360deg;}}
  @keyframes ownShimmer {to {background-position:200% center;}}
  @keyframes ownTwinkle {0%,100% {opacity:0.6; transform:scale(0.85) rotate(0deg);}
    50% {opacity:1; transform:scale(1.15) rotate(20deg); text-shadow:0 0 8px rgba(245,158,11,0.75);}}
  @media (prefers-reduced-motion: reduce) {.v5-user .av.owner-avatar::before, .v5-user .nm.owner-name, .v5-user .owner-spark {animation:none !important;}}

  /* ── Title strip ── */
  .v5-title h1 {font-size: 1.08rem !important; font-weight: 800 !important; letter-spacing: -0.02em;
    color: var(--v5-hi) !important; margin: 0 !important; padding: 0 !important; line-height: 1.25;}
  .v5-title .pp {font-size: 0.76rem; color: var(--v5-lo); margin-top: 2px;}
  [data-testid="stHorizontalBlock"]:has(.v5-title) {background: var(--v5-bar); border: 1px solid var(--v5-border);
    border-radius: 14px; padding: 0.45rem 0.6rem 0.45rem 1rem; margin: 0.15rem 0 0.1rem; gap: 0.6rem;
    box-shadow: 0 4px 14px rgba(16,24,40,0.05);}
  .st-key-refresh_btn button {border-radius: 999px !important; font-weight: 600 !important; min-height: 36px !important; padding: 0 0.9rem !important;
    background: var(--v5-indigo) !important; border: 1px solid var(--v5-indigo) !important; color: #fff !important;
    box-shadow: 0 6px 16px rgba(79,70,229,0.35); transition: transform .16s cubic-bezier(.16,1,.3,1), background .16s;}
  .st-key-refresh_btn button:hover {background: var(--v5-indigo-hi) !important; transform: translateY(-1px);}
  .st-key-refresh_btn button p {color: #fff !important; font-size: 0.8rem !important; font-weight: 600 !important;}
  @media (max-width: 900px) {.st-key-refresh_btn button p {display:none !important;} .st-key-refresh_btn button {min-width:44px;}}
</style>"""
for _k, _v in {**_V5, **_OWN}.items():
    _css = _css.replace("__" + _k + "__", _v)
if SHOW_DEPLOY:   # bring back Streamlit's header (Deploy button) and start the page below it
    _css = (_css.replace('[data-testid="stAppDeployButton"], .stAppDeployButton, [data-testid="stMainMenu"] {display:none !important;}', '')
            .replace('header[data-testid="stHeader"], [data-testid="stToolbar"],', '')
            .replace('.block-container {padding: 0.6rem 1.25rem 0 1.25rem !important;', '.block-container {padding: 3.6rem 1.25rem 0 1.25rem !important;')
            .replace('[data-testid="stElementContainer"]:has(.tn-bar), .element-container:has(.tn-bar) {position:sticky; top:0;',
                     '[data-testid="stElementContainer"]:has(.tn-bar), .element-container:has(.tn-bar) {position:sticky; top:3.75rem;')
            .replace('</style>', '  header[data-testid="stHeader"] {background: var(--v5-bg) !important;}\n</style>'))
st.markdown(_css, unsafe_allow_html=True)

# ── Top bar: brand · the page tab (travelling light) · Light / Dark · contact · owner ──
_themes = "".join(
    f"<a class='tn-th{' on' if THEME == m else ''}' href='?theme={m}' target='_self' aria-label='{l} theme'>"
    f"<span class='tn-ic' aria-hidden='true'>{ic}</span><span class='lbl'>{l}</span></a>"
    for m, l, ic in (("light", "Light", "light_mode"), ("dark", "Dark", "dark_mode")))
_owner = ("<div class='v5-user' title='Built and maintained by " + _esc(OWNER.get("name", ""), quote=True) + ", "
          + _esc(OWNER.get("title", ""), quote=True) + "'><div class='av owner-avatar'>" + _esc(OWNER.get("initials", "JO")) + "</div><div>"
          "<div class='nm owner-name'>" + _esc(OWNER.get("name", "")) + "<span class='owner-spark' aria-hidden='true'>✦</span></div>"
          "<div class='rl owner-role'>" + _esc(OWNER.get("title", "")) + "</div></div></div>") if OWNER.get("name") else ""
_mail = (f"<a class='tn-icon' href='mailto:{_esc(OWNER.get('email', ''), quote=True)}' title='Contact &amp; help' "
         "aria-label='Contact the owner by email'><span class='tn-ic' aria-hidden='true'>mail</span></a>") if OWNER.get("email") else ""
st.markdown(
    "<div class='tn-bar'>"
    "<div class='tn-brand'><div class='tn-mark'>DA</div><div><div class='tn-nm'>Denri Africa</div>"
    "<div class='tn-sb'>Stocks Picking</div></div></div>"
    "<div class='tn-scroller'><div class='tn-frame tn-glow'><nav class='tn-track' aria-label='Pages'>"
    f"<a class='tn-item on' href='?theme={THEME}' target='_self' aria-current='page' title='{_esc(PURPOSE, quote=True)}'>"
    "<span class='tn-ic' aria-hidden='true'>stacked_bar_chart</span>Stocks Picking</a></nav></div></div>"
    "<div class='tn-right'><div class='tn-theme' role='group' aria-label='Colour theme'>" + _themes + "</div>"
    + _mail + _owner + "</div></div>", unsafe_allow_html=True)
_topnav_js = _read("top_nav.js")                             # defines .tn-glow (the travelling light) + tab scrolling
if _topnav_js:
    _run_js("<script>(function(){var P=window.parent,D;try{D=P.document;}catch(e){return;}"
            "if(!P.TopNav){var s=D.createElement('script');s.textContent=" + json.dumps(_topnav_js).replace("</", "<\\/") +
            ";D.head.appendChild(s);}if(P.TopNav&&P.TopNav.injectCss){P.TopNav.injectCss(D);}"
            "var n=0;(function go(){var t=D.querySelector('.tn-track');if(t&&P.TopNav){P.TopNav.attach(t);}else if(n++<100){setTimeout(go,100);}})();})();</script>")

# ── Title strip: title + purpose · live clock pill (travelling light, "Updated …") · Refresh ──
CLOCK_HTML = """
<div class="pill" title="Live clock · when this page's data was last rebuilt from Odoo"><span class="dot"></span><span id="clk"></span><span class="sep"></span><span class="upd">__AGO__</span></div>
<style>
  body{margin:0;background:transparent;font-family:'Inter','Segoe UI',system-ui,sans-serif;display:flex;justify-content:flex-end;align-items:center;height:100vh}
  .pill{position:relative;display:inline-flex;align-items:center;gap:0.45rem;padding:0.5rem 0.85rem;border-radius:999px;
        background:__raised__;border:1px solid __border__;white-space:nowrap}
  @property --g{syntax:'<angle>';initial-value:0deg;inherits:false}
  .pill::after{content:'';position:absolute;inset:-1px;border-radius:inherit;padding:1.5px;pointer-events:none;
    background:conic-gradient(from var(--g),transparent 0deg 30deg,#a855f7 60deg,#ec4899 80deg,transparent 100deg 210deg,#a855f7 240deg,#ec4899 260deg,transparent 280deg);
    -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;
    mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);mask-composite:exclude;animation:gspin 5s linear infinite}
  @keyframes gspin{to{--g:360deg}}
  .dot{width:8px;height:8px;border-radius:50%;background:#10b981;display:inline-block;animation:pulse 1.8s ease-out infinite}
  #clk{font-size:0.74rem;color:__mid__;font-weight:600;font-variant-numeric:tabular-nums}
  .sep{width:1px;height:14px;background:__border__}
  .upd{font-size:0.7rem;color:__lo__;font-weight:500}
  @media (max-width:330px){.sep,.upd{display:none}}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(16,185,129,0.5)}70%{box-shadow:0 0 0 7px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}
  @media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>
<script>
  function tick(){
    var n=new Date(), d=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'], m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var p=function(x){return String(x).padStart(2,'0')};
    document.getElementById('clk').textContent = d[n.getDay()]+' '+n.getDate()+' '+m[n.getMonth()]+' \\u00b7 '+p(n.getHours())+':'+p(n.getMinutes())+':'+p(n.getSeconds());
  }
  tick(); setInterval(tick,1000);
  /*RELOAD*/
</script>
"""
for _k in ("raised", "border", "mid", "lo"):
    CLOCK_HTML = CLOCK_HTML.replace("__" + _k + "__", _V5[_k])
CLOCK_HTML = CLOCK_HTML.replace("__AGO__", _ago(_page_age_secs()))
if not NO_AUTOREFRESH:   # an idle tab reloads itself once the interval passes, so the auto-refresh check fires
    CLOCK_HTML = CLOCK_HTML.replace("/*RELOAD*/", "setTimeout(function(){ try{ (window.top||window.parent||window).location.reload(); }"
                                    "catch(e){ location.reload(); } }, " + str(_AUTO_SECS * 1000) + ");")

_tt, _ck, _rc = st.columns([0.55, 0.34, 0.11], vertical_alignment="center")
with _tt:
    st.markdown("<div class='v5-title'><h1>" + _esc(TITLE) + "</h1><div class='pp'>" + _esc(PURPOSE) + "</div></div>",
                unsafe_allow_html=True)
with _ck:
    st.iframe(CLOCK_HTML, height=44)
with _rc:
    if st.button("Refresh", icon=":material/refresh:", use_container_width=True, type="primary", key="refresh_btn",
                 help="Rebuild the page now from Odoo (about 40 s). The last build stays on screen until it's ready."):
        start_build("manual")

if not NO_AUTOREFRESH and _page_age_secs() >= _AUTO_SECS:
    start_build("auto")


@st.fragment(run_every=2)
def _watch():
    """While a rebuild runs: a progress bar; when it ends, rerun the app so the new page shows."""
    j = _job()
    if j["running"]:
        st.session_state.watching = j["started"]
        el = time.time() - j["started"]
        what = "Refreshing" if j["kind"] == "manual" else "Auto-refreshing"
        if j["secs"]:
            st.progress(min(0.97, el / j["secs"]), text=f"⟳ {what} — {int(el)} s of ~{int(j['secs'])} s · showing the last build until it's ready")
        else:
            st.progress(min(0.9, el / 60), text=f"⟳ {what} — {int(el)} s so far · showing the last build until it's ready")
    elif st.session_state.get("watching") and st.session_state.watching == j["started"]:
        st.session_state.watching = None
        st.session_state.done_msg = (j["ok"], j["log"])
        st.rerun(scope="app")


_watch()


@st.fragment(run_every=60)
def _idle_check():
    """An open, idle tab still auto-refreshes: every minute, rebuild if the page is older than the interval."""
    if not NO_AUTOREFRESH and _page_age_secs() >= _AUTO_SECS and start_build("auto"):
        st.rerun(scope="app")


_idle_check()

msg = st.session_state.pop("done_msg", None)
if msg:
    if msg[0]:
        st.toast("Updated from Odoo.", icon="✅")
    else:
        st.error("The refresh failed — still showing the last build.", icon=":material/error:")
        with st.expander("Build log"):
            st.code(msg[1] or "(no output)")

# ── The page ──
# Sizes the frame to the page's real height (no inner scroll bar) and drops its viewport-height rules.
EMBED_FIX = """
<style id="st-embed-fix">
  html, body { min-height:0 !important; height:auto !important; overflow-y:visible !important; overflow-x:hidden !important; max-width:100% !important; }
  .wrap { min-height:0 !important; }
  @media (max-width: 640px){ body { padding-left:0.6rem !important; padding-right:0.6rem !important; } }
</style>
<script>
(function(){
  var last = 0, pend = null;
  function fit(){
    try{
      var h = document.body ? document.body.scrollHeight : document.documentElement.scrollHeight;
      if (window.frameElement && h && Math.abs(h - last) > 2){
        last = h; window.frameElement.setAttribute('data-dash-page', '');
        window.frameElement.style.height = h + 'px'; window.frameElement.style.minHeight = h + 'px';
      }
    }catch(e){}
  }
  function schedule(){ if(pend) return; pend = setTimeout(function(){ pend=null; fit(); }, 120); }
  window.addEventListener('load', fit); window.addEventListener('resize', schedule);
  document.addEventListener('change', schedule, true); document.addEventListener('click', schedule, true);
  document.addEventListener('input', schedule, true);
  [150, 500, 1200, 2500].forEach(function(t){ setTimeout(fit, t); });
  try { new MutationObserver(schedule).observe(document.documentElement, {subtree:true, childList:true}); } catch(e){}
})();
</script>
"""


@st.cache_data(show_spinner=False)
def _page(mtime, theme, look_mtime):
    """The page HTML as the dashboard serves its pages: local scripts inlined (the frame has no URL to load them
    from), the V5 theme (light / dark) and drag-to-reorder added, sized to its content. Keyed on the page's
    mtime, the theme and the look files' mtimes, so the frame only re-renders when one of them changes."""
    html = _read(os.path.basename(HTML), BASE)

    def inline(m):
        code = _read(m.group(1), BASE)
        return ("<script>/* " + m.group(1) + " */\n" + code.replace("</script", "<\\/script") + "\n</script>") if code else m.group(0)
    html = re.sub(r'<script\s+src="([^":/]+\.js)"\s*>\s*</script>', inline, html)
    look = ""
    css, js = _read("v5_theme.css"), _read("v5_theme.js")
    if css and js:
        look += ('<style id="v5-css" data-v5>' + css + '</style><script>/* v5_theme.js */\n' + js.replace("</script", "<\\/script")
                 + '\n</script><script>(function(){var m="' + theme + '";'
                 'function go(){try{window.V5Theme&&V5Theme.apply(document,m);}catch(e){console.error("V5 theme",e);}}'
                 'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",go);else go();'
                 'window.addEventListener("load",go);})();</script>')
    drag = _read("kpi_drag.js")
    if drag:
        look += "<script>/* kpi_drag.js */\n" + drag.replace("</script", "<\\/script") + "\n</script>"
    html = html.replace("</body>", look + EMBED_FIX + "</body>", 1)
    return html + f"\n<!-- v:{mtime} theme:{theme} look:{look_mtime} -->"


if os.path.exists(HTML):
    _look_mtime = max([int(os.path.getmtime(os.path.join(DASHBOARD, f))) for f in ("v5_theme.css", "v5_theme.js", "kpi_drag.js")
                       if os.path.exists(os.path.join(DASHBOARD, f))] or [0])
    st.iframe(_page(int(os.path.getmtime(HTML)), THEME, _look_mtime), height=900)
else:
    st.warning("The page hasn't been built yet. Click **Refresh** to build it from Odoo.")
