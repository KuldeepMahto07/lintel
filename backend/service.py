r"""Change-set lifecycle shared by the HTTP API and the agent.

proposed --approve--> approved --host applies--> applied --revert--> reverted
    \--reject--> rejected               \--host refuses--> failed

Only a person (dashboard or host panel) can approve. The agent can only call `propose`.
"""
from . import checker, store

# Properties a change set may touch, per element type. Geometry-driven values
# (room area, corridor width) are flagged with advice instead of edited.
EDITABLE = {
    "door": {"clear_width_mm", "name"},
    "stair": {"riser_mm", "tread_mm", "risers", "width_mm"},
    "room": {"name", "use"},
}


class ChangeError(ValueError):
    pass


def elements(pid):
    snap = store.latest_snapshot(pid)
    return snap["elements"] if snap else []


def issues(pid):
    """Rule issues, each tagged with the open change set (proposed or approved) that touches its element."""
    open_cs = store.changesets(pid, "proposed") + store.changesets(pid, "approved")
    out = checker.check(elements(pid), store.rules("active"))
    for i in out:
        i["pending"] = next((c["id"] for c in open_cs
                             if any(o["element"] == i["element"] and o["prop"] in (i["prop"], "risers") for o in c["ops"])), None)
    return out


def propose(pid, title, reason, ops, source, actor, rule=None):
    els = {e["id"]: e for e in elements(pid)}
    if not ops:
        raise ChangeError("a change set needs at least one op")
    full = []
    for o in ops:
        el = els.get(o.get("element"))
        if not el:
            raise ChangeError(f"unknown element {o.get('element')!r}")
        if o.get("prop") not in EDITABLE.get(el["type"], set()):
            raise ChangeError(f"{el['type']}.{o.get('prop')} is not editable; editable: "
                              f"{sorted(EDITABLE.get(el['type'], []))}")
        full.append(checker.op(el, o["prop"], o["to"]))
    cid = store.add_changeset(pid, title, reason, full, source, rule)
    store.audit(pid, actor, "changeset.proposed", cid, {"title": title, "reason": reason, "ops": full})
    return cid


def fix_issue(pid, issue_id, actor):
    issue = next((i for i in issues(pid) if i["id"] == issue_id), None)
    if not issue:
        raise ChangeError("issue no longer present")
    if issue["pending"]:
        raise ChangeError(f"a fix for this is already open ({issue['pending']})")
    ops = checker.fix_ops(issue, elements(pid))
    if not ops:
        raise ChangeError("this issue needs a design decision; Lintel won't guess a geometry change")
    return propose(pid, f"Fix: {issue['rule_name']} at {issue['element_name']}",
                   f"{issue['message']} Ref: {issue['ref']}", ops, "rule", actor, rule=issue["rule"])


def decide(cid, decision, actor):
    cs = store.changeset(cid)
    if not cs:
        raise ChangeError("no such change set")
    if cs["status"] != "proposed":
        raise ChangeError(f"change set is {cs['status']}, not proposed")
    status = {"approve": "approved", "reject": "rejected"}[decision]
    store.set_changeset_status(cid, status)
    store.audit(cs["project"], actor, f"changeset.{status}", cid, {"title": cs["title"]})
    return status


def revert(cid, actor):
    cs = store.changeset(cid)
    if not cs or cs["status"] != "applied":
        raise ChangeError("only applied change sets can be reverted")
    ops = [dict(o, **{"from": o["to"], "to": o["from"]}) for o in reversed(cs["ops"])]
    # The user asked for the revert, so it goes straight to the host as approved.
    rid = store.add_changeset(cs["project"], f"Revert: {cs['title']}", f"Revert of {cid} requested by {actor}",
                              ops, "revert", status="approved", reverts=cid)
    store.audit(cs["project"], actor, "changeset.revert_requested", rid, {"reverts": cid})
    return rid


def host_result(cid, ok, error, host_name):
    cs = store.changeset(cid)
    if not cs or cs["status"] != "approved":
        raise ChangeError("change set is not waiting for the host")
    store.set_changeset_status(cid, "applied" if ok else "failed", error)
    store.audit(cs["project"], f"host:{host_name}", "changeset.applied" if ok else "changeset.failed", cid,
                {"error": error} if error else {})
    if ok and cs["reverts"]:
        store.set_changeset_status(cs["reverts"], "reverted")
