"""Hosted demo mode (LINTEL_DEMO=1), used on Vercel.

A serverless deploy has no CAD app connected and a throwaway database, so demo mode
1. seeds the sample clinic when the database is empty, and
2. plays the part of the host plugin: an approved change set is applied to the stored
   model straight away (same drift guard as a real host), then logged as host:demo.
Off by default; local runs keep the real plugin flow.
"""
import copy
import json
import os
from pathlib import Path

from . import store

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "clinic.json"


def enabled():
    return os.environ.get("LINTEL_DEMO") == "1"


def seed():
    if not enabled() or store.projects():
        return
    model = json.loads(SAMPLE.read_text(encoding="utf-8"))
    store.ensure_project(model["project"], model["name"], "demo")
    store.save_snapshot(model["project"], "demo", model["elements"])
    store.audit(model["project"], "host:demo", "model.snapshot", "", {"elements": len(model["elements"])})


def apply_now(cid):
    """Apply an approved change set to the latest snapshot, as a connected host would."""
    from . import service  # late import: service calls into this module
    cs = store.changeset(cid)
    snap = store.latest_snapshot(cs["project"])
    elements = copy.deepcopy(snap["elements"]) if snap else []
    by_id = {e["id"]: e for e in elements}
    for o in cs["ops"]:
        el = by_id.get(o["element"])
        current = el and el["props"].get(o["prop"])
        if el is None or (o.get("from") is not None and str(current) != str(o["from"]) and
                          not _close(current, o["from"])):
            service.host_result(cid, False, f"{o['element']}.{o['prop']} changed since the proposal", "demo")
            return
    for o in cs["ops"]:
        by_id[o["element"]]["props"][o["prop"]] = o["to"]
    store.save_snapshot(cs["project"], "demo", elements)
    service.host_result(cid, True, None, "demo")


def _close(a, b):
    try:
        return abs(float(a) - float(b)) < 0.05
    except (TypeError, ValueError):
        return False
