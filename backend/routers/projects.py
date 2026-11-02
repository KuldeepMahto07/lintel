"""Projects, issues and fixes, change sets (approve/reject/revert, comments), rule overrides, and chat."""
import json
import os
import time

from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse

from .. import agent, auth, checker, demo, plans, service, store
from ..auth import Ctx
from ..errors import ApiError, invalid, not_found
from . import text

router = APIRouter(prefix="/api")


def _project(c, ref):
    p = store.project(c.fid, ref)
    if not p:
        raise not_found("No such project.")
    return p


@router.get("/projects")
def list_projects(archived: int = 0, c: Ctx = Depends(auth.current)):
    out = store.projects(c.fid, bool(archived))
    for p in out:
        found = service.issues(c.fid, p["id"]) if p["snapshot_at"] else []
        p["issues"] = len(found)
        # room outlines for the card thumbnail, and which of them carry an issue
        rooms = [e for e in service.elements(p["id"]) if e["type"] == "room" and (e.get("geom") or {}).get("outline")][:60]
        flagged = {i["element"] for i in found}
        p["thumb"] = {"rooms": [r["geom"]["outline"] for r in rooms],
                      "flagged": [n for n, r in enumerate(rooms) if r["id"] in flagged]}
    return out


@router.post("/projects", status_code=201)
def create_project(body: dict = Body(...), c: Ctx = Depends(auth.need("member"))):
    name = text(body, "name", "Project name", max_len=120)
    plans.check_count(c.firm, "projects", store.project_count(c.fid))
    with store.db.tx():
        pid = store.create_project(c.fid, name, "manual")
        c.audit(pid, "project.created", pid, {"name": name})
    return {"project": store.project(c.fid, pid)}


@router.post("/projects/sample", status_code=201)
def create_sample(c: Ctx = Depends(auth.need("member"))):
    plans.check_count(c.firm, "projects", store.project_count(c.fid))
    return {"project": store.project(c.fid, demo.create_sample(c))}


@router.get("/projects/{ref}")
def get_project(ref: str, c: Ctx = Depends(auth.current)):
    p = _project(c, ref)
    snap = store.latest_snapshot(p["id"])
    els = snap["elements"] if snap else []
    return {"project": p, "snapshot_at": snap and snap["taken_at"], "host": snap and snap["host"],
            "elements": els, "issues": service.issues(c.fid, p["id"]), "egress": checker.egress_distances(els),
            "changesets": store.changesets(c.fid, p["id"]), "plugin_seen_at": p["last_plugin_poll_at"],
            "rules": service.rules_for(c.fid, p["id"]), "overrides": store.overrides(p["id"]),
            "needed_approvals": service.needed_approvals(c.firm)}


@router.patch("/projects/{ref}")
def patch_project(ref: str, body: dict = Body(...), c: Ctx = Depends(auth.need("admin"))):
    p = _project(c, ref)
    changes = {}
    if "name" in body:
        changes["name"] = text(body, "name", "Project name", max_len=120)
    if "archived" in body:
        if not body["archived"] and p["archived_at"]:
            plans.check_count(c.firm, "projects", store.project_count(c.fid))
        changes["archived_at"] = time.time() if body["archived"] else None
    with store.db.tx():
        store.update_project(c.fid, p["id"], **changes)
        action = "project.archived" if changes.get("archived_at") else (
            "project.restored" if "archived_at" in changes else "project.renamed")
        c.audit(p["id"], action, p["id"], {k: v for k, v in changes.items() if k == "name"})
    return {"project": store.project(c.fid, p["id"])}


@router.post("/projects/{ref}/issues/{iid}/fix", status_code=201)
def fix(ref: str, iid: str, c: Ctx = Depends(auth.need("member"))):
    p = _project(c, ref)
    cid = service.fix_issue(c, p["id"], iid)
    return {"changeset": cid}


@router.put("/projects/{ref}/rules/{rid}")
def set_override(ref: str, rid: str, body: dict = Body(...), c: Ctx = Depends(auth.need("admin"))):
    p = _project(c, ref)
    if not store.get_rule(c.fid, rid):
        raise not_found("No such rule.")
    plans.require(c.firm, "overrides")
    value = body.get("value")
    if value not in (None, ""):
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise invalid("Enter a number.", value="Enter a number.")
    else:
        value = None
    enabled = bool(body.get("enabled", True))
    with store.db.tx():
        store.set_override(p["id"], rid, value, enabled)
        c.audit(p["id"], "rule.override_set", rid, {"value": value, "enabled": enabled})
    return {"overrides": store.overrides(p["id"])}


@router.delete("/projects/{ref}/rules/{rid}")
def clear_override(ref: str, rid: str, c: Ctx = Depends(auth.need("admin"))):
    p = _project(c, ref)
    with store.db.tx():
        store.clear_override(p["id"], rid)
        c.audit(p["id"], "rule.override_cleared", rid)
    return {"overrides": store.overrides(p["id"])}


# ---- change sets -----------------------------------------------------------

@router.get("/approvals")
def approvals(c: Ctx = Depends(auth.current)):
    out = store.firm_changesets(c.fid, "proposed")
    for cs in out:
        cs["approvals"] = store.approvals(cs["id"])
    return {"changesets": out, "needed_approvals": service.needed_approvals(c.firm)}


@router.get("/changesets/{cid}")
def get_changeset(cid: str, c: Ctx = Depends(auth.current)):
    cs = store.changeset(c.fid, cid)
    if not cs:
        raise not_found("No such change set.")
    return dict(cs, approvals=store.approvals(cid), comments=store.comments(cid))


@router.post("/changesets/{cid}/approve")
def approve(cid: str, c: Ctx = Depends(auth.need("approver"))):
    return service.decide(c, cid, "approve")


@router.post("/changesets/{cid}/reject")
def reject(cid: str, c: Ctx = Depends(auth.need("approver"))):
    return service.decide(c, cid, "reject")


@router.post("/changesets/{cid}/undo-reject")
def undo_reject(cid: str, c: Ctx = Depends(auth.need("approver"))):
    return service.undo_reject(c, cid)


@router.post("/changesets/{cid}/revert")
def revert(cid: str, c: Ctx = Depends(auth.need("approver"))):
    return {"changeset": service.revert(c, cid)}


@router.get("/changesets/{cid}/comments")
def list_comments(cid: str, c: Ctx = Depends(auth.current)):
    if not store.changeset(c.fid, cid):
        raise not_found("No such change set.")
    return store.comments(cid)


@router.post("/changesets/{cid}/comments", status_code=201)
def add_comment(cid: str, body: dict = Body(...), c: Ctx = Depends(auth.need("member"))):
    cs = store.changeset(c.fid, cid)
    if not cs:
        raise not_found("No such change set.")
    note = text(body, "body", "Comment", max_len=4000)
    with store.db.tx():
        kid = store.add_comment(cid, c.uid, note)
        c.audit(cs["project_id"], "changeset.commented", cid, {"comment": kid})
    return {"id": kid, "comments": store.comments(cid)}


# ---- chat ------------------------------------------------------------------

@router.get("/projects/{ref}/chat")
def get_chat(ref: str, c: Ctx = Depends(auth.current)):
    p = _project(c, ref)
    out = agent.transcript(p["id"], c.uid)
    for m in out:
        if m["role"] == "changeset":
            m["changeset"] = store.changeset(c.fid, m["id"])
        elif m["role"] == "rule":
            m["rule"] = store.get_rule(c.fid, m["id"])
    return {"messages": [m for m in out if m.get("text") or m.get("changeset") or m.get("rule")],
            "configured": bool(os.environ.get("ANTHROPIC_API_KEY")) and c.firm["chat_enabled"],
            "chat_enabled": c.firm["chat_enabled"]}


def chat_guard(c):
    if not c.firm["chat_enabled"]:
        raise ApiError(403, "chat_disabled", "Chat is switched off for this firm in Settings.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ApiError(503, "chat_unavailable", "Chat isn't set up: add ANTHROPIC_API_KEY to the server and restart.")
    used = store.usage(c.fid)["chat_messages"]
    if used >= plans.chat_cap(c.firm, store.seats_in_use(c.fid)):
        raise ApiError(402, "plan_limit", plans._MESSAGES["chat"], limit="chat", plan=plans.effective(c.firm))


@router.post("/projects/{ref}/chat")
def post_chat(ref: str, body: dict = Body(...), c: Ctx = Depends(auth.need("member"))):
    p = _project(c, ref)
    message = text(body, "message", "Message", max_len=4000)
    chat_guard(c)
    auth.rate_limit(f"chat:{c.uid}", 20, 60)

    def stream():
        try:
            for ev in agent.chat_events(c, p["id"], message):
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except agent.anthropic.AuthenticationError:
            yield _err("The assistant isn't configured: the server's ANTHROPIC_API_KEY was rejected.")
        except agent.anthropic.APIStatusError as e:
            yield _err(f"The assistant is unavailable (API error {e.status_code}). Checks and approvals still work.")
        except agent.anthropic.APIConnectionError:
            yield _err("Couldn't reach the assistant. Checks and approvals still work.")

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


def _err(message):
    return f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"
