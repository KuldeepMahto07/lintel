# Lintel CAD plugins

Every plugin talks to Lintel over the same small protocol (`lintel_client.py`): it sends the model's
rooms, doors, stairs and walls, applies change sets an approver signed off (all or nothing, refused if
the model changed since), and reports the result. Nothing is written into a model without approval.

## Set up once per computer

Create a personal token in Lintel › Settings › Plugins, then save `~/.lintel/config.json`:

```json
{"url": "https://lintel-arc-4icn.vercel.app", "token": "lnt_..."}
```

(`LINTEL_URL` and `LINTEL_TOKEN` environment variables work too.)

## Apps

| App | Status | Start it | Live checks | Applies |
|---|---|---|---|---|
| Rhino 8 | current host | `_-RunPythonScript hosts/rhino/lintel_rhino.py`, then **Ctrl+Shift+L** | every 2 s | door width, stairs, names |
| Revit 2022+ | beta | pyRevit: add `hosts/revit` as a custom extension folder, then the **Lintel** button | every 2 s | door width (by type), stairs, names |
| Archicad 25+ | beta | `pip install archicad`, then `python hosts/archicad/lintel_archicad.py --watch` | every 2 s | zone names and "Lintel Use" only (the API can't edit geometry) |
| SketchUp 2020+ | beta | copy `hosts/sketchup/*` into SketchUp's Plugins folder, then Extensions › Lintel | every 2 s | door width, stair attributes, names |
| AutoCAD 2018+ (Windows) | beta | `pip install pywin32`, then `python hosts/autocad/lintel_autocad.py --watch` | every 2 s | door width, stair attributes, room labels |
| Vectorworks 2021+ | beta | a "Lintel Sync" menu command (see the top of `vectorworks/lintel_vectorworks.py`) | each time you run it | door width, stair fields, names |

**Beta** means the adapter is written against the app's published API but hasn't yet been run
inside that app by us. Expect rough edges and tell us what breaks.

How each app's objects map to rooms, doors and stairs (layers, tags, classes or native BIM objects)
is described at the top of each adapter file. `fixture_host.py` plays a CAD app from a JSON model
for tests and demos.
