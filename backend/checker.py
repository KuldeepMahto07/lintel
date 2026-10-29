"""Deterministic rule checker and fix builder.

A rule is the firm's own requirement: a numeric parameter plus a reference to the code
section it was taken from. No code text is stored. Kinds:
  min / max  - compare one element property against `value`
  egress     - longest travel distance from any room corner to the nearest exit door
"""
import heapq
import math

OPS = {"min": lambda a, v: a >= v - 1e-6, "max": lambda a, v: a <= v + 1e-6}


def _matches(el, rule):
    if el["type"] != rule["applies_to"]:
        return False
    return all(str(el["props"].get(k, "")).lower() == str(v).lower() for k, v in (rule.get("where") or {}).items())


def _name(el):
    return el["props"].get("name") or el["id"]


def check(elements, rules):
    issues = []
    for rule in rules:
        if rule.get("status", "active") != "active":
            continue
        if rule["kind"] == "egress":
            issues += _check_egress(elements, rule)
            continue
        for el in elements:
            if not _matches(el, rule):
                continue
            actual = el["props"].get(rule["prop"])
            if actual is None:
                continue
            if not OPS[rule["kind"]](float(actual), float(rule["value"])):
                word = "at least" if rule["kind"] == "min" else "at most"
                issues.append(_issue(rule, el, actual,
                                     f"{_name(el)}: {rule['prop']} is {actual:g} {rule.get('unit', '')}, "
                                     f"rule requires {word} {rule['value']:g} {rule.get('unit', '')}."))
    return issues


def _issue(rule, el, actual, message, fixable=None):
    return {
        "id": f"{rule['id']}:{el['id']}",
        "rule": rule["id"], "rule_name": rule["name"], "element": el["id"], "element_name": _name(el),
        "element_type": el["type"], "prop": rule.get("prop"), "actual": round(float(actual), 1),
        "required": rule["value"], "kind": rule["kind"], "unit": rule.get("unit", ""), "ref": rule.get("ref", ""),
        "severity": rule.get("severity", "error"), "message": message,
        "fixable": bool(rule.get("fixable")) if fixable is None else fixable,
    }


# ---- egress ----------------------------------------------------------------

def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def egress_distances(elements):
    """Approximate exit-access travel distance per room (mm).

    Graph nodes are doors; two doors that open into the same room are joined by a straight
    line across that room. Exit doors are the targets. A room's travel distance is the worst
    case over its outline corners of (corner -> door in that room -> nearest exit).
    Straight lines ignore furniture and walls inside the room, so this underestimates
    real paths in L-shaped rooms. That limit is documented in the README.
    """
    rooms = {e["id"]: e for e in elements if e["type"] == "room"}
    doors = [e for e in elements if e["type"] == "door" and e["geom"].get("location")]
    by_room = {rid: [] for rid in rooms}
    for d in doors:
        for rid in d["props"].get("rooms", []):
            if rid in by_room:
                by_room[rid].append(d)
    best = {d["id"]: (0.0 if d["props"].get("exit") else math.inf) for d in doors}
    loc = {d["id"]: d["geom"]["location"] for d in doors}
    heap = [(0.0, d["id"]) for d in doors if d["props"].get("exit")]
    while heap:
        dist, did = heapq.heappop(heap)
        if dist > best[did]:
            continue
        door = next(d for d in doors if d["id"] == did)
        for rid in door["props"].get("rooms", []):
            for other in by_room.get(rid, []):
                nd = dist + _dist(loc[did], loc[other["id"]])
                if nd < best[other["id"]]:
                    best[other["id"]] = nd
                    heapq.heappush(heap, (nd, other["id"]))
    out = {}
    for rid, room in rooms.items():
        corners = room["geom"].get("outline") or []
        if not corners or not by_room[rid]:
            continue
        out[rid] = max(min(_dist(c, loc[d["id"]]) + best[d["id"]] for d in by_room[rid]) for c in corners)
    return out


def _check_egress(elements, rule):
    issues = []
    rooms = {e["id"]: e for e in elements if e["type"] == "room"}
    for rid, dist in egress_distances(elements).items():
        el = rooms[rid]
        if rule.get("where") and not _matches(el, dict(rule, applies_to="room")):
            continue
        if dist > float(rule["value"]):
            issues.append(_issue(rule, el, dist,
                                 f"{_name(el)}: travel distance to the nearest exit is about {dist / 1000:.1f} m, "
                                 f"rule allows {rule['value'] / 1000:.1f} m. Add an exit or move doors.",
                                 fixable=False))
    return issues


# ---- fixes -----------------------------------------------------------------

def fix_ops(issue, elements):
    """Ops that bring one element into line with its rule, or [] when the fix is a design decision."""
    if not issue["fixable"]:
        return []
    el = next(e for e in elements if e["id"] == issue["element"])
    prop, target = issue["prop"], float(issue["required"])
    if el["type"] == "stair" and prop == "riser_mm" and el["props"].get("total_rise_mm"):
        total = float(el["props"]["total_rise_mm"])
        n = math.ceil(total / target - 1e-9)
        ops = [op(el, "risers", n), op(el, "riser_mm", round(total / n, 1))]
        return [o for o in ops if o["from"] != o["to"]]
    return [op(el, prop, target)]


def op(el, prop, to):
    return {"op": "set_prop", "element": el["id"], "element_name": _name(el), "prop": prop,
            "from": el["props"].get(prop), "to": to}
