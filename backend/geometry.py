"""Moving walls: what happens to the rooms and doors around a wall when it shifts.

A wall's `offset_mm` is a move at right angles to the wall, relative to where it is now: positive
is to the left of the wall's start -> end direction. Room outline points that sit on the wall line
move with it (so the rooms on both sides stretch or shrink), doors in the wall move along, and room
areas are recomputed. Used by the sample host to apply a move, and by the server to show what a
proposed move would do before anyone approves it.
"""
import copy
import math

ON_LINE_MM = 1.0     # an outline point this close to the wall line belongs to it
DOOR_MM = 300.0      # a door this close to the wall line is in the wall


def _unit(wall):
    (sx, sy), (ex, ey) = wall["geom"]["start"], wall["geom"]["end"]
    length = math.hypot(ex - sx, ey - sy)
    if length < 1e-6:
        raise ValueError("wall %s has no length" % wall["id"])
    dx, dy = (ex - sx) / length, (ey - sy) / length
    return (sx, sy), (dx, dy), (-dy, dx), length


def _on_wall(p, wall, tol):
    (sx, sy), (dx, dy), (nx, ny), length = _unit(wall)
    rx, ry = p[0] - sx, p[1] - sy
    along, across = rx * dx + ry * dy, rx * nx + ry * ny
    return abs(across) <= tol and -tol <= along <= length + tol


def area_m2(pts):
    a = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    return abs(a) / 2e6


def _min_side(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(max(xs) - min(xs), max(ys) - min(ys))


def direction(wall, delta):
    """'east', 'north-west'... for a move of delta mm, as people say it."""
    _, _, (nx, ny), _ = _unit(wall)
    vx, vy = nx * delta, ny * delta
    ns = "north" if vy > 0.5 * abs(vx) else "south" if vy < -0.5 * abs(vx) else ""
    ew = "east" if vx > 0.5 * abs(vy) else "west" if vx < -0.5 * abs(vy) else ""
    return "-".join(x for x in (ns, ew) if x) or "sideways"


def rooms_affected(elements, wall):
    """Rooms with an edge lying along this wall (they change shape when it moves)."""
    out = []
    for r in elements:
        pts = (r.get("geom") or {}).get("outline") or []
        if r["type"] == "room" and sum(1 for p in pts if _on_wall(p, wall, ON_LINE_MM)) >= 2:
            out.append(r)
    return out


def move_wall(elements, wall_id, delta):
    """A copy of the model with the wall moved delta mm at right angles."""
    els = copy.deepcopy(elements)
    wall = next(e for e in els if e["id"] == wall_id)
    _, _, (nx, ny), _ = _unit(wall)
    vx, vy = nx * delta, ny * delta
    for e in els:
        g = e.get("geom") or {}
        if e["type"] == "room" and g.get("outline"):
            pts = g["outline"]
            old_side = _min_side(pts)
            hits = [p for p in pts if _on_wall(p, wall, ON_LINE_MM)]
            if len(hits) < 2:
                continue  # a room that only touches the wall at a corner keeps its shape
            for p in hits:
                p[0], p[1] = round(p[0] + vx, 1), round(p[1] + vy, 1)
            e["props"]["area_m2"] = round(area_m2(pts), 2)
            cw = e["props"].get("clear_width_mm")
            if cw is not None and abs(float(cw) - old_side) < 1.0:  # width came from the outline: keep it in step
                e["props"]["clear_width_mm"] = round(_min_side(pts), 1)
        elif e["type"] == "door" and g.get("location") and _on_wall(g["location"], wall, DOOR_MM):
            g["location"] = [round(g["location"][0] + vx, 1), round(g["location"][1] + vy, 1)]
    for k in ("start", "end"):
        wall["geom"][k] = [round(wall["geom"][k][0] + vx, 1), round(wall["geom"][k][1] + vy, 1)]
    wall["props"]["offset_mm"] = 0  # offsets are relative: the moved wall is the new baseline
    return els


def area_fixes(elements, room, required_m2):
    """Candidate wall moves that bring a room up to an area: [(wall, delta mm)], each outward from the room."""
    pts = room["geom"]["outline"]
    short = required_m2 - area_m2(pts)
    if short <= 0:
        return []
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    out = []
    for w in elements:
        if w["type"] != "wall":
            continue
        on = [p for p in pts if _on_wall(p, w, ON_LINE_MM)]
        if len(on) < 2:
            continue
        edge = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a in on for b in on)
        if edge < 1:
            continue
        (sx, sy), _, (nx, ny), _ = _unit(w)
        outward = -1 if (cx - sx) * nx + (cy - sy) * ny > 0 else 1  # away from the room's centre
        out.append((w, outward * math.ceil(short * 1e6 / edge / 10.0) * 10.0))
    return out
