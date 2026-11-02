"""Factories for tests: a fresh database per test, users that carry their own cookies and CSRF token."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = json.loads((ROOT / "samples" / "clinic.json").read_text())
PASSWORD = "correct horse battery"


class User:
    """One browser: its own cookie jar; sends the CSRF header on writes."""

    def __init__(self, app):
        self.c = TestClient(app)
        self.csrf = ""
        self.me = None

    def refresh(self):
        r = self.c.get("/api/me")
        if r.status_code == 200:
            self.me = r.json()
            self.csrf = self.me["csrf"]
        return r

    def _h(self, kw):
        kw.setdefault("headers", {})["X-CSRF-Token"] = self.csrf
        return kw

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, **kw):
        return self.c.post(url, **self._h(kw))

    def patch(self, url, **kw):
        return self.c.patch(url, **self._h(kw))

    def put(self, url, **kw):
        return self.c.put(url, **self._h(kw))

    def delete(self, url, **kw):
        return self.c.request("DELETE", url, **self._h(kw))

    @property
    def fid(self):
        return self.me["firm"]["id"]


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for var in ("LINTEL_DEMO", "DATABASE_URL", "RESEND_API_KEY", "STRIPE_SECRET_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LINTEL_NO_RATE_LIMIT", "1")
    from backend import db
    db.reset(tmp_path / "t.db")
    from backend.app import app as fastapi_app
    yield fastapi_app
    db.reset(None)


@pytest.fixture()
def make_owner(app):
    n = [0]

    def make(firm="Studio North", name="Ana"):
        n[0] += 1
        u = User(app)
        r = u.c.post("/api/auth/signup", json={"name": name, "email": f"{name.lower()}{n[0]}@firm{n[0]}.test",
                                               "password": PASSWORD, "firm_name": firm})
        assert r.status_code == 201, r.text
        u.refresh()
        return u
    return make


@pytest.fixture()
def invite(app):
    def make(owner, role, name="Ben"):
        email = f"{name.lower()}.{role}@{owner.fid}.test"
        r = owner.post("/api/invites", json={"email": email, "role": role})
        assert r.status_code == 201, r.text
        token = r.json()["link"].rsplit("/", 1)[1]
        u = User(app)
        assert u.c.post(f"/api/invites/{token}/accept", json={"name": name, "password": PASSWORD}).status_code == 200
        u.refresh()
        return u
    return make


def plugin_token(user, name="Test host"):
    r = user.post("/api/tokens", json={"name": name})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture()
def sample(make_owner):
    """An owner whose firm has the sample clinic synced through a plugin token. Returns (owner, plugin headers)."""
    owner = make_owner()
    h = plugin_token(owner)
    r = owner.c.post("/api/plugin/snapshot", json=dict(SAMPLE, host="test"), headers=h)
    assert r.status_code == 200, r.text
    return owner, h
