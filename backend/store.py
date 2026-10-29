"""SQLite persistence: projects, model snapshots, rules, change sets, audit log, chat."""
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

DB_PATH = Path(os.environ.get("LINTEL_DB", Path(__file__).resolve().parent.parent / "data" / "lintel.db"))
_lock = threading.Lock()

SCHEMA = """
create table if not exists projects (id text primary key, name text, host text, created real);
create table if not exists snapshots (id integer primary key autoincrement, project text, host text, taken real, elements text);
create table if not exists rules (id text primary key, data text, status text, created real);
create table if not exists changesets (id text primary key, project text, title text, reason text, ops text,
  status text, source text, rule text, created real, updated real, error text, reverts text);
create table if not exists audit (id integer primary key autoincrement, ts real, project text, actor text,
  action text, target text, detail text);
create table if not exists chat (project text primary key, messages text);
"""

_db = None


def db():
    global _db
    if _db is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(DB_PATH, check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db.executescript(SCHEMA)
    return _db


def reset(path):
    """Point the store at another database file (tests, e2e)."""
    global _db, DB_PATH
    DB_PATH = Path(path)
    _db = None


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _write(sql, args=()):
    with _lock:
        db().execute(sql, args)
        db().commit()


# ---- audit -----------------------------------------------------------------

def audit(project, actor, action, target="", detail=None):
    _write("insert into audit (ts, project, actor, action, target, detail) values (?,?,?,?,?,?)",
           (time.time(), project, actor, action, target, json.dumps(detail or {})))


def audit_log(project=None, limit=500):
    q = "select * from audit" + (" where project=?" if project else "") + " order by id desc limit ?"
    rows = db().execute(q, (project, limit) if project else (limit,)).fetchall()
    return [dict(r, detail=json.loads(r["detail"])) for r in rows]


# ---- projects & snapshots --------------------------------------------------

def ensure_project(pid, name=None, host=None):
    row = db().execute("select * from projects where id=?", (pid,)).fetchone()
    if row:
        if host and row["host"] != host:
            _write("update projects set host=? where id=?", (host, pid))
        return
    _write("insert into projects values (?,?,?,?)", (pid, name or pid, host or "", time.time()))
    audit(pid, "system", "project.created", pid, {"name": name or pid, "host": host})


def project(pid):
    r = db().execute("select * from projects where id=?", (pid,)).fetchone()
    return dict(r) if r else None


def projects():
    out = []
    for r in db().execute("select * from projects order by created").fetchall():
        p = dict(r)
        snap = latest_snapshot(p["id"])
        p["snapshot_at"] = snap["taken"] if snap else None
        p["element_count"] = len(snap["elements"]) if snap else 0
        p["pending"] = db().execute("select count(*) from changesets where project=? and status='proposed'",
                                    (p["id"],)).fetchone()[0]
        out.append(p)
    return out


def save_snapshot(pid, host, elements):
    _write("insert into snapshots (project, host, taken, elements) values (?,?,?,?)",
           (pid, host, time.time(), json.dumps(elements)))


def latest_snapshot(pid):
    r = db().execute("select * from snapshots where project=? order by id desc limit 1", (pid,)).fetchone()
    return dict(r, elements=json.loads(r["elements"])) if r else None


# ---- rules -----------------------------------------------------------------

def _rule(r):
    return dict(json.loads(r["data"]), id=r["id"], status=r["status"]) if r else None


def rules(status=None):
    q = "select * from rules" + (" where status=?" if status else "") + " order by created"
    return [_rule(r) for r in db().execute(q, (status,) if status else ()).fetchall()]


def get_rule(rid):
    return _rule(db().execute("select * from rules where id=?", (rid,)).fetchone())


def put_rule(rule, status="active"):
    rid = rule.get("id") or new_id("rule")
    data = {k: v for k, v in rule.items() if k not in ("id", "status")}
    _write("insert into rules (id, data, status, created) values (?,?,?,?) "
           "on conflict(id) do update set data=excluded.data, status=excluded.status",
           (rid, json.dumps(data), status, time.time()))
    return rid


def delete_rule(rid):
    _write("delete from rules where id=?", (rid,))


# ---- change sets -----------------------------------------------------------

def _cs(r):
    return dict(r, ops=json.loads(r["ops"])) if r else None


def add_changeset(pid, title, reason, ops, source, rule=None, status="proposed", reverts=None):
    cid = new_id("cs")
    now = time.time()
    _write("insert into changesets values (?,?,?,?,?,?,?,?,?,?,?,?)",
           (cid, pid, title, reason, json.dumps(ops), status, source, rule, now, now, None, reverts))
    return cid


def changeset(cid):
    return _cs(db().execute("select * from changesets where id=?", (cid,)).fetchone())


def changesets(pid, status=None):
    q = "select * from changesets where project=?" + (" and status=?" if status else "") + " order by created desc"
    return [_cs(r) for r in db().execute(q, (pid, status) if status else (pid,)).fetchall()]


def set_changeset_status(cid, status, error=None):
    _write("update changesets set status=?, error=?, updated=? where id=?", (status, error, time.time(), cid))


# ---- chat ------------------------------------------------------------------

def chat_messages(pid):
    r = db().execute("select messages from chat where project=?", (pid,)).fetchone()
    return json.loads(r["messages"]) if r else []


def save_chat(pid, messages):
    _write("insert into chat values (?,?) on conflict(project) do update set messages=excluded.messages",
           (pid, json.dumps(messages)))
