r"""Change-set lifecycle shared by the HTTP API and the agent.

proposed --approve--> approved --host applies--> applied --revert--> reverted
    \--reject--> rejected               \--host refuses--> failed

Only a person with the Approver role or higher can approve. The agent can only call `propose`.
With the firm's two-approval mode on, a change set is approved after two different approvers.
"""
import json
from pathlib import Path

from . import checker, geometry, plans, store
from .errors import ApiError, conflict, not_found

# Properties a change set may touch, per element type. Room areas and corridor widths follow from
# the walls: a wall's offset_mm moves it at right angles (see geometry.py) and the rooms follow.
EDITABLE = {
    "door": {"clear_width_mm", "name"},
    "stair": {"riser_mm", "tread_mm", "risers", "width_mm"},
    "room": {"name", "use"},
    "wall": {"offset_mm"},
}
AREA = "area_m2"
STARTER = Path(__file__).resolve().parent / "starter_rules.json"
_topped_up = set()


def add_new_starter_rules(fid):
    """Firms made before a starter rule existed get it once (never overwriting their own edits)."""
    if fid in _topped_up:
        return
    have = {r["id"] for r in store.rules(fid)}
    dismissed = store.dismissed_suggestions(fid)
    for r in json.loads(STARTER.read_text(encoding="utf-8")):
        if r["id"] not in have and "starter:" + r["id"] not in dismissed:
            store.put_rule(fid, r)
    _topped_up.add(fid)


class ChangeError(ApiError):
    def __init__(self, message):
        super().__init__(409, "conflict", message)


def elements(pid):
    snap = store.latest_snapshot(pid)
    return snap["elements"] if snap else []


def elements_with_loads(fid, pid):
    """The model as people read it: rooms carry occupant_load from the firm's load factors."""
    return checker.with_loads(elements(pid), rules_for(fid, pid))


def rules_for(fid, pid):
    """Active firm rules with this project's overrides applied. On a plan without custom rules
    (Free) only the starter rules run and overrides are ignored; both come back on upgrade."""
    add_new_starter_rules(fid)
    lim = plans.limits(store.firm(fid) or {})
    ov = store.overrides(pid) if lim["overrides"] else {}
    out = []
    for r in store.rules(fid, "active"):
        if not lim["custom_rules"] and (r.get("source") or "firm") != "starter":
            continue
        o = ov.get(r["id"])
        if o and not o["enabled"]:
            continue
        if o and o["value"] is not None:
            r = dict(r, value=o["value"], overridden=True)
        out.append(r)
    return out


def require_writable(firm, pid):
    """Projects beyond the plan's project limit stay readable but can't change (Free keeps the oldest one).
    Archiving a project frees its place for the next one."""
    cap = plans.limits(firm)["projects"]
    if cap is None:
        return
    keep = [p["id"] for p in store.projects(firm["id"])[:cap]]
    if pid not in keep:
        raise ApiError(402, "plan_limit", "This project is read-only on the Free plan, which includes one project. "
                       "Upgrade, or archive your other project to work on this one.", limit="projects_readonly",
                       plan=plans.effective(firm))


def issues(fid, pid):
    """Rule issues, each tagged with the open change set (proposed or approved) that touches its element."""
    open_cs = store.changesets(fid, pid, "proposed") + store.changesets(fid, pid, "approved")
    els, rules = elements(pid), rules_for(fid, pid)
    out = checker.check(els, rules)
    for i in out:
        i["pending"] = next((c["id"] for c in open_cs
                             if any((o["element"] == i["element"] and o["prop"] in (i["prop"], "risers"))
                                    or i["element"] in o.get("rooms", []) for o in c["ops"])), None)
        if not i["fixable"] and i["prop"] == AREA and i["kind"] == "min":
            i["fixable"] = bool(area_fix(els, rules, i))  # a wall around the room can move
    return out


def _score(before, after):
    """New issues plus issues that got worse: lower is a kinder change."""
    old = {i["id"]: i for i in before}
    worse = 0
    for i in after:
        o = old.get(i["id"])
        if o is None:
            worse += 1
        elif abs(float(i["actual"]) - float(i["required"])) > abs(float(o["actual"]) - float(o["required"])) + 1e-6:
            worse += 1
    return worse


def area_fix(els, rules, issue):
    """The wall move that brings a room up to its area with the fewest side effects, as ops; [] if none."""
    room = next((e for e in els if e["id"] == issue["element"]), None)
    if not room or not (room.get("geom") or {}).get("outline"):
        return []
    before = checker.check(els, rules)
    best = None
    for wall, delta in geometry.area_fixes(els, room, float(issue["required"])):
        after = checker.check(geometry.move_wall(els, wall["id"], delta), rules)
        if any(i["id"] == issue["id"] for i in after):
            continue  # didn't get there (an odd-shaped room)
        key = (_score(before, after), len(geometry.rooms_affected(els, wall)), abs(delta))
        if best is None or key < best[0]:
            best = (key, wall, delta)
    if not best:
        return []
    return [dict(checker.op(best[1], "offset_mm", best[2]), **{"from": 0})]


def _effects(els, rules, ops):
    """What wall moves would do, in words, and the rooms they touch (for the reason and the queue)."""
    moved, lines, touched = els, [], set()
    for o in ops:
        if o["prop"] != "offset_mm":
            continue
        wall = next(e for e in moved if e["id"] == o["element"])
        touched |= {r["id"] for r in geometry.rooms_affected(moved, wall)}
        lines.append(f"{o['element_name']} moves {abs(float(o['to'])):g} mm {geometry.direction(wall, float(o['to']))}.")
        moved = geometry.move_wall(moved, o["element"], float(o["to"]))
    if not lines:
        return "", touched
    old = {e["id"]: e for e in els}
    for e in moved:
        if e["id"] in touched:
            a, b = old[e["id"]]["props"].get(AREA), e["props"].get(AREA)
            if a is not None and b is not None and abs(a - b) >= 0.01:
                lines.append(f"{e['props'].get('name') or e['id']}: {a:g} → {b:g} m².")
    before, after = checker.check(els, rules), checker.check(moved, rules)
    fixed = [i for i in before if i["id"] not in {x["id"] for x in after}]
    new = [i for i in after if i["id"] not in {x["id"] for x in before}]
    lines += [f"Resolves: {i['message']}" for i in fixed] + [f"New issue: {i['message']}" for i in new]
    return " ".join(lines), touched


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
        if el["type"] == "wall":
            try:
                to = float(o["to"])
            except (TypeError, ValueError):
                raise ChangeError("A wall move needs a distance in millimetres.")
            if not to or abs(to) > 5000:
                raise ChangeError("Move a wall by up to 5 000 mm, and not by zero.")
            full.append(dict(checker.op(el, "offset_mm", to), **{"from": 0}))  # moves are relative to where it is now
        else:
            full.append(checker.op(el, o["prop"], o["to"]))
    effects, touched = _effects(list(els.values()), rules_for(c.fid, pid), full)
    if effects:
        reason = ((reason or "").rstrip() + " What this does: " + effects).strip()
        for o in full:
            if o["prop"] == "offset_mm":
                o["rooms"] = sorted(touched)
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
    els = elements(pid)
    ops = area_fix(els, rules_for(c.fid, pid), issue) if issue["prop"] == AREA else checker.fix_ops(issue, els)
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
    ops = [dict(o, **({"from": 0, "to": -float(o["to"])} if o["prop"] == "offset_mm" else {"from": o["to"], "to": o["from"]}))
           for o in reversed(cs["ops"])]  # a wall goes back by the same distance
    # The approver asked for the revert, so the inverse goes straight to the host as approved.
    with store.db.tx():
        rid = store.add_changeset(cs["project_id"], f"Revert: {cs['title']}", f"Revert of {cid} requested by {c.name}",
                                  ops, "revert", by=c.uid, status="approved", reverts=cid)
        c.audit(cs["project_id"], "changeset.revert_requested", rid, {"reverts": cid, "title": cs["title"]})
    _auto_apply(c.fid, cs["project_id"], rid)
    return rid


def _auto_apply(fid, pid, cid):
    """The sample project has no CAD app attached, so the built-in sample host applies at once.
    Every other project waits for its plugin: Lintel never reports a change as applied that no CAD app made."""
    from . import demo
    p = store.project(fid, pid)
    if p and p["host"] == demo.SAMPLE_HOST:
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
