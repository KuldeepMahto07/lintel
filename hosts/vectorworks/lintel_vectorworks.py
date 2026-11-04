"""Lintel for Vectorworks (2021 and later), in Vectorworks' built-in Python 3.

Install: Tools > Plug-ins > Plug-in Manager > New > Menu Command "Lintel Sync", language Python,
script:   import sys; sys.path.insert(0, r"<path>\\hosts\\vectorworks"); import lintel_vectorworks; lintel_vectorworks.run()
then add the command to your workspace (Tools > Workspaces > Edit) and give it a shortcut.

Vectorworks runs one script at a time, so Lintel can't watch in the background here: each run of
Lintel Sync applies approved changes, re-checks the drawing and lists what's new. Run it after
edits, or before you hand a sheet on.

Objects are found by class, with their values in a record format called "Lintel" (created on
the first run; attach it from the Object Info palette's Data tab):
  Lintel-Rooms   polygons, polylines or rectangles. Fields: name, use (optional; guessed from name).
  Lintel-Doors   symbols. Fields: name, clear_width_mm, exit (yes/no). Without clear_width_mm the
                 width is the symbol's width on the plan.
  Lintel-Stairs  any object. Fields: name, riser_mm, tread_mm, risers, width_mm, total_rise_mm.
  Lintel-Walls   lines or walls.
Element ids are Vectorworks object UUIDs. A whole run is one undo step in Vectorworks.
"""
import json
import os
import sys

import vs  # Vectorworks' scripting module

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import common  # noqa: E402
import lintel_client  # noqa: E402

CLASSES = {"Lintel-Rooms": "room", "Lintel-Doors": "door", "Lintel-Stairs": "stair", "Lintel-Walls": "wall"}
FIELDS = ["name", "use", "clear_width_mm", "exit", "riser_mm", "tread_mm", "risers", "width_mm", "total_rise_mm"]
NUMERIC = {"clear_width_mm", "riser_mm", "tread_mm", "risers", "width_mm", "total_rise_mm"}
REC = "Lintel"


def ensure_record():
    if vs.GetObject(REC) is None:
        for f in FIELDS:
            vs.NewField(REC, f, "", 4, 0)  # 4 = text field


def _mm():
    return 25.4 / vs.GetUnits()[3]  # GetUnits() -> (fraction, display, format, units per inch, name, squareName)


def _fields(h):
    out = {}
    for f in FIELDS:
        v = vs.GetRField(h, REC, f)
        if v == "":
            continue
        if f in NUMERIC:
            try:
                v = float(v)
            except ValueError:
                continue
        elif f == "exit":
            v = v.strip().lower() in ("1", "yes", "true", "y")
        out[f] = v
    return out


def _bbox(h, s):
    (x1, y1), (x2, y2) = vs.GetBBox(h)
    return x1 * s, y1 * s, x2 * s, y2 * s


def _outline(h, s):
    if vs.GetTypeN(h) == 3:  # rectangle
        x1, y1, x2, y2 = _bbox(h, s)
        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    return [[p[0] * s, p[1] * s] for p in (vs.GetPolyPt(h, i) for i in range(1, vs.GetVertNum(h) + 1))]


def _center(h, s):
    x1, y1, x2, y2 = _bbox(h, s)
    return [(x1 + x2) / 2, (y1 + y2) / 2]


def _door_width(h, f, s):
    if "clear_width_mm" in f:
        return f["clear_width_mm"]
    x1, _, x2, _ = _bbox(h, s)
    return abs(x2 - x1)


def snapshot():
    s, found = _mm(), []

    def visit(h):
        kind = CLASSES.get(vs.GetClass(h))
        if kind:
            found.append((kind, h))
    vs.ForEachObject(visit, "(%s)" % " | ".join("(C='%s')" % c for c in CLASSES))
    out = []
    for kind, h in found:
        f, eid = _fields(h), vs.GetObjectUuid(h)
        name = f.get("name") or vs.GetName(h) or kind
        if kind == "room":
            out.append(common.room(eid, name, _outline(h, s), use=f.get("use")))
        elif kind == "door":
            out.append(common.door(eid, name, _center(h, s), _door_width(h, f, s), exit=f.get("exit", False)))
        elif kind == "stair":
            out.append(common.stair(eid, name, _center(h, s), riser_mm=f.get("riser_mm"), tread_mm=f.get("tread_mm"),
                                    risers=f.get("risers"), width_mm=f.get("width_mm"), total_rise_mm=f.get("total_rise_mm")))
        else:
            (x1, y1), (x2, y2) = vs.GetSegPt1(h), vs.GetSegPt2(h)
            out.append(common.wall(eid, [x1 * s, y1 * s], [x2 * s, y2 * s]))
    return common.link_doors(out)


def _handle(eid):
    h = vs.GetObjectByUuid(eid)
    if h is None:
        raise KeyError(eid)
    return h


def get(eid, prop):
    e = next((x for x in snapshot() if x["id"] == eid), None)
    if e is None or prop not in e["props"]:
        raise KeyError(eid)
    return e["props"][prop]


def set_(eid, prop, value):
    if prop not in FIELDS:
        raise ValueError("Lintel can't change %s in Vectorworks" % prop)
    h = _handle(eid)
    vs.SetRecord(h, REC)
    if prop == "clear_width_mm" and vs.GetTypeN(h) == 15:  # a door symbol: stretch it along X
        old = _door_width(h, _fields(h), _mm())
        if old:
            c = _center(h, 1.0)
            vs.HScale2D(h, c[0], c[1], float(value) / old, 1.0, False)
    if prop == "riser_mm":
        f = _fields(h)
        if "total_rise_mm" in f:  # more risers, each one lower
            n = common.risers_for(f["total_rise_mm"], value)
            vs.SetRField(h, REC, "risers", str(n))
            value = round(f["total_rise_mm"] / n, 1)
    vs.SetRField(h, REC, prop, ("%g" % value) if isinstance(value, float) else str(value))
    if prop == "name":
        vs.SetName(h, str(value))
    vs.ResetObject(h)


def _state_path(key):
    return os.path.join(os.path.expanduser("~"), ".lintel", "vectorworks-%s.json" % key)


def run():
    ensure_record()
    name = os.path.splitext(os.path.basename(vs.GetFName() or "Untitled"))[0]
    key = "vectorworks-" + "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")
    watch = lintel_client.Watcher(lintel_client.Client(key, "vectorworks", name), snapshot, get, set_)
    path = _state_path(key)
    try:
        with open(path) as f:
            watch.known = set(json.load(f)["known"])  # issues already reported on an earlier run
    except (IOError, OSError, ValueError, KeyError):
        pass
    try:
        applied, new = watch.tick()
    except Exception as ex:
        vs.AlrtDialog("Lintel couldn't sync: %s" % ex)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"known": sorted(watch.known or [])}, f)
    vs.ReDrawAll()
    lines = ["%s %s" % ("Applied" if ok else "Refused", err or cid) for cid, ok, err in applied]
    lines += ["New: %s (%s)" % (i["message"], i["ref"]) for i in new[:8]]
    lines.append("%d open issue%s. Review them at %s/app/p/%s" % (watch.count, "" if watch.count == 1 else "s",
                                                                 watch.client.url, key))
    vs.AlrtDialog("\n".join(lines))
