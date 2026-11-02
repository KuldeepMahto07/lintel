"""Database access: SQLite locally and in tests, Postgres when DATABASE_URL is set.

SQL is written once with `?` placeholders; the Postgres path rewrites them to `%s`.
Timestamps are epoch seconds (float) and JSON columns are text, so the same queries run on both.
"""
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = Path(__file__).resolve().parent / "migrations"

_lock = threading.RLock()
_conn = None
_path = None
_local = threading.local()


def url():
    return os.environ.get("DATABASE_URL", "")


def is_pg():
    return url().startswith(("postgres://", "postgresql://"))


def sqlite_path():
    return Path(_path or os.environ.get("LINTEL_DB") or ROOT / "data" / "lintel.db")


def reset(path=None):
    """Point at another SQLite file (tests, e2e) and drop the open connection."""
    global _conn, _path
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
        _conn, _path = None, path


def _connect():
    if is_pg():
        import psycopg  # production only
        from psycopg.rows import dict_row
        return psycopg.connect(url(), row_factory=dict_row, autocommit=True)
    p = sqlite_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, check_same_thread=False, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("pragma foreign_keys = on")
    return c


def conn():
    global _conn
    with _lock:
        if _conn is None:
            _conn = _connect()
            migrate(_conn)
        return _conn


def _sql(sql):
    return sql.replace("?", "%s") if is_pg() else sql


def _exec(sql, args=()):
    c = conn()
    if is_pg():
        cur = c.cursor()
        cur.execute(_sql(sql), args)
        return cur
    return c.execute(sql, args)


@contextmanager
def tx():
    """One transaction for a group of writes (an audit entry commits with the change it describes)."""
    with _lock:
        depth = getattr(_local, "depth", 0)
        if depth == 0:
            _exec("begin")
        _local.depth = depth + 1
        try:
            yield
        except BaseException:
            _local.depth = depth
            if depth == 0:
                _exec("rollback")
            raise
        _local.depth = depth
        if depth == 0:
            _exec("commit")


def all(sql, args=()):
    with _lock:
        return [dict(r) for r in _exec(sql, args).fetchall()]


def one(sql, args=()):
    with _lock:
        r = _exec(sql, args).fetchone()
        return dict(r) if r else None


def val(sql, args=()):
    r = one(sql, args)
    return next(iter(r.values())) if r else None


def run(sql, args=()):
    """Execute a write; commits on its own unless inside tx(). Returns the row count."""
    with tx():
        return _exec(sql, args).rowcount


def migrate(c):
    """Apply migrations/NNNN_*.sql in order, once each."""
    pg = is_pg()
    cur = c.cursor()
    cur.execute("create table if not exists schema_migrations (name text primary key)")
    cur.execute("select name from schema_migrations")
    done = {r["name"] if pg else r[0] for r in cur.fetchall()}
    if not pg and not done:
        _set_aside_v1(cur)
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name in done:
            continue
        text = "\n".join(l for l in f.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--"))
        if pg:
            text = (text.replace("integer primary key autoincrement", "bigserial primary key")
                        .replace(" real", " double precision").replace(" collate nocase", ""))
        cur.execute("begin")
        for stmt in [s.strip() for s in text.split(";") if s.strip()]:
            cur.execute(stmt)
        cur.execute(_sql("insert into schema_migrations (name) values (?)"), (f.name,))
        cur.execute("commit")


def _set_aside_v1(cur):
    """A database from the single-user MVP has tables with the same names; keep them as *_v1."""
    cur.execute("select name from sqlite_master where type='table'")
    old = {r[0] for r in cur.fetchall()} & {"projects", "snapshots", "rules", "changesets", "audit", "chat", "waitlist"}
    for t in sorted(old):
        cur.execute(f"alter table {t} rename to {t}_v1")


def health():
    try:
        val("select 1 as ok")
        return "ok"
    except Exception as e:  # reported by /api/health, never raised
        return f"error: {type(e).__name__}"
