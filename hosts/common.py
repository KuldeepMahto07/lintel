"""Helpers shared by the Python host adapters (Revit, ArchiCAD, AutoCAD, Vectorworks).

Each adapter reads its app's own objects into plain records, then these helpers turn them into
the elements the Lintel protocol expects: {id, type, props, geom}, millimetres and square metres.
Python 2.7 and 3 compatible (Revit's pyRevit runs IronPython 2.7).
"""
import math

USES = (("corridor", ("corridor", "hall", "passage", "circulation")), ("exam", ("exam",)),
        ("bedroom", ("bedroom", "bed ", "sleep")), ("office", ("office",)), ("lobby", ("lobby", "reception", "foyer")),
        ("wc", ("wc", "toilet", "restroom", "bath")), ("stair", ("stair",)), ("storage", ("store", "storage")))


def guess_use(name):
    """A room's use from its name when the model doesn't say ("Corridor 2" -> corridor)."""
    n = " %s " % str(name or "").lower()
    for use, words in USES:
        if any(w in n for w in words):
            return use
    return ""


def polygon_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def min_side(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(max(xs) - min(xs), max(ys) - min(ys)) if pts else 0.0


def _seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / float(dx * dx + dy * dy)))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def near_rooms(point, rooms, tol_mm=300.0):
    """Ids of rooms whose outline passes within tol of the point (a door touches the rooms it joins)."""
    out = []
    for r in rooms:
        pts = r["geom"].get("outline") or []
        if any(_seg_dist(point, pts[i], pts[(i + 1) % len(pts)]) <= tol_mm for i in range(len(pts))):
            out.append(r["id"])
    return out


def room(eid, name, outline_mm, use=None, area_m2=None, clear_width_mm=None, **extra):
    pts = [[round(x, 1), round(y, 1)] for x, y in outline_mm]
    props = {"name": name or eid, "use": use if use is not None else guess_use(name),
             "area_m2": round(area_m2 if area_m2 is not None else polygon_area(pts) / 1e6, 2),
             "clear_width_mm": round(clear_width_mm if clear_width_mm is not None else min_side(pts), 1)}
    props.update(dict((k, v) for k, v in extra.items() if v is not None))
    return {"id": eid, "type": "room", "props": props, "geom": {"outline": pts}}


def door(eid, name, location_mm, clear_width_mm, exit=False, rooms=None, **extra):
    props = {"name": name or eid, "clear_width_mm": round(float(clear_width_mm), 1), "exit": bool(exit)}
    if rooms is not None:
        props["rooms"] = list(rooms)
    props.update(dict((k, v) for k, v in extra.items() if v is not None))
    return {"id": eid, "type": "door", "props": props, "geom": {"location": [round(location_mm[0], 1), round(location_mm[1], 1)]}}


def stair(eid, name, location_mm, riser_mm=None, tread_mm=None, risers=None, width_mm=None, total_rise_mm=None):
    props = {"name": name or eid}
    for k, v in (("riser_mm", riser_mm), ("tread_mm", tread_mm), ("risers", risers), ("width_mm", width_mm),
                 ("total_rise_mm", total_rise_mm)):
        if v is not None:
            props[k] = round(float(v), 1) if k != "risers" else int(v)
    return {"id": eid, "type": "stair", "props": props, "geom": {"location": [round(location_mm[0], 1), round(location_mm[1], 1)]}}


def wall(eid, start_mm, end_mm, thickness_mm=None):
    props = {"length_mm": round(math.hypot(end_mm[0] - start_mm[0], end_mm[1] - start_mm[1]), 1), "offset_mm": 0}
    if thickness_mm is not None:
        props["thickness_mm"] = round(float(thickness_mm), 1)
    return {"id": eid, "type": "wall", "props": props, "geom": {"start": list(start_mm), "end": list(end_mm)}}


def link_doors(elements, tol_mm=300.0):
    """Fill in `rooms` for doors that don't list them, from geometry."""
    rooms = [e for e in elements if e["type"] == "room"]
    for e in elements:
        if e["type"] == "door" and not e["props"].get("rooms"):
            e["props"]["rooms"] = near_rooms(e["geom"]["location"], rooms, tol_mm)
    return elements


def risers_for(total_rise_mm, max_riser_mm):
    """Fewest risers that keep each one at or under the limit."""
    return int(math.ceil(float(total_rise_mm) / float(max_riser_mm) - 1e-9))
