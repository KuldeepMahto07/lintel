"""Lintel backend: dashboard API, plugin API, static web UI. Run: uvicorn backend.app:app --port 8002"""
import csv
import io
import json
import re
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import agent, checker, service, store

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


def plugin_token():
    """Shared secret for host plugins; written next to the database so a local plugin can read it."""
    if os.environ.get("LINTEL_TOKEN"):
        return os.environ["LINTEL_TOKEN"]
    path = store.DB_PATH.parent / "plugin-token.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(24))
    return path.read_text().strip()


def seed():
    if not store.rules():
        for r in json.loads((Path(__file__).parent / "starter_rules.json").read_text(encoding="utf-8")):
            store.put_rule(r)
        store.audit(None, "system", "rules.seeded", "", {"count": len(store.rules())})
    plugin_token()


@asynccontextmanager
async def lifespan(_):
    seed()
    yield


app = FastAPI(title="Lintel", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")
SITE = ROOT / "site" / "public"
if SITE.exists():  # marketing site, built by site/build.py
    app.mount("/site", StaticFiles(directory=SITE, html=True), name="site")


@app.exception_handler(service.ChangeError)
def change_error(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=409)


def _project(pid):
    if not store.project(pid):
        raise HTTPException(404, "no such project")


# ---- dashboard -------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/projects")
def list_projects():
    return store.projects()


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    _project(pid)
    snap = store.latest_snapshot(pid)
    els = snap["elements"] if snap else []
    return {"project": store.project(pid), "snapshot_at": snap and snap["taken"], "host": snap and snap["host"],
            "elements": els, "issues": service.issues(pid), "egress": checker.egress_distances(els),
            "changesets": store.changesets(pid)}


@app.post("/api/projects/{pid}/issues/{iid}/fix")
def fix(pid: str, iid: str, body: dict = Body(default={})):
    _project(pid)
    return {"changeset": service.fix_issue(pid, iid, body.get("actor", "user"))}


@app.post("/api/changesets/{cid}/{action}")
def changeset_action(cid: str, action: str, body: dict = Body(default={})):
    actor = body.get("actor", "user")
    if action in ("approve", "reject"):
        return {"status": service.decide(cid, action, actor)}
    if action == "revert":
        return {"changeset": service.revert(cid, actor)}
    raise HTTPException(404)


@app.get("/api/projects/{pid}/chat")
def get_chat(pid: str):
    _project(pid)
    return agent.transcript(pid)


@app.post("/api/projects/{pid}/chat")
def post_chat(pid: str, body: dict = Body(...)):
    _project(pid)
    try:
        return agent.chat(pid, body["message"])
    except agent.anthropic.AuthenticationError:
        raise HTTPException(503, "Claude isn't configured: set ANTHROPIC_API_KEY and restart Lintel.")
    except agent.anthropic.APIStatusError as e:
        raise HTTPException(502, f"Claude API error {e.status_code}: {e.message}")
    except agent.anthropic.APIConnectionError:
        raise HTTPException(502, "Couldn't reach the Claude API.")


@app.get("/api/audit")
def get_audit(project: str | None = None):
    return store.audit_log(project)


# ---- waitlist (marketing site form) ----------------------------------------

@app.post("/api/waitlist")
def join_waitlist(body: dict = Body(...)):
    email = str(body.get("email", "")).strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 200:
        raise HTTPException(422, "Please enter a valid email address.")
    fields = ("name", "firm", "firm_size", "host", "message")
    data = {k: str(body.get(k, ""))[:1000] for k in fields}
    new = store.add_waitlist(email, data)
    if new:
        store.audit(None, "site", "waitlist.joined", email, {"host": data["host"], "firm_size": data["firm_size"]})
    return {"ok": True, "new": new}


@app.get("/api/waitlist")
def list_waitlist():
    return store.waitlist()


# ---- rules -----------------------------------------------------------------

RULE_FIELDS = ["id", "name", "kind", "applies_to", "where", "prop", "value", "unit", "severity", "fixable", "ref", "source"]


def _clean_rule(r):
    if r.get("kind") not in ("min", "max", "egress"):
        raise HTTPException(422, "kind must be min, max or egress")
    if r.get("applies_to") not in ("room", "door", "stair"):
        raise HTTPException(422, "applies_to must be room, door or stair")
    if r["kind"] != "egress" and not r.get("prop"):
        raise HTTPException(422, "prop is required")
    try:
        r["value"] = float(r["value"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "value must be a number")
    if isinstance(r.get("where"), str):
        r["where"] = dict(kv.split("=", 1) for kv in r["where"].split(";") if "=" in kv)
    if isinstance(r.get("fixable"), str):
        r["fixable"] = r["fixable"].strip().lower() in ("1", "true", "yes")
    return {k: r[k] for k in RULE_FIELDS if r.get(k) not in (None, "")}


@app.get("/api/rules")
def list_rules():
    return store.rules()


@app.post("/api/rules")
def save_rule(body: dict = Body(...)):
    rule = _clean_rule(body)
    rule.setdefault("source", "firm")
    status = body.get("status", "active")
    rid = store.put_rule(rule, status)
    store.audit(None, body.get("actor", "user"), "rule.saved", rid, rule)
    return {"id": rid}


@app.post("/api/rules/{rid}/status")
def rule_status(rid: str, body: dict = Body(...)):
    rule = store.get_rule(rid)
    if not rule or body.get("status") not in ("active", "disabled"):
        raise HTTPException(404 if not rule else 422)
    store.put_rule(rule, body["status"])
    store.audit(None, body.get("actor", "user"), f"rule.{body['status']}", rid, {"name": rule["name"]})
    return {"ok": True}


@app.delete("/api/rules/{rid}")
def remove_rule(rid: str, actor: str = "user"):
    store.delete_rule(rid)
    store.audit(None, actor, "rule.deleted", rid)
    return {"ok": True}


@app.post("/api/rules/import")
async def import_rules(request: Request):
    """Accepts a JSON list of rules, or CSV with a header row using the rule field names."""
    text = (await request.body()).decode("utf-8-sig").strip()
    rows = json.loads(text) if text.startswith("[") else list(csv.DictReader(io.StringIO(text)))
    ids = [store.put_rule(_clean_rule(dict(r, source=r.get("source") or "firm"))) for r in rows]
    store.audit(None, request.headers.get("x-actor", "user"), "rules.imported", "", {"count": len(ids)})
    return {"imported": len(ids), "ids": ids}


@app.get("/api/rules/export")
def export_rules():
    return JSONResponse(store.rules(), headers={"Content-Disposition": "attachment; filename=lintel-rules.json"})


# ---- host plugin API -------------------------------------------------------

def _auth(token):
    if not token or not secrets.compare_digest(token, plugin_token()):
        raise HTTPException(401, "bad plugin token")


@app.post("/api/plugin/snapshot")
def plugin_snapshot(body: dict = Body(...), x_lintel_token: str | None = Header(None)):
    _auth(x_lintel_token)
    pid, host = body["project"], body.get("host", "unknown")
    store.ensure_project(pid, body.get("name"), host)
    store.save_snapshot(pid, host, body["elements"])
    store.audit(pid, f"host:{host}", "model.snapshot", "", {"elements": len(body["elements"])})
    return {"issues": len(service.issues(pid))}


@app.get("/api/plugin/pending")
def plugin_pending(project: str, x_lintel_token: str | None = Header(None)):
    _auth(x_lintel_token)
    return store.changesets(project, "approved")


@app.post("/api/plugin/result")
def plugin_result(body: dict = Body(...), x_lintel_token: str | None = Header(None)):
    _auth(x_lintel_token)
    service.host_result(body["changeset"], body["ok"], body.get("error"), body.get("host", "unknown"))
    return {"ok": True}
