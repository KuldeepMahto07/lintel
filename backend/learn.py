"""Learning the office standard from the firm's own drawings.

After a sync, Lintel looks at the latest model of every project in the firm. When most elements of
one kind are drawn to a value that is stricter than the rule in force (say 85% of doors are 900 mm
clear against a code minimum of 813 mm), it proposes that value as a firm rule. A proposal is only
a suggestion: an admin activates or discards it on the Rules page, and a discarded suggestion is
never offered again. Nothing here edits a model or switches a rule on.
"""
import math
import time

from . import store

MIN_ELEMENTS = 6   # don't generalise from a handful of elements
SHARE = 0.8        # the value most of the drawings already meet
EVERY = 60         # seconds between runs for one firm; syncs arrive every couple of seconds
_last = {}

# (type, prop, kind, where-key, rounding step, unit, label)
TARGETS = [
    ("door", "clear_width_mm", "min", None, 10, "mm", "Door clear width"),
    ("stair", "riser_mm", "max", None, 1, "mm", "Stair riser height"),
    ("stair", "tread_mm", "min", None, 1, "mm", "Stair tread depth"),
    ("stair", "width_mm", "min", None, 10, "mm", "Stair width"),
    ("room", "clear_width_mm", "min", "corridor", 10, "mm", "Corridor clear width"),
    ("room", "area_m2", "min", "*", 0.5, "m²", "Room area"),
]
FIXABLE = {("door", "clear_width_mm"), ("stair", "riser_mm"), ("stair", "tread_mm")}


def after_sync(fid, force=False):
    """Called after every model sync; does the work at most once a minute per firm."""
    if not force and time.time() - _last.get(fid, 0) < EVERY:
        return []
    _last[fid] = time.time()
    return suggest(fid)


def _elements(fid):
    out = []
    for p in store.projects(fid):
        snap = store.latest_snapshot(p["id"])
        if snap:
            out += [(p["id"], e) for e in snap["elements"]]
    return out


def _groups(elements):
    """(target, use) -> [(project, value)] for every target that has numbers in the drawings."""
    groups = {}
    for t in TARGETS:
        typ, prop, where = t[0], t[1], t[3]
        for pid, e in elements:
            if e["type"] != typ:
                continue
            use = str(e["props"].get("use", "")).lower()
            if where == "corridor" and use != "corridor":
                continue
            if where == "*" and (not use or use == "corridor"):
                continue
            try:
                v = float(e["props"][prop])
            except (KeyError, TypeError, ValueError):
                continue
            groups.setdefault((t, use if where == "*" else where), []).append((pid, v))
    return groups


def _quantile(values, kind, step):
    """The value SHARE of elements already meet: the low end for a minimum, the high end for a maximum."""
    vals = sorted(values)
    if kind == "min":
        v = vals[max(0, math.ceil(len(vals) * (1 - SHARE)) - 1)]
        v = math.floor(v / step) * step
    else:
        v = vals[min(len(vals) - 1, math.ceil(len(vals) * SHARE) - 1)]
        v = math.ceil(v / step) * step
    return round(v, 2)


def _current(rules, typ, prop, kind, use):
    """The strictest active rule on the same property, or None."""
    vals = [r["value"] for r in rules if r.get("status") == "active" and r["applies_to"] == typ and r.get("prop") == prop
            and r["kind"] == kind and (r.get("where") or {}).get("use") == use]
    if not vals:
        return None
    return max(vals) if kind == "min" else min(vals)


def suggest(fid):
    rules = store.rules(fid)
    have = {r["id"]: r for r in rules}
    dismissed = store.dismissed_suggestions(fid)
    made = []
    for (t, use), pairs in _groups(_elements(fid)).items():
        typ, prop, kind, _, step, unit, label = t
        if len(pairs) < MIN_ELEMENTS:
            continue
        key = "-".join(x for x in (typ, prop.replace("_", "-"), use) if x)
        rid = "learned-" + key
        if key in dismissed or (rid in have and have[rid]["status"] != "proposed"):
            continue
        value = _quantile([v for _, v in pairs], kind, step)
        current = _current(rules, typ, prop, kind, use)
        stricter = current is None or (value > current * 1.02 if kind == "min" else value < current * 0.98)
        if value <= 0 or not stricter or (rid in have and have[rid]["value"] == value):
            continue
        meets = sum(1 for _, v in pairs if (v >= value if kind == "min" else v <= value))
        projects = len({p for p, _ in pairs})
        noun = {"door": "doors", "stair": "stairs"}.get(typ, "corridors" if use == "corridor" else f"{use} rooms")
        name = f"{label}, {use}" if typ == "room" and use != "corridor" else label
        rule = {"id": rid, "name": f"{name} (your standard)", "kind": kind, "applies_to": typ, "prop": prop,
                "value": value, "unit": unit, "severity": "warning", "fixable": (typ, prop) in FIXABLE, "source": "learned",
                "ref": f"Learned from your drawings: {meets} of {len(pairs)} {noun} in {projects} project"
                       f"{'' if projects == 1 else 's'} are {'at least' if kind == 'min' else 'at most'} {value:g} {unit}"
                       + (f"; the rule in force is {current:g} {unit}." if current is not None else ".")}
        if typ == "room":
            rule["where"] = {"use": use}
        with store.db.tx():
            store.put_rule(fid, rule, "proposed")
            if rid not in have:
                store.audit(fid, None, "learn", "rule.proposed", rid, {"name": rule["name"], "value": value, "unit": unit},
                            actor_name="Lintel, from your drawings")
        made.append(rid)
    return made


def dismiss(fid, rule):
    """An admin discarded a learned suggestion: don't offer that property again."""
    if rule.get("source") == "learned" and rule.get("status") == "proposed":
        store.dismiss_suggestion(fid, rule["id"].removeprefix("learned-"))
