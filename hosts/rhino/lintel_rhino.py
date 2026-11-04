#! python3
"""Lintel for Rhino 8 (Python 3 / RhinoCommon).

Run once to connect the open model to Lintel and open the floating Lintel window; run again to
disconnect. In Rhino:  _-RunPythonScript "<path>\\hosts\\rhino\\lintel_rhino.py"
The first run adds a `Lintel` command alias and, if the key is free, the Ctrl+Shift+L shortcut,
so after that the window is one keystroke away.

While connected Lintel watches the model: it re-checks within a couple of seconds of each edit and
writes new issues to the command line, so problems are found the moment they are drawn.

Model convention (Rhino has no BIM objects, so Lintel reads layers and Attribute User Text):
  Lintel::Rooms   closed planar curves. User text: name, use (corridor, exam, bedroom, office...),
                  optional clear_width_mm (corridors; else the shorter side of the bounding box).
  Lintel::Doors   block instances of "LintelDoor" (1000 mm wide at scale 1) or any object.
                  User text: name, clear_width_mm, exit (true/false), optional rooms (ids, comma list).
  Lintel::Stairs  any object. User text: name, riser_mm, tread_mm, risers, width_mm, total_rise_mm.
  Lintel::Walls   curves. User text: thickness_mm, height_mm.
Element ids are Rhino object ids. All values are sent in millimetres.

Approved change sets are applied on Rhino's UI thread (Idle event), inside one undo record each,
so Ctrl+Z undoes a whole Lintel edit. Nothing is written without an approved change set.
"""
import os
import sys
import time

import Rhino
import scriptcontext as sc
import System

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # hosts/ for lintel_client
import lintel_client  # noqa: E402

STICKY = "lintel_state"
LAYERS = {"Lintel::Rooms": "room", "Lintel::Doors": "door", "Lintel::Stairs": "stair", "Lintel::Walls": "wall"}
NUMERIC = {"clear_width_mm", "riser_mm", "tread_mm", "risers", "width_mm", "total_rise_mm", "thickness_mm", "height_mm"}
POLL_SECONDS = 2.0


def _doc():
    return Rhino.RhinoDoc.ActiveDoc


def _scale(doc):
    return Rhino.RhinoMath.UnitScale(doc.ModelUnitSystem, Rhino.UnitSystem.Millimeters)


def _usertext(obj):
    keys = obj.Attributes.GetUserStrings()
    out = {}
    for k in keys.AllKeys:
        v = keys[k]
        if k in NUMERIC:
            try:
                v = float(v)
            except ValueError:
                pass
        elif k == "exit":
            v = v.strip().lower() in ("1", "true", "yes")
        out[k] = v
    return out


def _layer_type(doc, obj):
    layer = doc.Layers[obj.Attributes.LayerIndex]
    return LAYERS.get(layer.FullPath)


def _outline(curve, s):
    ok, pl = curve.TryGetPolyline()
    pts = list(pl) if ok else [curve.PointAt(t) for t in curve.DivideByCount(24, True)]
    if ok and len(pts) > 1 and pts[0].DistanceTo(pts[-1]) < 1e-6:
        pts = pts[:-1]
    return [[round(p.X * s, 1), round(p.Y * s, 1)] for p in pts]


def snapshot():
    doc = _doc()
    s = _scale(doc)
    rooms, elements, curves = [], [], {}
    for obj in doc.Objects:
        kind = _layer_type(doc, obj)
        if not kind or obj.IsDeleted:
            continue
        props = _usertext(obj)
        props.setdefault("name", obj.Attributes.Name or kind)
        geom = {}
        g = obj.Geometry
        if kind == "room" and isinstance(g, Rhino.Geometry.Curve) and g.IsClosed:
            amp = Rhino.Geometry.AreaMassProperties.Compute(g)
            props["area_m2"] = round(amp.Area * s * s / 1e6, 2) if amp else None
            geom["outline"] = _outline(g, s)
            if "clear_width_mm" not in props:
                bb = g.GetBoundingBox(True)
                props["clear_width_mm"] = round(min(bb.Max.X - bb.Min.X, bb.Max.Y - bb.Min.Y) * s, 1)
            curves[str(obj.Id)] = g
        elif kind == "wall" and isinstance(g, Rhino.Geometry.Curve):
            props["length_mm"] = round(g.GetLength() * s, 1)
            geom["start"] = [g.PointAtStart.X * s, g.PointAtStart.Y * s]
            geom["end"] = [g.PointAtEnd.X * s, g.PointAtEnd.Y * s]
        else:
            if isinstance(g, Rhino.Geometry.InstanceReferenceGeometry):
                x = g.Xform  # insertion point = translation part of the block transform
                p = Rhino.Geometry.Point3d(x.M03, x.M13, x.M23)
            else:
                p = g.GetBoundingBox(True).Center
            geom["location"] = [round(p.X * s, 1), round(p.Y * s, 1)]
            geom["_pt"] = p
        el = {"id": str(obj.Id), "type": kind, "props": props, "geom": geom}
        (rooms if kind == "room" else elements).append(el)
    # Doors that don't list their rooms: any room whose boundary passes within 300 mm.
    tol = 300.0 / s
    for el in elements:
        pt = el["geom"].pop("_pt", None)
        if el["type"] == "door" and pt is not None:
            if el["props"].get("rooms"):
                el["props"]["rooms"] = [r.strip() for r in str(el["props"]["rooms"]).split(",") if r.strip()]
            else:
                near = []
                for rid, c in curves.items():
                    ok, t = c.ClosestPoint(pt)
                    if ok and c.PointAt(t).DistanceTo(pt) <= tol:
                        near.append(rid)
                el["props"]["rooms"] = near
    return rooms + elements


def _obj(eid):
    obj = _doc().Objects.FindId(System.Guid(eid))
    if obj is None or obj.IsDeleted:
        raise KeyError(eid)
    return obj


def get(eid, prop):
    return _usertext(_obj(eid)).get(prop)


def set_(eid, prop, value):
    doc = _doc()
    obj = _obj(eid)
    old = _usertext(obj).get(prop)
    attrs = obj.Attributes.Duplicate()
    attrs.SetUserString(prop, str(value))
    if prop == "name":
        attrs.Name = str(value)
    doc.Objects.ModifyAttributes(obj, attrs, True)
    # Door width also changes the door's geometry: scale the block along its own X axis.
    if prop == "clear_width_mm" and isinstance(obj.Geometry, Rhino.Geometry.InstanceReferenceGeometry) and old:
        x = obj.Geometry.Xform
        origin = Rhino.Geometry.Point3d(x.M03, x.M13, x.M23)
        axis_x = Rhino.Geometry.Vector3d(x.M00, x.M10, x.M20)
        axis_y = Rhino.Geometry.Vector3d(x.M01, x.M11, x.M21)
        plane = Rhino.Geometry.Plane(origin, axis_x, axis_y)
        scale = Rhino.Geometry.Transform.Scale(plane, float(value) / float(old), 1.0, 1.0)
        doc.Objects.Transform(obj.Id, scale, True)


class Undo:
    def __init__(self):
        self.serial = None

    def begin(self, title):
        self.serial = _doc().BeginUndoRecord("Lintel: " + title)

    def commit(self):
        _doc().EndUndoRecord(self.serial)
        _doc().Views.Redraw()

    def rollback(self):
        _doc().EndUndoRecord(self.serial)
        _doc().Undo()


def project_id(doc):
    pid = doc.Strings.GetValue("lintel_project")
    if not pid:
        base = os.path.splitext(doc.Name or "untitled")[0].lower().replace(" ", "-")
        pid = "%s-%s" % (base, str(System.Guid.NewGuid())[:6])
        doc.Strings.SetString("lintel_project", pid)
    return pid


class Session:
    def __init__(self):
        doc = _doc()
        self.client = lintel_client.Client(project_id(doc), "rhino8", doc.Name or "Untitled Rhino model")
        self.undo = Undo()
        self.watch = lintel_client.Watcher(self.client, snapshot, get, set_, begin=self.undo.begin,
                                           commit=self.undo.commit, rollback=self.undo.rollback)
        self.last = 0.0
        self.form = None

    def on_idle(self, sender, e):
        if time.time() - self.last < POLL_SECONDS:
            return
        self.last = time.time()
        first = self.watch.known is None
        try:
            applied, new = self.watch.tick()
        except Exception as ex:  # server down: keep Rhino responsive, retry later
            self.last = time.time() + 10
            Rhino.RhinoApp.WriteLine("Lintel: sync failed (%s); retrying" % ex)
            return
        for cid, ok, err in applied:
            Rhino.RhinoApp.WriteLine("Lintel: %s %s %s" % ("applied" if ok else "refused", cid, err or ""))
        if first:
            Rhino.RhinoApp.WriteLine("Lintel: watching. %d open issue%s." % (self.watch.count, "" if self.watch.count == 1 else "s"))
        for i in new[:5]:
            Rhino.RhinoApp.WriteLine("Lintel %s %s (%s) %s" % ("!" if i["severity"] == "error" else "?", i["message"],
                                                             i["element_name"], i["ref"]))
        if len(new) > 5:
            Rhino.RhinoApp.WriteLine("Lintel: and %d more. Open the Lintel window (Ctrl+Shift+L)." % (len(new) - 5))
        if self.form:
            self.form.Title = "Lintel · %d issue%s" % (self.watch.count, "" if self.watch.count == 1 else "s")

    def open_window(self):
        import Eto.Forms as forms
        import Eto.Drawing as drawing
        form = forms.Form()
        form.Title = "Lintel"
        form.ClientSize = drawing.Size(420, 720)
        form.Topmost = True
        view = forms.WebView()
        view.Url = System.Uri("%s/?panel=%s" % (self.client.url, self.client.project))
        form.Content = view
        form.Owner = Rhino.UI.RhinoEtoApp.MainWindow
        form.Show()
        self.form = form


def register_hotkey():
    """A `Lintel` alias for this script, and Ctrl+Shift+L for it unless that key is already taken."""
    macro = '_-RunPythonScript "%s"' % os.path.abspath(__file__)
    aliases = Rhino.ApplicationSettings.CommandAliasList
    if not aliases.IsAlias("Lintel"):
        aliases.Add("Lintel", macro)
    keys = Rhino.ApplicationSettings.ShortcutKeySettings
    for name in ("CtrlShiftL", "ShiftCtrlL"):  # the enum name differs between Rhino builds
        key = getattr(Rhino.ApplicationSettings.ShortcutKey, name, None)
        if key is not None:
            if not keys.GetMacro(key):
                keys.SetMacro(key, "Lintel")
            return


def main():
    state = sc.sticky.get(STICKY)
    if state:
        Rhino.RhinoApp.Idle -= state.on_idle
        if state.form:
            state.form.Close()
        sc.sticky.pop(STICKY)
        Rhino.RhinoApp.WriteLine("Lintel disconnected.")
        return
    session = Session()
    register_hotkey()
    Rhino.RhinoApp.Idle += session.on_idle
    sc.sticky[STICKY] = session
    session.open_window()
    Rhino.RhinoApp.WriteLine("Lintel connected: project %s. Run again to disconnect." % session.client.project)


if __name__ == "__main__":
    main()
