#! python3
"""Build the sample clinic in a new Rhino 8 document (millimetres), following the Lintel layer
and user-text convention. Then run lintel_rhino.py to connect it.

    _-RunPythonScript "<path>\\hosts\\rhino\\build_sample.py"
"""
import json
import os

import Rhino
import System
from Rhino.Geometry import Line, Plane, Point3d, Polyline, Rectangle3d, Transform

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "samples", "clinic.json")


def layer(doc, path):
    idx = doc.Layers.FindByFullPath(path, -1)
    if idx >= 0:
        return idx
    parent, _, name = path.rpartition("::")
    lay = Rhino.DocObjects.Layer()
    lay.Name = name
    if parent:
        lay.ParentLayerId = doc.Layers[layer(doc, parent)].Id
    return doc.Layers.Add(lay)


def attrs(doc, path, props, name=None):
    a = Rhino.DocObjects.ObjectAttributes()
    a.LayerIndex = layer(doc, path)
    a.Name = name or props.get("name", "")
    for k, v in props.items():
        if k in ("area_m2", "level"):
            continue  # area is measured from the geometry
        a.SetUserString(k, ",".join(v) if isinstance(v, list) else str(v).lower() if isinstance(v, bool) else str(v))
    return a


def door_block(doc):
    idef = doc.InstanceDefinitions.Find("LintelDoor")
    if idef:
        return idef.Index
    leaf = Rectangle3d(Plane.WorldXY, Point3d(-500, -50, 0), Point3d(500, 50, 0)).ToNurbsCurve()
    return doc.InstanceDefinitions.Add("LintelDoor", "Lintel door, 1000 mm clear at scale 1", Point3d.Origin, [leaf])


def main():
    doc = Rhino.RhinoDoc.ActiveDoc
    doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters
    model = json.load(open(SAMPLE, encoding="utf-8"))
    ids = {}
    blk = door_block(doc)
    for el in model["elements"]:
        p, g = el["props"], el["geom"]
        if el["type"] == "room":
            pts = [Point3d(x, y, 0) for x, y in g["outline"]]
            pts.append(pts[0])
            ids[el["id"]] = doc.Objects.AddPolyline(Polyline(pts), attrs(doc, "Lintel::Rooms", p))
    for el in model["elements"]:
        p, g = dict(el["props"]), el["geom"]
        if el["type"] == "door":
            p["rooms"] = [str(ids[r]) for r in p.get("rooms", [])]
            x, y = g["location"]
            xf = Transform.Translation(x, y, 0) * Transform.Scale(Plane.WorldXY, p["clear_width_mm"] / 1000.0, 1, 1)
            doc.Objects.AddInstanceObject(blk, xf, attrs(doc, "Lintel::Doors", p))
        elif el["type"] == "stair":
            x, y = g["location"]
            run = p["tread_mm"] * (p["risers"] - 1)
            rect = Rectangle3d(Plane.WorldXY, Point3d(x - run / 2, y - p["width_mm"] / 2, 0), Point3d(x + run / 2, y + p["width_mm"] / 2, 0))
            doc.Objects.AddCurve(rect.ToNurbsCurve(), attrs(doc, "Lintel::Stairs", p))
        elif el["type"] == "wall":
            (x0, y0), (x1, y1) = g["start"], g["end"]
            doc.Objects.AddLine(Line(Point3d(x0, y0, 0), Point3d(x1, y1, 0)), attrs(doc, "Lintel::Walls", p, el["id"]))
    doc.Views.ActiveView.ActiveViewport.ZoomExtents()
    doc.Views.Redraw()
    Rhino.RhinoApp.WriteLine("Lintel sample clinic built: %d elements." % len(model["elements"]))


if __name__ == "__main__":
    main()
