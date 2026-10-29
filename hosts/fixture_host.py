"""Fixture host: plays the part of a CAD app using a JSON model file, over the same
plugin protocol as the Rhino plugin. Used for tests and demos when no CAD app is installed.

    python hosts/fixture_host.py samples/clinic.json            # push model, apply approved changes, exit
    python hosts/fixture_host.py samples/clinic.json --watch    # keep polling every 2 s

It edits a working copy in data/fixture-<project>.json, never the sample itself.
"""
import argparse
import copy
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lintel_client import Client, sync_once  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FixtureHost:
    def __init__(self, model_path, url=None, token=None, fresh=False):
        with open(model_path, encoding="utf-8") as f:
            sample = json.load(f)
        self.path = os.path.join(ROOT, "data", "fixture-%s.json" % sample["project"])
        if fresh or not os.path.exists(self.path):
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            shutil.copy(model_path, self.path)
        with open(self.path, encoding="utf-8") as f:
            self.model = json.load(f)
        kw = {"url": url} if url else {}
        self.client = Client(self.model["project"], "fixture", self.model["name"], token=token, **kw)
        self.undo = []

    def _el(self, eid):
        for e in self.model["elements"]:
            if e["id"] == eid:
                return e
        raise KeyError(eid)

    def snapshot(self):
        return copy.deepcopy(self.model["elements"])

    def get(self, eid, prop):
        return self._el(eid)["props"].get(prop)

    def set(self, eid, prop, value):
        self._el(eid)["props"][prop] = value

    # one undo record per change set, like Rhino's BeginUndoRecord/EndUndoRecord
    def begin(self, title):
        self.undo.append(copy.deepcopy(self.model))

    def commit(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.model, f, indent=1)

    def rollback(self):
        self.model = self.undo.pop()

    def sync(self):
        return sync_once(self.client, self.snapshot, self.get, self.set,
                         begin=self.begin, commit=self.commit, rollback=self.rollback)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="start again from the sample file")
    args = ap.parse_args()
    host = FixtureHost(args.model, fresh=args.fresh)
    while True:
        try:
            for cid, ok, err in host.sync():
                print("applied" if ok else "refused", cid, err or "")
        except OSError as e:  # server restarting: keep watching
            if not args.watch:
                raise
            print("Lintel unreachable (%s); retrying" % e)
        if not args.watch:
            print("snapshot pushed for", host.model["project"])
            break
        time.sleep(2)


if __name__ == "__main__":
    main()
