"""Lintel for Archicad (25 and later), through Graphisoft's Python API.

Install once:  pip install archicad
Run while Archicad has your project open:
    python hosts/archicad/lintel_archicad.py --watch
(or add it under Archicad's Options > Scripts so it's a menu item and can have a shortcut).

Archicad is a BIM app, so Lintel reads its native objects through the JSON interface:
  Zones   name, number, category and net area; the outline is the zone's 2D bounding box.
          Use comes from a "Lintel Use" property (group "Lintel") if you add one, else the zone name.
  Doors   width and position; the zones each door touches; exit = a "Lintel Exit" property,
          otherwise a door that touches only one zone.
  Stairs  riser height, tread depth, risers and width, where Archicad exposes them as properties.

Applying changes: Archicad's API can set property values but not geometry. Lintel applies
changes to zone names and to "Lintel Use"; a change to a door width or a stair is refused with a
note in Lintel saying to make that edit by hand, so the record stays honest.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import common  # noqa: E402
import lintel_client  # noqa: E402

PROPS = {  # our key -> candidate Archicad built-in property names (they vary by version)
    "zone_name": ["Zone_ZoneName"], "zone_number": ["Zone_ZoneNumber"],
    "zone_area": ["Zone_NetArea", "Zone_MeasuredArea", "Zone_Area"],
    "zone_category": ["Zone_ZoneCategoryName", "Zone_ZoneCategoryCode"],
    "width": ["General_Width", "OpeningSize_Width"], "element_id": ["General_ElementID"],
    "riser_mm": ["Stair_RiserHeight", "Stair_Riser_Height"], "tread_mm": ["Stair_TreadDepth", "Stair_Going"],
    "risers": ["Stair_NumberOfRisers", "Stair_RiserNumber"], "width_mm": ["Stair_FlightWidth", "Stair_Width"],
}


class Archicad:
    def __init__(self):
        from archicad import ACConnection
        conn = ACConnection.connect()
        if not conn:
            raise RuntimeError("Can't reach Archicad. Open your project in Archicad first.")
        self.acc, self.act, self.acu = conn.commands, conn.types, conn.utilities
        self.ids = {}
        for key, names in PROPS.items():
            for n in names:
                try:
                    self.ids[key] = self.acu.GetBuiltInPropertyId(n)
                    break
                except Exception:
                    continue
        for key, name in (("use", "Lintel Use"), ("exit", "Lintel Exit")):
            try:
                self.ids[key] = self.acu.GetUserDefinedPropertyId("Lintel", name)
            except Exception:
                pass

    def values(self, elements, keys):
        keys = [k for k in keys if k in self.ids]
        if not elements or not keys:
            return [{} for _ in elements]
        out = []
        for r in self.acc.GetPropertyValuesOfElements(elements, [self.ids[k] for k in keys]):
            row = {}
            for k, pv in zip(keys, r.propertyValues):
                v = getattr(pv, "propertyValue", None)
                if v is not None and getattr(v, "status", "normal") == "normal":
                    row[k] = getattr(v, "value", None)
            out.append(row)
        return out

    def boxes(self, elements):
        return [b.boundingBox2D for b in self.acc.Get2DBoundingBoxes(elements)] if elements else []

    def snapshot(self):
        acc = self.acc
        zones, doors, stairs = acc.GetElementsByType("Zone"), acc.GetElementsByType("Door"), acc.GetElementsByType("Stair")
        out = []
        for el, v, b in zip(zones, self.values(zones, ["zone_name", "zone_number", "zone_area", "zone_category", "use"]),
                            self.boxes(zones)):
            pts = [[b.xMin * 1000, b.yMin * 1000], [b.xMax * 1000, b.yMin * 1000], [b.xMax * 1000, b.yMax * 1000],
                   [b.xMin * 1000, b.yMax * 1000]]  # Archicad reports metres
            name = v.get("zone_name") or v.get("zone_number") or "Zone"
            use = (v.get("use") or "").lower() or common.guess_use("%s %s" % (name, v.get("zone_category") or ""))
            out.append(common.room(str(el.elementId.guid), name, pts, use=use, area_m2=v.get("zone_area"),
                                   number=v.get("zone_number")))
        for el, v, b in zip(doors, self.values(doors, ["width", "element_id", "exit"]), self.boxes(doors)):
            out.append(common.door(str(el.elementId.guid), v.get("element_id") or "Door",
                                   [(b.xMin + b.xMax) * 500, (b.yMin + b.yMax) * 500], (v.get("width") or 0) * 1000,
                                   exit=bool(v.get("exit"))))
        for el, v, b in zip(stairs, self.values(stairs, ["riser_mm", "tread_mm", "risers", "width_mm", "element_id"]),
                            self.boxes(stairs)):
            def mm(k):
                return v[k] * 1000 if v.get(k) is not None else None
            out.append(common.stair(str(el.elementId.guid), v.get("element_id") or "Stair",
                                    [(b.xMin + b.xMax) * 500, (b.yMin + b.yMax) * 500],
                                    riser_mm=mm("riser_mm"), tread_mm=mm("tread_mm"), risers=v.get("risers"), width_mm=mm("width_mm")))
        common.link_doors(out)
        if "exit" not in self.ids:  # no "Lintel Exit" property: a door that opens onto only one zone leads outside
            for e in out:
                if e["type"] == "door":
                    e["props"]["exit"] = len(e["props"].get("rooms") or []) < 2
        return out

    def get(self, eid, prop):
        e = dict((x["id"], x) for x in self.snapshot()).get(eid)
        if e is None or prop not in e["props"]:
            raise KeyError(eid)
        return e["props"][prop]

    def set_(self, eid, prop, value):
        key = {"name": "zone_name", "use": "use"}.get(prop)
        if key is None or key not in self.ids:
            raise ValueError("Archicad's API can't change %s; make this edit by hand and Lintel re-checks it" % prop)
        act = self.act
        pv = act.ElementPropertyValue(act.ElementId(eid), self.ids[key], act.NormalStringPropertyValue(str(value)))
        res = self.acc.SetPropertyValuesOfElements([pv])
        if res and getattr(res[0], "success", True) is False:
            raise ValueError("Archicad refused the change: %s" % getattr(res[0], "error", "unknown error"))


def main():
    ap = argparse.ArgumentParser(description="Sync the open Archicad project with Lintel.")
    ap.add_argument("--project", help="project key in Lintel (default: from the Archicad project name)")
    ap.add_argument("--watch", action="store_true", help="keep checking every 2 seconds until stopped")
    args = ap.parse_args()
    ac = Archicad()
    name = "Archicad project"
    try:
        name = ac.acc.GetProjectInfo().projectName or name
    except Exception:
        pass
    key = args.project or "archicad-" + "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")
    watch = lintel_client.Watcher(lintel_client.Client(key, "archicad", name), ac.snapshot, ac.get, ac.set_)
    print("Lintel: connected %s as %s" % (name, key))
    while True:
        first = watch.known is None
        applied, new = watch.tick()
        for cid, ok, err in applied:
            print("Lintel: %s %s %s" % ("applied" if ok else "refused", cid, err or ""))
        if first:
            print("Lintel: %d open issues. Open %s/app/p/%s" % (watch.count, watch.client.url, key))
        for i in new:
            print("Lintel: %s (%s) %s" % (i["message"], i["element_name"], i["ref"]))
        if not args.watch:
            return
        time.sleep(2)


if __name__ == "__main__":
    main()
