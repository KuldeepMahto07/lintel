# -*- coding: utf-8 -*-
"""Lintel for Revit (2022 and later), run through pyRevit's IronPython engine.

Install: add hosts/revit/Lintel.extension to pyRevit (pyRevit > Settings > Custom extension
directories > add the hosts/revit folder, then Reload). A Lintel tab appears with one button:
click it to connect the open model and open Lintel in your browser; click again to disconnect.
Assign it a keyboard shortcut in Revit (View > User Interface > Keyboard Shortcuts, search "Lintel").

Revit is a BIM app, so Lintel reads its native objects:
  Rooms   placed rooms: name, number, area, boundary. Use comes from a "Lintel Use" text
          parameter if the project has one, otherwise from the room name ("Corridor 2" -> corridor).
  Doors   door instances: width (or a "Lintel Clear Width" length parameter), the rooms on each
          side, and exit = a "Lintel Exit" yes/no parameter, otherwise a door with no room on one side.
  Stairs  stairs: actual riser height, tread depth, number of risers, run width, total height.
  Walls   wall location lines and thickness.
Element ids are Revit UniqueIds.

Approved change sets run inside one Revit transaction group, so one Ctrl+Z undoes a Lintel edit.
A door width change swaps the door to a type of that width in the same family (making the type
if needed); it never edits a type other doors share. Stair edits go through a StairsEditScope.
Revit only allows model edits inside its API context, so the sync runs as an ExternalEvent raised
by a two-second timer on Revit's UI thread.
"""
import os
import sys

import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System.Windows.Forms")
import System  # noqa: E402
from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter, FailureProcessingResult,  # noqa: E402
                               FilteredElementCollector, IFailuresPreprocessor, SpatialElementBoundaryOptions,
                               StorageType, Transaction, TransactionGroup)
from Autodesk.Revit.DB.Architecture import Room, Stairs, StairsEditScope  # noqa: E402
from Autodesk.Revit.UI import ExternalEvent, IExternalEventHandler  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # hosts/ for lintel_client and common
import common  # noqa: E402
import lintel_client  # noqa: E402

FT = 304.8          # Revit stores lengths in feet
FT2 = 0.09290304    # and areas in square feet
KEY = "lintel_revit_session"


# ---- HTTP through .NET (IronPython's own TLS support is unreliable) --------

def net_transport(method, url, headers, data):
    from System.IO import StreamReader
    from System.Net import SecurityProtocolType, ServicePointManager, WebClient, WebException
    ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12
    wc = WebClient()
    wc.Encoding = System.Text.Encoding.UTF8
    for k, v in headers.items():
        wc.Headers.Add(k, v)
    try:
        if method == "GET":
            return wc.DownloadString(url)
        return wc.UploadString(url, method, data.decode("utf-8") if data else "")
    except WebException as e:
        if e.Response is None:
            raise
        body = StreamReader(e.Response.GetResponseStream()).ReadToEnd()
        raise lintel_client.LintelHttpError(int(e.Response.StatusCode), body)


# ---- reading the model -----------------------------------------------------

def _p(el, name):
    p = el.LookupParameter(name)
    return p if p is not None and p.HasValue else None


def _xy(pt):
    return [pt.X * FT, pt.Y * FT]


def _collect(doc, cat):
    return FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements()


def _door_width_param(el):
    p = el.get_Parameter(BuiltInParameter.DOOR_WIDTH)
    return p if p is not None else el.Symbol.get_Parameter(BuiltInParameter.DOOR_WIDTH)


def _door_name(el):
    mark = el.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    mark = mark.AsString() if mark is not None else None
    return mark or "%s %s" % (el.Symbol.FamilyName, el.Symbol.Name)


def _clear_width(el):
    p = _p(el, "Lintel Clear Width")
    if p is not None and p.StorageType == StorageType.Double:
        return p.AsDouble() * FT
    w = _door_width_param(el)
    return w.AsDouble() * FT if w is not None else 0.0


def _room(r, opts):
    loops = r.GetBoundarySegments(opts)
    pts = [_xy(seg.GetCurve().GetEndPoint(0)) for seg in loops[0]] if loops and loops.Count else []
    name = r.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() or r.Number
    use = _p(r, "Lintel Use")
    return common.room(r.UniqueId, name, pts, use=use.AsString().lower() if use else None, area_m2=r.Area * FT2,
                       number=r.Number, level=r.Level.Name if r.Level else None)


def _door(d):
    sides = [x for x in (d.FromRoom, d.ToRoom) if x is not None]
    flag = _p(d, "Lintel Exit")
    exit_ = (flag.AsInteger() == 1) if flag is not None else len(sides) < 2
    return common.door(d.UniqueId, _door_name(d), _xy(d.Location.Point), _clear_width(d), exit=exit_,
                       rooms=[x.UniqueId for x in sides])


def _stair(doc, s):
    runs = [doc.GetElement(i) for i in s.GetStairsRuns()]
    bb = s.get_BoundingBox(None)
    c = (bb.Min + bb.Max) / 2 if bb else None
    return common.stair(s.UniqueId, s.Name, _xy(c) if c else [0, 0], riser_mm=s.ActualRiserHeight * FT,
                        tread_mm=s.ActualTreadDepth * FT, risers=s.ActualRisersNumber,
                        width_mm=min(r.ActualRunWidth for r in runs) * FT if runs else None, total_rise_mm=s.Height * FT)


def snapshot(doc):
    out = []
    opts = SpatialElementBoundaryOptions()
    for r in _collect(doc, BuiltInCategory.OST_Rooms):
        if r.Area:  # skip unplaced or unenclosed rooms
            out.append(_room(r, opts))
    for d in _collect(doc, BuiltInCategory.OST_Doors):
        if d.Location is not None and hasattr(d.Location, "Point"):
            out.append(_door(d))
    for s in _collect(doc, BuiltInCategory.OST_Stairs):
        if isinstance(s, Stairs):
            out.append(_stair(doc, s))
    for w in _collect(doc, BuiltInCategory.OST_Walls):
        lc = getattr(w, "Location", None)
        if lc is not None and hasattr(lc, "Curve"):
            out.append(common.wall(w.UniqueId, _xy(lc.Curve.GetEndPoint(0)), _xy(lc.Curve.GetEndPoint(1)),
                                   thickness_mm=w.Width * FT))
    return out


# ---- writing approved changes ----------------------------------------------

class _Continue(IFailuresPreprocessor):
    def PreprocessFailures(self, accessor):
        return FailureProcessingResult.Continue


def _element(doc, eid):
    el = doc.GetElement(eid)
    if el is None:
        raise KeyError(eid)
    return el


def get(doc, eid, prop):
    el = _element(doc, eid)
    if isinstance(el, Room):
        e = _room(el, SpatialElementBoundaryOptions())
    elif isinstance(el, Stairs):
        e = _stair(doc, el)
    else:
        e = _door(el)
    if prop not in e["props"]:
        raise KeyError(prop)
    return e["props"][prop]


def _door_type(doc, el, width_mm):
    """A door type of the requested width in the same family, made by duplicating if none exists."""
    for sid in el.Symbol.Family.GetFamilySymbolIds():
        sym = doc.GetElement(sid)
        w = sym.get_Parameter(BuiltInParameter.DOOR_WIDTH)
        if w is not None and abs(w.AsDouble() * FT - width_mm) < 1.0:
            return sym
    new = el.Symbol.Duplicate("%s %d mm" % (el.Symbol.Name, int(round(width_mm))))
    new.get_Parameter(BuiltInParameter.DOOR_WIDTH).Set(width_mm / FT)
    return new


def set_(doc, eid, prop, value):
    el = _element(doc, eid)
    if isinstance(el, Stairs):
        return _set_stair(doc, el, prop, float(value))
    t = Transaction(doc, "Lintel: %s" % prop)
    t.Start()
    try:
        if prop == "name" and isinstance(el, Room):
            el.get_Parameter(BuiltInParameter.ROOM_NAME).Set(str(value))
        elif prop == "use":
            p = el.LookupParameter("Lintel Use")
            if p is None:
                raise ValueError('add a text parameter "Lintel Use" to rooms to let Lintel set the use')
            p.Set(str(value))
        elif prop == "name":
            el.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).Set(str(value))
        elif prop == "clear_width_mm":
            new = float(value)
            clear = _p(el, "Lintel Clear Width")
            nominal = _door_width_param(el).AsDouble() * FT
            target = nominal + (new - _clear_width(el)) if clear is not None else new
            inst = el.get_Parameter(BuiltInParameter.DOOR_WIDTH)
            if inst is not None and not inst.IsReadOnly:
                inst.Set(target / FT)  # width is an instance parameter in this family
            else:
                el.Symbol = _door_type(doc, el, target)
            if clear is not None:
                clear.Set(new / FT)
        else:
            raise ValueError("Lintel can't change %s in Revit" % prop)
        t.Commit()
    except Exception:
        t.RollBack()
        raise


def _set_stair(doc, st, prop, value):
    scope = StairsEditScope(doc, "Lintel stair")
    scope.Start(st.Id)
    t = Transaction(doc, "Lintel: stair %s" % prop)
    t.Start()
    try:
        if prop == "risers":
            st.DesiredRisersNumber = int(value)
        elif prop == "riser_mm":
            st.DesiredRisersNumber = common.risers_for(st.Height * FT, value)
        elif prop == "tread_mm":
            st.ActualTreadDepth = value / FT
        elif prop == "width_mm":
            for rid in st.GetStairsRuns():
                doc.GetElement(rid).ActualRunWidth = value / FT
        else:
            raise ValueError("Lintel can't change stair %s in Revit" % prop)
        t.Commit()
        scope.Commit(_Continue())
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        scope.Cancel()
        raise


class Undo(object):
    """One transaction group per change set: Revit's undo list shows a single "Lintel: ..." entry."""

    def __init__(self, doc):
        self.doc, self.group = doc, None

    def begin(self, title):
        self.group = TransactionGroup(self.doc, "Lintel: " + title)
        self.group.Start()

    def commit(self):
        self.group.Assimilate()

    def rollback(self):
        self.group.RollBack()


# ---- the session -----------------------------------------------------------

def project_id(doc):
    base = "".join(ch if ch.isalnum() else "-" for ch in (doc.Title or "revit").lower()).strip("-")
    return "revit-%s-%s" % (base, doc.ProjectInformation.UniqueId[-6:])


class Handler(IExternalEventHandler):
    def __init__(self, session):
        self.session = session

    def Execute(self, uiapp):
        self.session.tick()

    def GetName(self):
        return "Lintel sync"


class Session(object):
    def __init__(self, uiapp):
        doc = uiapp.ActiveUIDocument.Document
        self.doc = doc
        self.client = lintel_client.Client(project_id(doc), "revit", doc.Title, transport=net_transport)
        undo = Undo(doc)
        self.watch = lintel_client.Watcher(self.client, lambda: snapshot(doc), lambda e, p: get(doc, e, p),
                                           lambda e, p, v: set_(doc, e, p, v), begin=undo.begin, commit=undo.commit,
                                           rollback=undo.rollback)
        self.event = ExternalEvent.Create(Handler(self))
        self.timer = System.Windows.Forms.Timer()
        self.timer.Interval = 2000
        self.timer.Tick += lambda s, e: self.event.Raise()

    def tick(self):
        first = self.watch.known is None
        try:
            applied, new = self.watch.tick()
        except Exception as ex:  # server unreachable: keep Revit responsive and try again on the next tick
            print("Lintel: sync failed (%s); retrying" % ex)
            return
        for cid, ok, err in applied:
            print("Lintel: %s %s %s" % ("applied" if ok else "refused", cid, err or ""))
        if first:
            print("Lintel: watching %s. %d open issues." % (self.doc.Title, self.watch.count))
        for i in new[:5]:
            print("Lintel: %s (%s) %s" % (i["message"], i["element_name"], i["ref"]))

    def start(self):
        self.timer.Start()
        self.event.Raise()
        System.Diagnostics.Process.Start("%s/app/p/%s" % (self.client.url, self.client.project))

    def stop(self):
        self.timer.Stop()
        self.event.Dispose()


def toggle(uiapp):
    domain = System.AppDomain.CurrentDomain
    session = domain.GetData(KEY)
    if session is not None:
        session.stop()
        domain.SetData(KEY, None)
        print("Lintel disconnected.")
        return
    session = Session(uiapp)
    domain.SetData(KEY, session)
    session.start()
    print("Lintel connected: project %s. Click Lintel again to disconnect." % session.client.project)
