r"""Change-set lifecycle shared by the HTTP API and the agent.

proposed --approve--> approved --host applies--> applied --revert--> reverted
    \--reject--> rejected               \--host refuses--> failed

Only a person with the Approver role or higher can approve. The agent can only call `propose`.
With the firm's two-approval mode on, a change set is approved after two different approvers.
"""
from . import checker, plans, store
from .errors import ApiError, conflict, not_found

# Properties a change set may touch, per element type. Geometry-driven values
# (room area, corridor width) are flagged with advice instead of edited.
EDITABLE = {
    "door": {"clear_width_mm", "name"},
    "stair": {"riser_mm", "tread_mm", "risers", "width_mm"},
    "room": {"name", "use"},
}


class ChangeError(ApiError):
    def __init__(self, message):
        super().__init__(409, "conflict", message)


def elements(pid):
    snap = store.latest_snapshot(pid)
    return snap["elements"] if snap else []


def rules_for(fid, pid):
    """Active firm rules with this project's overrides applied."""
    ov = store.overrides(pid)
    out = []
    for r in store.rules(fid, "active"):
        o = ov.get(r["id"])
        if o and not o["enabled"]:
            continue
        if o and o["value"] is not None:
            r = dict(r, value=o["value"], overridden=True)
        out.append(r)
    return out


def issues(fid, pid):
    """Rule issues, each tagged with the open change set (proposed or approved) that touches its element."""
    open_cs = store.changesets(fid, pid, "proposed") + store.changesets(fid, pid, "approved")
    out = checker.check(elements(pid), rules_for(fid, pid))
    for i in out:
        i["pending"] = next((c["id"] for c in open_cs
                             if any(o["element"] == i["element"] and o["prop"] in (i["prop"], "risers") for o in c["ops"])), None)
    return out


def propose(c, pid, title, reason, ops, source, rule=None):
    els = {e["id"]: e for e in elements(pid)}
    if not ops:
        raise ChangeError("A change set needs at least one edit.")
    full = []
    for o in ops:
        el = els.get(o.get("element"))
        if not el:
            raise ChangeError(f"Unknown element {o.get('element')!r}.")
        if o.get("prop") not in EDITABLE.get(el["type"], set()):
            raise ChangeError(f"{el['type']}.{o.get('prop')} is not editable; editable: "
                              f"{sorted(EDITABLE.get(el['type'], []))}")
        full.append(checker.op(el, o["prop"], o["to"]))
    with store.db.tx():
        cid = store.add_changeset(pid, title[:200], (reason or "")[:2000], full, source, by=c.uid, rule=rule)
        if source == "agent":
            store.audit(c.fid, pid, "agent", "changeset.proposed", cid, {"title": title, "reason": reason, "ops": full,
                                                                          "asked_by": c.uid}, actor_name="the assistant")
        else:
            c.audit(pid, "changeset.proposed", cid, {"title": title, "reason": reason, "ops": full})
    return cid


def fix_issue(c, pid, issue_id):
    issue = next((i for i in issues(c.fid, pid) if i["id"] == issue_id), None)
    if not issue:
        raise ChangeError("This issue is no longer present. Re-run checks.")
    if issue["pending"]:
        raise ChangeError("A fix for this issue is already waiting for approval.")
    ops = checker.fix_ops(issue, elements(pid))
    if not ops:
        raise ChangeError("This issue needs a design decision; Lintel won't guess a geometry change.")
    return propose(c, pid, f"Fix: {issue['rule_name']} at {issue['element_name']}",
                   f"{issue['message']} Ref: {issue['ref']}", ops, "rule", rule=issue["rule"])


def _get(c, cid):
    cs = store.changeset(c.fid, cid)
    if not cs:
        raise not_found("No such change set.")
    return cs


def needed_approvals(firm):
    return 2 if firm["two_approvals"] and plans.limits(firm)["two_approvals"] else 1


def decide(c, cid, decision):
    cs = _get(c, cid)
    if cs["status"] != "proposed":
        raise ChangeError(f"This change set is {cs['status']}, not waiting for approval.")
    if decision == "approve":
        plans.require(c.firm, "apply")
    needed = needed_approvals(c.firm)
    with store.db.tx():
        store.add_approval(cid, c.uid, decision)
        if decision == "reject":
            store.set_changeset_status(cid, "rejected")
            c.audit(cs["project_id"], "changeset.rejected", cid, {"title": cs["title"]})
            return {"status": "rejected"}
        got = sum(1 for a in store.approvals(cid) if a["decision"] == "approve")
        if got < needed:
            c.audit(cs["project_id"], "changeset.approval_recorded", cid, {"title": cs["title"], "approvals": got, "needed": needed})
            return {"status": "proposed", "approvals": got, "needed": needed}
        store.set_changeset_status(cid, "approved")
        c.audit(cs["project_id"], "changeset.approved", cid, {"title": cs["title"]})
    _auto_apply(c.fid, cs["project_id"], cid)
    return {"status": store.changeset(c.fid, cid)["status"], "approvals": got, "needed": needed}


def undo_reject(c, cid):
    """The 6-second Undo on a reject toast: back to proposed, if nothing else happened."""
    cs = _get(c, cid)
    if cs["status"] != "rejected":
        raise ChangeError("Only a rejected change set can be restored.")
    with store.db.tx():
        store.db.run("delete from approvals where changeset_id=?", (cid,))
        store.set_changeset_status(cid, "proposed")
        c.audit(cs["project_id"], "changeset.reject_undone", cid, {"title": cs["title"]})
    return {"status": "proposed"}


def revert(c, cid):
    cs = _get(c, cid)
    if cs["status"] != "applied":
        raise ChangeError("Only applied change sets can be reverted.")
    plans.require(c.firm, "apply")
    ops = [dict(o, **{"from": o["to"], "to": o["from"]}) for o in reversed(cs["ops"])]
    # The approver asked for the revert, so the inverse goes straight to the host as approved.
    with store.db.tx():
        rid = store.add_changeset(cs["project_id"], f"Revert: {cs['title']}", f"Revert of {cid} requested by {c.name}",
                                  ops, "revert", by=c.uid, status="approved", reverts=cid)
        c.audit(cs["project_id"], "changeset.revert_requested", rid, {"reverts": cid, "title": cs["title"]})
    _auto_apply(c.fid, cs["project_id"], rid)
    return rid


def _auto_apply(fid, pid, cid):
    """The sample project (and the hosted demo) has no CAD app attached, so the built-in sample host applies at once."""
    from . import demo
    p = store.project(fid, pid)
    if demo.enabled() or (p and p["host"] == demo.SAMPLE_HOST):
        demo.apply_now(fid, cid)


def host_result(fid, cid, ok, error, host_name, actor_name=None):
    cs = store.changeset(fid, cid)
    if not cs:
        raise not_found("No such change set.")
    if cs["status"] != "approved":
        raise conflict("This change set is not waiting for the host.")
    with store.db.tx():
        store.set_changeset_status(cid, "applied" if ok else "failed", None if ok else (error or "The host refused the change."))
        store.audit(fid, cs["project_id"], f"host:{host_name}", "changeset.applied" if ok else "changeset.failed", cid,
                    {"error": error} if error else {"title": cs["title"]}, actor_name=actor_name or f"host:{host_name}")
        if ok and cs["reverts"]:
            store.set_changeset_status(cs["reverts"], "reverted")
