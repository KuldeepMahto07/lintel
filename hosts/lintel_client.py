"""Host-side client for the Lintel plugin protocol. Standard library only, so it runs inside
Rhino 8's Python 3, Vectorworks' Python 3, plain CPython (ArchiCAD, AutoCAD) and pyRevit's
IronPython 2.7 (Revit, which passes its own .NET transport).

A host adapter supplies three callables:
  snapshot()            -> list of elements {id, type, props, geom}
  get(element, prop)    -> current value, or raises KeyError
  set(element, prop, v) -> writes the value into the model
and optionally begin()/commit()/rollback() to wrap a change set in one undo step.
"""
import hashlib
import json
import os
import time

try:  # Python 3
    from urllib.error import HTTPError
    from urllib.parse import quote
    from urllib.request import Request, urlopen
except ImportError:  # IronPython 2.7 (pyRevit)
    from urllib import quote
    from urllib2 import HTTPError, Request, urlopen

CONFIG = os.path.join(os.path.expanduser("~"), ".lintel", "config.json")


def _config():
    """~/.lintel/config.json: {"url": "https://...", "token": "lnt_..."}, shared by every CAD app on this computer."""
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except (IOError, OSError, ValueError):
        return {}


DEFAULT_URL = os.environ.get("LINTEL_URL") or _config().get("url") or "http://127.0.0.1:8002"


class LintelHttpError(Exception):
    def __init__(self, code, body=""):
        Exception.__init__(self, "Lintel answered HTTP %s %s" % (code, body[:200]))
        self.code = code


def urllib_transport(method, url, headers, data):
    """(method, url, headers, body bytes or None) -> response bytes; raises LintelHttpError."""
    req = Request(url, data=data, headers=headers)
    req.get_method = lambda: method
    try:
        r = urlopen(req, timeout=15)
        try:
            return r.read()
        finally:
            r.close()
    except HTTPError as e:
        raise LintelHttpError(e.code, e.read().decode("utf-8", "replace"))


def read_token(data_dir=None):
    """Your personal plugin token (Lintel > Settings > Plugins): LINTEL_TOKEN, ~/.lintel/config.json,
    or saved in data/plugin-token.txt."""
    if os.environ.get("LINTEL_TOKEN"):
        return os.environ["LINTEL_TOKEN"]
    if _config().get("token"):
        return _config()["token"]
    data_dir = data_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    path = os.path.join(data_dir, "plugin-token.txt")
    if not os.path.exists(path):
        raise RuntimeError("No Lintel plugin token. Create one in Lintel > Settings > Plugins, then set LINTEL_TOKEN "
                           "or save it in " + path)
    with open(path) as f:
        return f.read().strip()


class Client:
    def __init__(self, project, host, name=None, url=DEFAULT_URL, token=None, transport=None):
        self.project, self.host, self.name = project, host, name or project
        self.url, self.token = url.rstrip("/"), token or read_token()
        self.transport = transport or urllib_transport

    def _req(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        out = self.transport(method, self.url + path,
                             {"Content-Type": "application/json", "Authorization": "Bearer " + self.token}, data)
        if isinstance(out, bytes):
            out = out.decode("utf-8")
        return json.loads(out) if out else None

    def push_snapshot(self, elements):
        return self._req("POST", "/api/plugin/snapshot",
                         {"project": self.project, "name": self.name, "host": self.host, "elements": elements})

    def pending(self):
        try:
            return self._req("GET", "/api/plugin/pending?project=" + quote(self.project))
        except LintelHttpError as e:
            if e.code == 404:  # first sync: the snapshot pushed after this creates the project
                return []
            raise

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


class Watcher:
    """Live checking for any host: call tick() often (every second or two, from the host's idle loop).

    It applies approved change sets, pushes the model only when it changed (or every `keepalive`
    seconds so the dashboard knows the plugin is connected) and returns the issues that are new
    since the last sync, so the host can speak up once instead of repeating itself.
    """

    def __init__(self, client, snapshot, get, set_, keepalive=30.0, **undo):
        self.client, self.snapshot, self.get, self.set_, self.undo = client, snapshot, get, set_, undo
        self.keepalive, self.digest, self.pushed_at, self.known, self.count = keepalive, None, 0.0, None, 0

    def tick(self):
        applied = []
        for cs in self.client.pending():
            ok, err = apply_changeset(cs, self.get, self.set_, **self.undo)
            self.client.report(cs["id"], ok, err)
            applied.append((cs["id"], ok, err))
        elements = self.snapshot()
        digest = hashlib.sha1(json.dumps(elements, sort_keys=True, default=str).encode()).hexdigest()
        if digest == self.digest and not applied and time.time() - self.pushed_at < self.keepalive:
            return applied, []
        out = self.client.push_snapshot(elements) or {}
        self.digest, self.pushed_at = digest, time.time()
        items = out.get("items") or []
        self.count = out.get("issues", len(items))
        ids = set(i["id"] for i in items)
        new = [] if self.known is None else [i for i in items if i["id"] not in self.known]
        self.known = ids
        return applied, new
