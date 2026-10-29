"""Host-side client for the Lintel plugin protocol. Standard library only, so it runs
inside Rhino 8's Python 3 as well as plain CPython.

A host adapter supplies three callables:
  snapshot()            -> list of elements {id, type, props, geom}
  get(element, prop)    -> current value, or raises KeyError
  set(element, prop, v) -> writes the value into the model
and optionally begin()/commit()/rollback() to wrap a change set in one undo step.
"""
import json
import os
import urllib.parse
import urllib.request

DEFAULT_URL = os.environ.get("LINTEL_URL", "http://127.0.0.1:8002")


def read_token(data_dir=None):
    if os.environ.get("LINTEL_TOKEN"):
        return os.environ["LINTEL_TOKEN"]
    data_dir = data_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    with open(os.path.join(data_dir, "plugin-token.txt")) as f:
        return f.read().strip()


class Client:
    def __init__(self, project, host, name=None, url=DEFAULT_URL, token=None):
        self.project, self.host, self.name = project, host, name or project
        self.url, self.token = url.rstrip("/"), token or read_token()

    def _req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "X-Lintel-Token": self.token})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or b"null")

    def push_snapshot(self, elements):
        return self._req("POST", "/api/plugin/snapshot",
                         {"project": self.project, "name": self.name, "host": self.host, "elements": elements})

    def pending(self):
        return self._req("GET", "/api/plugin/pending?project=" + urllib.parse.quote(self.project))

    def report(self, changeset_id, ok, error=None):
        return self._req("POST", "/api/plugin/result",
                         {"changeset": changeset_id, "ok": ok, "error": error, "host": self.host})


def same(a, b):
    try:
        return abs(float(a) - float(b)) < 0.05
    except (TypeError, ValueError):
        return a == b


def apply_changeset(cs, get, set_, begin=None, commit=None, rollback=None):
    """Apply every op or none. Refuses if the model drifted since the proposal."""
    for o in cs["ops"]:
        try:
            current = get(o["element"], o["prop"])
        except KeyError:
            return False, "element %s no longer exists" % o["element"]
        if o.get("from") is not None and not same(current, o["from"]):
            return False, "%s.%s is now %s, expected %s; re-run checks" % (o["element"], o["prop"], current, o["from"])
    if begin:
        begin(cs["title"])
    try:
        for o in cs["ops"]:
            set_(o["element"], o["prop"], o["to"])
    except Exception as e:  # host API errors: undo whatever was written
        if rollback:
            rollback()
        return False, "host error: %s" % e
    if commit:
        commit()
    return True, None


def sync_once(client, snapshot, get, set_, **undo):
    """One poll cycle: apply approved change sets, report, then push a fresh snapshot."""
    applied = []
    for cs in client.pending():
        ok, err = apply_changeset(cs, get, set_, **undo)
        client.report(cs["id"], ok, err)
        applied.append((cs["id"], ok, err))
    client.push_snapshot(snapshot())
    return applied
