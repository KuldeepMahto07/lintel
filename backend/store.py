"""Repository layer. Every function that touches firm data takes firm_id and puts it in the WHERE
clause (directly, or through projects.firm_id), so one firm can never read another firm's rows."""
import hashlib
import json
import os
import secrets
import time
import uuid

from . import db, plans

DAY = 86400


def now():
    return time.time()


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def sha(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _j(v):
    return json.dumps(v, separators=(",", ":"), default=str)


def _l(v, default=None):
    return json.loads(v) if v else default


# ---- users -----------------------------------------------------------------

def create_user(email, name, password_hash):
    uid = new_id("usr")
    db.run("insert into users (id, email, name, password_hash, created_at) values (?,?,?,?,?)",
           (uid, email.strip().lower(), name.strip(), password_hash, now()))
    return uid


def user(uid):
    return db.one("select id, email, name, created_at, last_login_at from users where id=? and deleted_at is null", (uid,))


def user_by_email(email):
    return db.one("select * from users where email=? and deleted_at is null", (email.strip().lower(),))


def password_hash(uid):
    return db.val("select password_hash from users where id=?", (uid,))


def update_user(uid, **fields):
    allowed = {k: v for k, v in fields.items() if k in ("name", "email", "password_hash", "last_login_at")}
    if allowed:
        db.run(f"update users set {', '.join(k + '=?' for k in allowed)} where id=?", (*allowed.values(), uid))


# ---- firms and memberships -------------------------------------------------

def create_firm(name, plan="free", seats=1, trial_ends_at=None):
    """The firm's data region is the region of the deployment that created it (LINTEL_REGION)."""
    fid = new_id("frm")
    db.run("insert into firms (id, name, plan, seats, trial_ends_at, created_at, region) values (?,?,?,?,?,?,?)",
           (fid, name.strip(), plan, seats, trial_ends_at, now(), os.environ.get("LINTEL_REGION") or None))
    return fid


def sso_firms():
    return [firm(r["id"]) for r in db.all("select id from firms where sso is not null and deleted_at is null")]


def firm(fid):
    f = db.one("select * from firms where id=? and deleted_at is null", (fid,))
    if f:
        f["two_approvals"], f["chat_enabled"] = bool(f["two_approvals"]), bool(f["chat_enabled"])
        f["sso"] = _l(f.get("sso"), None)
        f["pilot"] = bool(f.get("pilot"))
    return f


def update_firm(fid, **fields):
    allowed = {k: v for k, v in fields.items()
               if k in ("name", "plan", "seats", "two_approvals", "chat_enabled", "trial_ends_at", "billing_customer_id", "deleted_at",
                         "chat_cap_override", "region", "sso", "pilot")}
    if "sso" in allowed and allowed["sso"] is not None:
        allowed["sso"] = _j(allowed["sso"])
    if allowed:
        db.run(f"update firms set {', '.join(k + '=?' for k in allowed)} where id=?", (*allowed.values(), fid))


def add_member(fid, uid, role):
    db.run("insert into memberships (user_id, firm_id, role, created_at) values (?,?,?,?)", (uid, fid, role, now()))


def role(fid, uid):
    return db.val("select role from memberships where firm_id=? and user_id=?", (fid, uid))


def members(fid):
    return db.all("select u.id, u.name, u.email, m.role, m.created_at, u.last_login_at from memberships m "
                  "join users u on u.id=m.user_id where m.firm_id=? and u.deleted_at is null order by m.created_at", (fid,))


def set_role(fid, uid, new_role):
    db.run("update memberships set role=? where firm_id=? and user_id=?", (new_role, fid, uid))


def remove_member(fid, uid):
    with db.tx():
        db.run("delete from memberships where firm_id=? and user_id=?", (fid, uid))
        db.run("delete from sessions where firm_id=? and user_id=?", (fid, uid))
        db.run("update plugin_tokens set revoked_at=? where firm_id=? and user_id=? and revoked_at is null", (now(), fid, uid))


def firms_for_user(uid):
    return db.all("select f.id, f.name, m.role from memberships m join firms f on f.id=m.firm_id "
                  "where m.user_id=? and f.deleted_at is null order by m.created_at", (uid,))


def seats_in_use(fid):
    return db.val("select count(*) as n from memberships where firm_id=? and role != 'viewer'", (fid,))


# ---- invites ---------------------------------------------------------------

def create_invite(fid, email, role_, invited_by, days=7):
    token = secrets.token_urlsafe(32)
    iid = new_id("inv")
    db.run("insert into invites (id, firm_id, email, role, token_hash, invited_by, created_at, expires_at) values (?,?,?,?,?,?,?,?)",
           (iid, fid, email.strip().lower(), role_, sha(token), invited_by, now(), now() + days * DAY))
    return iid, token


def invite_by_token(token):
    return db.one("select i.*, f.name as firm_name from invites i join firms f on f.id=i.firm_id "
                  "where i.token_hash=? and f.deleted_at is null", (sha(token),))


def invites(fid):
    return db.all("select id, email, role, created_at, expires_at from invites where firm_id=? and accepted_at is null "
                  "and cancelled_at is null order by created_at desc", (fid,))


def invite(fid, iid):
    return db.one("select * from invites where firm_id=? and id=?", (fid, iid))


def mark_invite(iid, field):
    assert field in ("accepted_at", "cancelled_at")
    db.run(f"update invites set {field}=? where id=?", (now(), iid))


def rotate_invite(fid, iid, days=7):
    token = secrets.token_urlsafe(32)
    db.run("update invites set token_hash=?, expires_at=? where firm_id=? and id=?", (sha(token), now() + days * DAY, fid, iid))
    return token


# ---- sessions --------------------------------------------------------------

def create_session(uid, fid, user_agent="", days=30):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    db.run("insert into sessions (id_hash, user_id, firm_id, csrf, created_at, expires_at, user_agent) values (?,?,?,?,?,?,?)",
           (sha(token), uid, fid, csrf, now(), now() + days * DAY, (user_agent or "")[:200]))
    return token


def session(token):
    if not token:
        return None
    return db.one("select * from sessions where id_hash=? and expires_at>?", (sha(token), now()))


def set_session_firm(token, fid):
    db.run("update sessions set firm_id=? where id_hash=?", (fid, sha(token)))


def delete_session(token):
    db.run("delete from sessions where id_hash=?", (sha(token),))


def delete_user_sessions(uid, keep_token=None):
    if keep_token:
        db.run("delete from sessions where user_id=? and id_hash!=?", (uid, sha(keep_token)))
    else:
        db.run("delete from sessions where user_id=?", (uid,))


# ---- password resets -------------------------------------------------------

def create_reset(uid, minutes=30):
    token = secrets.token_urlsafe(32)
    db.run("insert into password_resets (token_hash, user_id, expires_at) values (?,?,?)", (sha(token), uid, now() + minutes * 60))
    return token


def use_reset(token):
    """Returns the user id once; the token is spent either way."""
    r = db.one("select * from password_resets where token_hash=? and used_at is null and expires_at>?", (sha(token), now()))
    if not r:
        return None
    db.run("update password_resets set used_at=? where token_hash=?", (now(), sha(token)))
    return r["user_id"]


# ---- plugin tokens ---------------------------------------------------------

def create_token(uid, fid, name):
    token = "lnt_" + secrets.token_urlsafe(30)
    tid = new_id("tok")
    db.run("insert into plugin_tokens (id, user_id, firm_id, name, token_hash, prefix, created_at) values (?,?,?,?,?,?,?)",
           (tid, uid, fid, name.strip()[:80], sha(token), token[:8], now()))
    return tid, token


def tokens(uid, fid):
    return db.all("select id, name, prefix, last_used_at, created_at, revoked_at from plugin_tokens "
                  "where user_id=? and firm_id=? order by created_at desc", (uid, fid))


def token_owner(token):
    t = db.one("select t.*, m.role from plugin_tokens t join memberships m on m.user_id=t.user_id and m.firm_id=t.firm_id "
               "join firms f on f.id=t.firm_id where t.token_hash=? and t.revoked_at is null and f.deleted_at is null",
               (sha(token),))
    if t:
        db.run("update plugin_tokens set last_used_at=? where id=?", (now(), t["id"]))
    return t


def revoke_token(uid, fid, tid):
    return db.run("update plugin_tokens set revoked_at=? where id=? and user_id=? and firm_id=? and revoked_at is null",
                  (now(), tid, uid, fid))


# ---- projects and snapshots ------------------------------------------------

def create_project(fid, name, host="", ext_key=None):
    pid = new_id("prj")
    db.run("insert into projects (id, firm_id, ext_key, name, host, created_at) values (?,?,?,?,?,?)",
           (pid, fid, ext_key, name.strip()[:120], host or "", now()))
    return pid


def project(fid, ref):
    """By id, or by the plugin's own project key, inside one firm only."""
    return db.one("select * from projects where firm_id=? and (id=? or ext_key=?)", (fid, ref, ref))


def project_count(fid):
    return db.val("select count(*) as n from projects where firm_id=? and archived_at is null", (fid,))


def projects(fid, archived=False):
    rows = db.all("select * from projects where firm_id=? and archived_at is " + ("not null" if archived else "null")
                  + " order by created_at", (fid,))
    for p in rows:
        snap = db.one("select taken_at from snapshots where project_id=? order by id desc limit 1", (p["id"],))
        p["snapshot_at"] = snap and snap["taken_at"]
        p["awaiting"] = db.val("select count(*) as n from changesets where project_id=? and status='proposed'", (p["id"],))
    return rows


def update_project(fid, pid, **fields):
    allowed = {k: v for k, v in fields.items() if k in ("name", "host", "archived_at", "last_plugin_poll_at")}
    if allowed:
        db.run(f"update projects set {', '.join(k + '=?' for k in allowed)} where firm_id=? and id=?", (*allowed.values(), fid, pid))


def save_snapshot(pid, host, elements):
    with db.tx():
        db.run("insert into snapshots (project_id, host, taken_at, elements) values (?,?,?,?)", (pid, host, now(), _j(elements)))
        db.run("delete from snapshots where project_id=? and id not in "
               "(select id from snapshots where project_id=? order by id desc limit 50)", (pid, pid))


def latest_snapshot(pid):
    r = db.one("select * from snapshots where project_id=? order by id desc limit 1", (pid,))
    return dict(r, elements=_l(r["elements"], [])) if r else None


# ---- rules -----------------------------------------------------------------

def _rule(r):
    return dict(_l(r["data"], {}), id=r["id"], status=r["status"], created_at=r["created_at"]) if r else None


def rules(fid, status=None):
    q = "select * from rules where firm_id=?" + (" and status=?" if status else "") + " order by created_at, id"
    return [_rule(r) for r in db.all(q, (fid, status) if status else (fid,))]


def get_rule(fid, rid):
    return _rule(db.one("select * from rules where firm_id=? and id=?", (fid, rid)))


def put_rule(fid, rule, status="active", by=None):
    rid = rule.get("id") or new_id("rule")
    data = {k: v for k, v in rule.items() if k not in ("id", "status", "created_at")}
    db.run("insert into rules (firm_id, id, data, status, created_by, created_at) values (?,?,?,?,?,?) "
           "on conflict(firm_id, id) do update set data=excluded.data, status=excluded.status",
           (fid, rid, _j(data), status, by, now()))
    return rid


def delete_rule(fid, rid):
    return db.run("delete from rules where firm_id=? and id=?", (fid, rid))


def overrides(pid):
    return {r["rule_id"]: {"value": r["value"], "enabled": bool(r["enabled"])}
            for r in db.all("select * from project_rule_overrides where project_id=?", (pid,))}


def set_override(pid, rid, value, enabled):
    db.run("insert into project_rule_overrides (project_id, rule_id, value, enabled) values (?,?,?,?) "
           "on conflict(project_id, rule_id) do update set value=excluded.value, enabled=excluded.enabled",
           (pid, rid, value, 1 if enabled else 0))


def clear_override(pid, rid):
    db.run("delete from project_rule_overrides where project_id=? and rule_id=?", (pid, rid))


# ---- change sets -----------------------------------------------------------

def _cs(r):
    return dict(r, ops=_l(r["ops"], [])) if r else None


def add_changeset(pid, title, reason, ops, source, by=None, rule=None, status="proposed", reverts=None):
    cid = new_id("cs")
    t = now()
    db.run("insert into changesets (id, project_id, title, reason, ops, status, source, rule_id, reverts, created_by, created_at, updated_at) "
           "values (?,?,?,?,?,?,?,?,?,?,?,?)", (cid, pid, title, reason, _j(ops), status, source, rule, reverts, by, t, t))
    return cid


def changeset(fid, cid):
    return _cs(db.one("select c.* from changesets c join projects p on p.id=c.project_id where p.firm_id=? and c.id=?", (fid, cid)))


_CS_LIST = ("select c.*, p.name as project_name, coalesce(u.name, c.created_by) as created_by_name, "
            "(select count(*) from comments k where k.changeset_id=c.id) as comment_count, "
            "(select count(*) from approvals a where a.changeset_id=c.id and a.decision='approve') as approval_count "
            "from changesets c join projects p on p.id=c.project_id left join users u on u.id=c.created_by ")


def changesets(fid, pid, status=None):
    q = _CS_LIST + "where p.firm_id=? and c.project_id=?" + (" and c.status=?" if status else "") + " order by c.created_at desc, c.id"
    return [_cs(r) for r in db.all(q, (fid, pid, status) if status else (fid, pid))]


def firm_changesets(fid, status):
    return [_cs(r) for r in db.all(_CS_LIST + "where p.firm_id=? and c.status=? and p.archived_at is null "
                                    "order by c.created_at desc", (fid, status))]


def set_changeset_status(cid, status, error=None):
    db.run("update changesets set status=?, error=?, updated_at=? where id=?", (status, error, now(), cid))


def add_approval(cid, uid, decision):
    db.run("insert into approvals (changeset_id, user_id, decision, at) values (?,?,?,?) "
           "on conflict(changeset_id, user_id) do update set decision=excluded.decision, at=excluded.at", (cid, uid, decision, now()))


def approvals(cid):
    return db.all("select a.*, u.name from approvals a left join users u on u.id=a.user_id where changeset_id=? order by at", (cid,))


def add_comment(cid, uid, body):
    kid = new_id("cmt")
    db.run("insert into comments (id, changeset_id, user_id, body, created_at) values (?,?,?,?,?)", (kid, cid, uid, body, now()))
    return kid


def comments(cid):
    return db.all("select k.id, k.body, k.created_at, k.user_id, coalesce(u.name, 'Deleted user') as name from comments k "
                  "left join users u on u.id=k.user_id where k.changeset_id=? order by k.created_at", (cid,))


# ---- chat and usage --------------------------------------------------------

def chat_messages(pid, uid):
    return _l(db.val("select messages from chat_threads where project_id=? and user_id=?", (pid, uid)), [])


def save_chat(pid, uid, messages):
    db.run("insert into chat_threads (project_id, user_id, messages, updated_at) values (?,?,?,?) "
           "on conflict(project_id, user_id) do update set messages=excluded.messages, updated_at=excluded.updated_at",
           (pid, uid, _j(messages), now()))


def month():
    return time.strftime("%Y-%m", time.gmtime())


def add_usage(fid, messages=0, input_tokens=0, output_tokens=0):
    db.run("insert into usage (firm_id, month, chat_messages, input_tokens, output_tokens) values (?,?,?,?,?) "
           "on conflict(firm_id, month) do update set chat_messages=usage.chat_messages+excluded.chat_messages, "
           "input_tokens=usage.input_tokens+excluded.input_tokens, output_tokens=usage.output_tokens+excluded.output_tokens",
           (fid, month(), messages, input_tokens, output_tokens))


def usage(fid):
    return db.one("select chat_messages, input_tokens, output_tokens, topup_messages from usage where firm_id=? and month=?",
                  (fid, month())) or {"chat_messages": 0, "input_tokens": 0, "output_tokens": 0, "topup_messages": 0}


def add_topup(fid, messages):
    """Extra assistant messages for the current month only (a top-up doesn't roll over)."""
    db.run("insert into usage (firm_id, month, topup_messages) values (?,?,?) "
           "on conflict(firm_id, month) do update set topup_messages=usage.topup_messages+excluded.topup_messages",
           (fid, month(), messages))


def dismissed_suggestions(fid):
    return {r["key"] for r in db.all("select key from rule_suggestions_dismissed where firm_id=?", (fid,))}


def dismiss_suggestion(fid, key):
    db.run("insert into rule_suggestions_dismissed (firm_id, key, at) values (?,?,?) on conflict(firm_id, key) do nothing",
           (fid, key, now()))


def chat_cap(firm):
    return plans.chat_cap(firm, seats_in_use(firm["id"]), usage(firm["id"])["topup_messages"])


# ---- audit -----------------------------------------------------------------

def audit(fid, project, actor, action, target="", detail=None, actor_name=None):
    db.run("insert into audit (firm_id, project_id, actor, actor_name, action, target, detail, at) values (?,?,?,?,?,?,?,?)",
           (fid, project, actor, actor_name, action, target or "", _j(detail or {}), now()))


def audit_log(fid, project=None, actor=None, action=None, since=None, until=None, cursor=None, limit=50):
    q, args = ("select a.*, p.name as project_name from audit a left join projects p on p.id=a.project_id "
               "where a.firm_id=?"), [fid]
    for cond, v in (("a.project_id=?", project), ("a.actor=?", actor), ("a.at>=?", since), ("a.at<?", until), ("a.id<?", cursor)):
        if v not in (None, ""):
            q += " and " + cond
            args.append(v)
    if action:
        q += " and a.action like ?"
        args.append(action.rstrip("*") + "%")
    q += " order by a.id desc"
    if limit:
        q += " limit ?"
        args.append(limit)
    return [dict(r, detail=_l(r["detail"], {})) for r in db.all(q, args)]


# ---- waitlist and billing --------------------------------------------------

def add_waitlist(email, data):
    """Returns False if the email was already on the list."""
    if db.one("select id from waitlist where email=?", (email,)):
        return False
    db.run("insert into waitlist (email, data, at) values (?,?,?)", (email, _j(data), now()))
    return True


def waitlist():
    return [dict(r, data=_l(r["data"], {})) for r in db.all("select * from waitlist order by id desc")]


def billing_event_seen(eid):
    """Records a webhook event id; True if it was already processed."""
    if db.one("select id from billing_events where id=?", (eid,)):
        return True
    db.run("insert into billing_events (id, at) values (?,?)", (eid, now()))
    return False
