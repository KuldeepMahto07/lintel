"""The sample clinic and the built-in sample host.

A firm can load the sample clinic from onboarding. No CAD app is attached to it, so the
sample host plays the plugin's part: an approved change set is applied to the stored model
straight away, with the same drift guard as a real host, and logged as host:sample.
LINTEL_DEMO=1 (the public demo deployment) does the same for every project.
"""
import copy
import json
import os
from pathlib import Path

from . import store

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "clinic.json"
SAMPLE_HOST = "sample"


def enabled():
    return os.environ.get("LINTEL_DEMO") == "1"


def create_sample(c):
    model = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with store.db.tx():
        pid = store.create_project(c.fid, "Sample clinic", SAMPLE_HOST)
        store.save_snapshot(pid, SAMPLE_HOST, model["elements"])
        c.audit(pid, "project.created", pid, {"name": "Sample clinic", "sample": True})
        store.audit(c.fid, pid, "host:sample", "model.snapshot", "", {"elements": len(model["elements"])}, actor_name="Sample host")
    return pid


def apply_now(fid, cid):
    """Apply an approved change set to the latest snapshot, as a connected host would."""
    from . import service  # late import: service calls into this module
    cs = store.changeset(fid, cid)
    snap = store.latest_snapshot(cs["project_id"])
    elements = copy.deepcopy(snap["elements"]) if snap else []
    by_id = {e["id"]: e for e in elements}
    for o in cs["ops"]:
        el = by_id.get(o["element"])
        current = el and el["props"].get(o["prop"])
        if el is None or (o.get("from") is not None and str(current) != str(o["from"]) and not _close(current, o["from"])):
            service.host_result(fid, cid, False, f"{o['element']} changed since the proposal; re-run checks", SAMPLE_HOST,
                                actor_name="Sample host")
            return
    for o in cs["ops"]:
        by_id[o["element"]]["props"][o["prop"]] = o["to"]
    store.save_snapshot(cs["project_id"], SAMPLE_HOST, elements)
    service.host_result(fid, cid, True, None, SAMPLE_HOST, actor_name="Sample host")


def _close(a, b):
    try:
        return abs(float(a) - float(b)) < 0.05
    except (TypeError, ValueError):
        return False
