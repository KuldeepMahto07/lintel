"""Host plugin API (Bearer personal token), the audit log, the waitlist and health."""
import csv
import io
import os
import re
import secrets
import time

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import Response

from .. import auth, db, learn, plans, service, store
from ..auth import Ctx
from ..errors import forbidden, invalid, not_found
from . import text

router = APIRouter(prefix="/api")
VERSION = "0.2.0"


# ---- plugin ----------------------------------------------------------------

def _plugin_project(c, ref):
    p = store.project(c.fid, ref)
    if not p:
        raise not_found("No such project in this firm.")
    return p


@router.post("/plugin/snapshot")
def plugin_snapshot(body: dict = Body(...), c: Ctx = Depends(auth.plugin)):
    if not c.can("member"):
        raise forbidden("Viewers can't sync models.")
    ref = text(body, "project", "Project", max_len=120)
    host = re.sub(r"[^a-z0-9_.-]", "", str(body.get("host", "unknown")).lower())[:32] or "unknown"
    elements = body.get("elements")
    if not isinstance(elements, list) or len(elements) > 20000:
        raise invalid("elements must be a list (at most 20 000).")
    for e in elements:
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or e.get("type") not in ("room", "door", "stair", "wall"):
            raise invalid("Each element needs an id and a type of room, door, stair or wall.")
        e.setdefault("props", {})
        e.setdefault("geom", {})
    c.host = host
    p = store.project(c.fid, ref)
    with store.db.tx():
        if not p:
            plans.check_count(c.firm, "projects", store.project_count(c.fid))
            pid = store.create_project(c.fid, str(body.get("name") or ref), host, ext_key=ref)
            c.audit(pid, "project.created", pid, {"name": body.get("name") or ref, "host": host})
            p = store.project(c.fid, pid)
        elif p["host"] != host:
            store.update_project(c.fid, p["id"], host=host)
        store.save_snapshot(p["id"], host, elements)
        c.audit(p["id"], "model.snapshot", "", {"elements": len(elements)})
    found = service.issues(c.fid, p["id"])
    learn.after_sync(c.fid)
    # Hosts compare these ids between syncs to speak up only about issues that are new.
    return {"project": p["id"], "issues": len(found),
            "items": [{"id": i["id"], "message": i["message"], "element_name": i["element_name"], "severity": i["severity"],
                       "ref": i["ref"]} for i in found[:50]]}


@router.get("/plugin/pending")
def plugin_pending(project: str, c: Ctx = Depends(auth.plugin)):
    p = _plugin_project(c, project)
    store.update_project(c.fid, p["id"], last_plugin_poll_at=time.time())
    return store.changesets(c.fid, p["id"], "approved")


@router.post("/plugin/result")
def plugin_result(body: dict = Body(...), c: Ctx = Depends(auth.plugin)):
    host = re.sub(r"[^a-z0-9_.-]", "", str(body.get("host", "plugin")).lower())[:32] or "plugin"
    service.host_result(c.fid, str(body.get("changeset", "")), bool(body.get("ok")), body.get("error"), host,
                        actor_name=f"{c.user['name']} via {host}")
    return Response(status_code=204)


# ---- audit -----------------------------------------------------------------

def _audit_rows(c, project, actor, action, since, until, cursor, limit):
    pid = None
    if project:
        p = store.project(c.fid, project)
        if not p:
            raise not_found("No such project.")
        pid = p["id"]
    return store.audit_log(c.fid, project=pid, actor=actor, action=action, since=since, until=until, cursor=cursor, limit=limit)


@router.get("/audit")
def audit(project: str = "", actor: str = "", action: str = "", since: float | None = None, until: float | None = None,
          cursor: int | None = None, c: Ctx = Depends(auth.current)):
    rows = _audit_rows(c, project, actor, action, since, until, cursor, 50)
    return {"entries": rows, "next": rows[-1]["id"] if len(rows) == 50 else None}


@router.get("/audit.csv")
def audit_csv(project: str = "", actor: str = "", action: str = "", since: float | None = None, until: float | None = None,
              c: Ctx = Depends(auth.need("admin"))):
    plans.require(c.firm, "audit_csv")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["when_utc", "project", "who", "action", "target", "detail"])
    for r in _audit_rows(c, project, actor, action, since, until, None, 0):
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(r["at"])), r.get("project_name") or "",
                    r.get("actor_name") or r["actor"], r["action"], r["target"], _flat(r["detail"])])
    c.audit(None, "audit.exported", "")
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=lintel-audit.csv"})


def _flat(d):
    s = "; ".join(f"{k}={v}" for k, v in d.items())
    return ("'" + s) if s[:1] in ("=", "+", "-", "@") else s  # keep spreadsheets from evaluating it


# ---- waitlist and health ---------------------------------------------------

@router.post("/waitlist")
def join_waitlist(request: Request, body: dict = Body(...)):
    auth.rate_limit(f"waitlist:{request.client.host if request.client else '?'}", 10, 3600)
    mail = str(body.get("email", "")).strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", mail) or len(mail) > 200:
        raise invalid("Please enter a valid email address.", email="Enter a valid email address.")
    data = {k: str(body.get(k, ""))[:1000] for k in ("name", "firm", "firm_size", "host", "message")}
    new = store.add_waitlist(mail, data)
    if new:
        store.audit(None, None, "site", "waitlist.joined", mail, {"host": data["host"], "firm_size": data["firm_size"]})
    return {"ok": True, "new": new}


@router.get("/waitlist")
def list_waitlist(request: Request):
    """Staff only: needs the LINTEL_STAFF_TOKEN header."""
    staff = os.environ.get("LINTEL_STAFF_TOKEN", "")
    if not staff or not secrets.compare_digest(request.headers.get("x-staff-token", ""), staff):
        raise forbidden()
    return store.waitlist()


@router.get("/health")
def health():
    state = db.health()
    return {"ok": state == "ok", "db": state, "version": VERSION}
