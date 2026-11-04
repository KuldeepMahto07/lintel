"""Lintel for AutoCAD on Windows (2018 and later), through AutoCAD's COM interface.

Install once:  pip install pywin32
Run while the drawing is open in AutoCAD:
    python hosts/autocad/lintel_autocad.py --watch

AutoCAD has no rooms or doors as objects, so Lintel reads four layers (like the Rhino plugin):
  Lintel-Rooms   closed polylines; a text or multiline text on the same layer inside the outline
                 is the room's name ("Exam 1", "Corridor"), and the use comes from it.
  Lintel-Doors   block references with attributes NAME, CLEAR_WIDTH_MM and EXIT (yes/no). Without a
                 CLEAR_WIDTH_MM attribute the width is the block's X scale x 1000 mm (a 1000 mm block).
  Lintel-Stairs  block references with attributes NAME, RISER_MM, TREAD_MM, RISERS, WIDTH_MM, TOTAL_RISE_MM.
  Lintel-Walls   lines or polylines.
Element ids are AutoCAD handles. Drawing units come from INSUNITS (mm, cm, m, inches, feet).

Approved change sets are wrapped in one undo mark, so a single U undoes a Lintel edit. A door
width change updates CLEAR_WIDTH_MM and stretches the block along its own X axis.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import common  # noqa: E402
import lintel_client  # noqa: E402

LAYERS = {"LINTEL-ROOMS": "room", "LINTEL-DOORS": "door", "LINTEL-STAIRS": "stair", "LINTEL-WALLS": "wall"}
UNITS = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}  # INSUNITS -> mm per drawing unit
NUMERIC = {"CLEAR_WIDTH_MM", "RISER_MM", "TREAD_MM", "RISERS", "WIDTH_MM", "TOTAL_RISE_MM"}
TAGS = {"name": "NAME", "clear_width_mm": "CLEAR_WIDTH_MM", "riser_mm": "RISER_MM", "tread_mm": "TREAD_MM",
        "risers": "RISERS", "width_mm": "WIDTH_MM"}


def _attrs(ref):
    """TAG -> (value, attribute reference) for a block reference."""
    out = {}
    if getattr(ref, "HasAttributes", False):
        for a in ref.GetAttributes():
            v = a.TextString
            if a.TagString.upper() in NUMERIC:
                try:
                    v = float(v)
                except ValueError:
                    pass
            out[a.TagString.upper()] = (v, a)
    return out


def _inside(pt, poly):
    x, y, hit = pt[0], pt[1], False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            hit = not hit
    return hit


def _door_width(ref, a):
    return float(a["CLEAR_WIDTH_MM"][0]) if "CLEAR_WIDTH_MM" in a else abs(ref.XScaleFactor) * 1000.0


class AutoCAD:
    def __init__(self):
        import win32com.client
        self.doc = win32com.client.GetActiveObject("AutoCAD.Application").ActiveDocument

    def _scale(self):
        return UNITS.get(int(self.doc.GetVariable("INSUNITS")), 1.0)

    def snapshot(self):
        s = self._scale()
        rooms, texts, out = [], [], []
        for e in self.doc.ModelSpace:
            kind, name = LAYERS.get(str(e.Layer).upper()), e.ObjectName
            if kind == "room" and name == "AcDbPolyline" and e.Closed:
                c = list(e.Coordinates)
                rooms.append((e, [[c[i] * s, c[i + 1] * s] for i in range(0, len(c), 2)]))
            elif kind == "room" and name in ("AcDbText", "AcDbMText"):
                p = e.InsertionPoint
                texts.append((e, [p[0] * s, p[1] * s]))
            elif kind in ("door", "stair") and name == "AcDbBlockReference":
                a, p = _attrs(e), e.InsertionPoint
                loc = [p[0] * s, p[1] * s]

                def val(k):
                    return a[k][0] if k in a else None
                if kind == "door":
                    out.append(common.door(e.Handle, val("NAME") or e.EffectiveName, loc, _door_width(e, a),
                                           exit=str(val("EXIT") or "").strip().lower() in ("1", "yes", "true", "y")))
                else:
                    out.append(common.stair(e.Handle, val("NAME") or e.EffectiveName, loc, riser_mm=val("RISER_MM"),
                                            tread_mm=val("TREAD_MM"), risers=val("RISERS"), width_mm=val("WIDTH_MM"),
                                            total_rise_mm=val("TOTAL_RISE_MM")))
            elif kind == "wall" and name in ("AcDbLine", "AcDbPolyline"):
                if name == "AcDbLine":
                    a, b = e.StartPoint, e.EndPoint
                else:
                    c = list(e.Coordinates)
                    a, b = c[:2], c[-2:]
                out.append(common.wall(e.Handle, [a[0] * s, a[1] * s], [b[0] * s, b[1] * s]))
        for e, pts in rooms:
            label = next((t for t, p in texts if _inside(p, pts)), None)
            out.append(common.room(e.Handle, label.TextString if label is not None else "Room " + e.Handle, pts,
                                   area_m2=e.Area * s * s / 1e6, label=label.Handle if label is not None else None))
        return common.link_doors(out)

    def _obj(self, eid):
        try:
            return self.doc.HandleToObject(eid)
        except Exception:
            raise KeyError(eid)

    def get(self, eid, prop):
        e = next((x for x in self.snapshot() if x["id"] == eid), None)
        if e is None or prop not in e["props"]:
            raise KeyError(eid)
        return e["props"][prop]

    def set_(self, eid, prop, value):
        obj = self._obj(eid)
        if obj.ObjectName == "AcDbPolyline":  # a room: its name lives in its text label
            e = next((x for x in self.snapshot() if x["id"] == eid), None)
            label = e and e["props"].get("label")
            if prop != "name" or not label:
                raise ValueError("Lintel can only rename a room that has a text label inside its outline")
            self._obj(label).TextString = str(value)
            return
        a, tag = _attrs(obj), TAGS.get(prop)
        if tag is None:
            raise ValueError("Lintel can't change %s in AutoCAD" % prop)
        if prop == "clear_width_mm":
            obj.XScaleFactor = obj.XScaleFactor * float(value) / _door_width(obj, a)
        if prop == "riser_mm" and "TOTAL_RISE_MM" in a:  # more risers, each one lower
            n = common.risers_for(a["TOTAL_RISE_MM"][0], value)
            if "RISERS" in a:
                a["RISERS"][1].TextString = str(n)
            value = round(float(a["TOTAL_RISE_MM"][0]) / n, 1)
        if tag in a:
            a[tag][1].TextString = ("%g" % value) if isinstance(value, float) else str(value)
        elif prop != "clear_width_mm":
            raise ValueError("the block has no %s attribute" % tag)
        obj.Update()

    def begin(self, title):
        self.doc.StartUndoMark()

    def commit(self):
        self.doc.EndUndoMark()
        self.doc.Regen(1)

    def rollback(self):
        self.doc.EndUndoMark()
        self.doc.SendCommand("_.U ")


def main():
    ap = argparse.ArgumentParser(description="Sync the open AutoCAD drawing with Lintel.")
    ap.add_argument("--project", help="project key in Lintel (default: from the drawing name)")
    ap.add_argument("--watch", action="store_true", help="keep checking every 2 seconds until stopped")
    args = ap.parse_args()
    cad = AutoCAD()
    name = os.path.splitext(cad.doc.Name)[0]
    key = args.project or "autocad-" + "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")
    watch = lintel_client.Watcher(lintel_client.Client(key, "autocad", name), cad.snapshot, cad.get, cad.set_,
                                  begin=cad.begin, commit=cad.commit, rollback=cad.rollback)
    print("Lintel: connected %s as %s" % (name, key))
    while True:
        first = watch.known is None
        try:
            applied, new = watch.tick()
        except Exception as ex:  # AutoCAD busy ("call was rejected by callee") or server unreachable
            print("Lintel: waiting (%s)" % ex)
            applied, new = [], []
        for cid, ok, err in applied:
            print("Lintel: %s %s %s" % ("applied" if ok else "refused", cid, err or ""))
        if first and watch.known is not None:
            print("Lintel: %d open issues. Open %s/app/p/%s" % (watch.count, watch.client.url, key))
        for i in new:
            print("Lintel: %s (%s) %s" % (i["message"], i["element_name"], i["ref"]))
        if not args.watch:
            return
        time.sleep(2)


if __name__ == "__main__":
    main()
