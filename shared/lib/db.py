"""lib/db.py — Postgres access for the marketing dashboard.

Deliberately the SAME surface as the Streamlit app's lib.db so the existing
queries and report code port straight in when we migrate the rest of the
dashboard: run_query(sql, params) -> DataFrame, plus check_connection().

Connection comes from the environment (a .env in this folder is loaded):
    DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname
  — or the individual pieces —
    PGHOST=... PGPORT=5432 PGDATABASE=... PGUSER=... PGPASSWORD=...

Named params use :name placeholders, e.g.
    run_query("SELECT ... WHERE d BETWEEN :start_date AND :end_date",
              {"start_date": s, "end_date": e})
"""
from __future__ import annotations

import os
import time
import json
import pickle
import hashlib
import threading
from functools import lru_cache

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

load_dotenv()

# A per-thread reused connection. Every run_query reuses one connection for the life
# of the (short-lived) generator process instead of borrowing a fresh one from the pool
# — which, with pool_pre_ping, costs a round-trip PING before every query. On the
# high-latency Supabase pooler that ping dominates a refresh; reuse cuts ~1s per query.
_local = threading.local()


def _env(*names: str, default: str | None = None) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return default


def _url():
    """Build a SQLAlchemy URL from the environment, or None if unset.
    Accepts DATABASE_URL, or the individual PG*/DB_* pieces (DB_* matches the
    Streamlit app's .env). URL.create handles any special chars in the password."""
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        if dsn.startswith("postgres://"):
            dsn = "postgresql+psycopg2://" + dsn[len("postgres://"):]
        elif dsn.startswith("postgresql://") and "+psycopg2" not in dsn:
            dsn = "postgresql+psycopg2://" + dsn[len("postgresql://"):]
        return dsn
    host = _env("PGHOST", "DB_HOST")
    if not host:
        return None
    return URL.create(
        "postgresql+psycopg2",
        username=_env("PGUSER", "DB_USER", default=""),
        password=_env("PGPASSWORD", "DB_PASSWORD", default=""),
        host=host,
        port=int(_env("PGPORT", "DB_PORT", default="5432")),
        database=_env("PGDATABASE", "DB_NAME", default=""),
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine | None:
    url = _url()
    if url is None:
        return None
    # pool_pre_ping avoids stale-connection errors on a long-lived generator run.
    # create_engine imports the DB driver (psycopg2) eagerly — if it isn't
    # installed in whichever Python runs the dashboard, return None so callers
    # fall back to the sheet instead of the whole refresh crashing.
    try:
        # connect_timeout caps how long a connection attempt waits. Without it, a
        # blocked/unreachable DB (e.g. a firewall dropping packets from a cloud host)
        # hangs for a minute+ per attempt, making a refresh drag on. 10s → fail fast.
        return create_engine(url, pool_pre_ping=True, future=True,
                             connect_args={"connect_timeout": 20})
    except ImportError as e:   # psycopg2 missing in this Python, etc.
        print(f"  DB driver not installed ({e}) — falling back to sheet data.")
        return None


def check_connection() -> tuple[bool, str]:
    """(ok, detail). Never raises — the callers show `detail` in the UI."""
    eng = get_engine()
    if eng is None:
        return False, ("No database configured. Set DATABASE_URL (or PGHOST/…) "
                       "in a .env file — see .env.example.")
    try:
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        return True, "connected"
    except Exception as e:                                   # noqa: BLE001
        return False, str(e)


def _shared_conn():
    """The process's reused connection (opened on first query). Every generator runs
    as its own short-lived subprocess, so holding one connection for the run — instead
    of borrowing + pinging a fresh one per query — is safe and cuts ~1s off each query
    on the high-latency pooler. Returns None if the DB is unreachable."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            if not conn.closed:
                return conn
        except Exception:                                    # noqa: BLE001
            pass
    eng = get_engine()
    if eng is None:
        _local.conn = None
        return None
    try:
        _local.conn = eng.connect()
    except Exception:                                        # noqa: BLE001
        _local.conn = None
    return getattr(_local, "conn", None)


def _drop_shared_conn():
    c = getattr(_local, "conn", None)
    _local.conn = None
    if c is not None:
        try:
            c.close()
        except Exception:                                    # noqa: BLE001
            pass


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame | None:
    """Run a read query and return a DataFrame, or None if the DB is unreachable.

    Matches lib.db.run_query from the Streamlit app so report code is portable.
    Queries reuse one per-process connection (see _shared_conn); if it has gone stale
    the query is retried once on a fresh connection.
    """
    if get_engine() is None:
        return None
    last_err = None
    for attempt in (1, 2):
        conn = _shared_conn()
        if conn is None:
            return None
        try:
            return pd.read_sql(text(sql), conn, params=params or {})
        except Exception as e:                               # noqa: BLE001
            last_err = e
            _drop_shared_conn()                              # maybe stale — reconnect & retry once
    print(f"  DB query failed: {last_err}")
    return None


# ── TTL disk cache ────────────────────────────────────────────
# Slow Odoo lookups (a month of POS lines, per-bag price scans, live stock) are cached to
# disk keyed by the exact SQL + params, so a repeated identical query within `ttl_min` is
# served from disk instead of re-hitting the high-latency pooler. Persists across the
# short-lived generator subprocesses. A manual Refresh sets DENRI_FORCE_FRESH=1 to bypass
# the read and repopulate; if the DB is unreachable, a stale cached copy is returned.
_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".odoo_cache")


def _cache_path(sql: str, params: dict | None) -> str:
    raw = " ".join(sql.split()) + "\x00" + json.dumps(params or {}, sort_keys=True, default=str)
    return os.path.join(_CACHE_DIR, hashlib.sha1(raw.encode("utf-8")).hexdigest() + ".pkl")


def run_query_cached(sql: str, params: dict | None = None, ttl_min: float = 30) -> pd.DataFrame | None:
    """run_query with a TTL disk cache. Identical to run_query for callers, but a repeated
    identical (sql, params) within ttl_min minutes is read from disk instead of Odoo.
    DENRI_FORCE_FRESH=1 (set by a manual Refresh) skips the read and refreshes the file.
    If the DB is unreachable, any cached copy (even expired) is returned as a fallback."""
    path = _cache_path(sql, params)
    if os.getenv("DENRI_FORCE_FRESH") != "1":
        try:
            if (time.time() - os.path.getmtime(path)) < ttl_min * 60:
                with open(path, "rb") as f:
                    return pickle.load(f)
        except Exception:                                    # noqa: BLE001 — miss → fetch
            pass
    df = run_query(sql, params)
    if df is not None:
        try:
            os.makedirs(_CACHE_DIR, exist_ok=True)
            with open(path, "wb") as f:
                pickle.dump(df, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:                                    # noqa: BLE001 — cache write is best-effort
            pass
        return df
    # DB unreachable — fall back to a stale cached copy if we have one.
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:                                        # noqa: BLE001
        return None
