"""Message top-ups, live sync deltas, learned standards, Enterprise (SSO, staff terms, custom limits), host helpers."""
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from conftest import PASSWORD, User, plugin_token

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hosts"))


def _webhook(owner, monkeypatch, ev):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    body = json.dumps(ev).encode()
    t = str(int(time.time()))
    sig = hmac.new(b"whsec_test", f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return owner.c.post("/api/billing/webhook", content=body, headers={"Stripe-Signature": f"t={t},v1={sig}"})


def _staff(owner, monkeypatch, body):
    monkeypatch.setenv("LINTEL_STAFF_TOKEN", "staff-secret")
    return owner.c.patch(f"/api/staff/firms/{owner.fid}", json=body, headers={"x-staff-token": "staff-secret"})


# ---- message top-ups and the 80% notice ------------------------------------

def test_topup_adds_messages_for_this_month(sample, monkeypatch):
    owner, _ = sample
    cap = owner.refresh().json()["usage"]["chat_cap"]
    assert owner.me["usage"]["warn_at"] == 0.8
    assert owner.post("/api/billing/topup").json()["error"]["code"] == "billing_unavailable"  # no Stripe key here
    ev = {"id": "evt_top", "type": "checkout.session.completed",
          "data": {"object": {"payment_status": "paid", "client_reference_id": owner.fid,
                              "metadata": {"firm_id": owner.fid, "kind": "topup", "messages": "500"}}}}
    assert _webhook(owner, monkeypatch, ev).json() == {"ok": True}
    assert _webhook(owner, monkeypatch, ev).json()["duplicate"]
    me = owner.refresh().json()
    assert me["usage"]["chat_cap"] == cap + 500 and me["usage"]["topup_messages"] == 500
    assert me["firm"]["plan"] == "pro"  # a top-up never changes the plan
    assert any(a["action"] == "billing.topup" for a in owner.get("/api/audit").json()["entries"])


def test_unpaid_topup_adds_nothing_and_free_cannot_buy(sample, monkeypatch):
    owner, _ = sample
    cap = owner.refresh().json()["usage"]["chat_cap"]
    ev = {"id": "evt_unpaid", "type": "checkout.session.completed",
          "data": {"object": {"payment_status": "unpaid", "metadata": {"firm_id": owner.fid, "kind": "topup"}}}}
    _webhook(owner, monkeypatch, ev)
    assert owner.refresh().json()["usage"]["chat_cap"] == cap
    _staff(owner, monkeypatch, {"plan": "free"})
    r = owner.post("/api/billing/topup")
    assert r.status_code == 402 and r.json()["error"]["limit"] == "topup"


# ---- live sync: issue deltas for hosts --------------------------------------

def test_snapshot_returns_issue_items(sample):
    from conftest import SAMPLE
    owner, h = sample
    out = owner.c.post("/api/plugin/snapshot", json=dict(SAMPLE, host="test"), headers=h).json()
    assert out["issues"] == len(out["items"]) and out["items"]
    assert {"id", "message", "element_name", "severity", "ref"} <= set(out["items"][0])


def test_watcher_pushes_only_on_change_and_reports_new_issues():
    import lintel_client

    class Fake:
        url, project = "http://x", "p"

        def __init__(self):
            self.pushes, self.issues = 0, [{"id": "a"}]

        def pending(self):
            return []

        def push_snapshot(self, els):
            self.pushes += 1
            return {"issues": len(self.issues), "items": self.issues}

    model = [{"id": "D1", "type": "door", "props": {"clear_width_mm": 900}, "geom": {}}]
    fake = Fake()
    w = lintel_client.Watcher(fake, lambda: model, None, None)
    assert w.tick() == ([], []) and fake.pushes == 1 and w.count == 1  # first sync: no "new" spam
    assert w.tick() == ([], []) and fake.pushes == 1  # unchanged model: nothing sent
    model[0]["props"]["clear_width_mm"] = 700
    fake.issues = [{"id": "a"}, {"id": "b"}]
    assert w.tick() == ([], [{"id": "b"}]) and fake.pushes == 2


# ---- learning office standards ---------------------------------------------

def _doors(n, width, start=0):
    return [{"id": f"D{start + i}", "type": "door", "props": {"name": f"D{start + i}", "clear_width_mm": width},
             "geom": {"location": [i * 1000, 0]}} for i in range(n)]


def test_learns_a_stricter_door_standard_and_respects_discard(make_owner):
    from backend import learn
    owner = make_owner()
    h = plugin_token(owner)
    els = _doors(8, 900) + _doors(1, 820, start=8)
    owner.c.post("/api/plugin/snapshot", json={"project": "studio-a", "name": "A", "host": "test", "elements": els}, headers=h)
    learn.after_sync(owner.fid, force=True)
    rule = next(r for r in owner.get("/api/rules").json() if r["id"] == "learned-door-clear-width-mm")
    assert rule["status"] == "proposed" and rule["value"] == 900 and rule["source"] == "learned"
    assert "8 of 9 doors" in rule["ref"] and "813" in rule["ref"]
    assert not any(i["rule"] == rule["id"] for i in owner.get("/api/projects/studio-a").json()["issues"])  # not active yet
    assert owner.delete(f"/api/rules/{rule['id']}").status_code == 200
    assert learn.after_sync(owner.fid, force=True) == []  # a discarded suggestion isn't offered again


def test_no_suggestion_from_few_or_looser_values(make_owner):
    from backend import learn
    owner = make_owner()
    h = plugin_token(owner)
    owner.c.post("/api/plugin/snapshot", json={"project": "b", "name": "B", "host": "test", "elements": _doors(4, 950)}, headers=h)
    assert learn.after_sync(owner.fid, force=True) == []  # too few doors
    owner.c.post("/api/plugin/snapshot", json={"project": "b", "name": "B", "host": "test", "elements": _doors(10, 815)}, headers=h)
    assert learn.after_sync(owner.fid, force=True) == []  # no stricter than the 813 mm rule


# ---- Enterprise: staff terms, custom limits, SSO ----------------------------

def test_staff_endpoint_sets_enterprise_terms(sample, monkeypatch):
    owner, _ = sample
    assert owner.c.patch(f"/api/staff/firms/{owner.fid}", json={"plan": "enterprise"}).status_code == 403
    r = _staff(owner, monkeypatch, {"plan": "enterprise", "seats": 40, "chat_cap_override": 20000, "region": "eu-west"})
    assert r.status_code == 200
    me = owner.refresh().json()
    assert me["firm"]["plan"] == "enterprise" and me["firm"]["region"] == "eu-west" and me["firm"]["limits"]["sso"]
    assert me["usage"]["chat_cap"] == 20000
    assert _staff(owner, monkeypatch, {"seats": 0}).status_code == 422


class FakeIdP:
    def __init__(self, email, verified=True):
        self.email, self.verified, self.token_calls = email, verified, []

    def __call__(self, url, data=None, headers=None):
        if url.endswith("/.well-known/openid-configuration"):
            return {"authorization_endpoint": "https://idp.test/auth", "token_endpoint": "https://idp.test/token",
                    "userinfo_endpoint": "https://idp.test/userinfo"}
        if url == "https://idp.test/token":
            self.token_calls.append(data)
            return {"access_token": "at-1"}
        if url == "https://idp.test/userinfo":
            assert headers["Authorization"] == "Bearer at-1"
            return {"email": self.email, "email_verified": self.verified, "name": "Sam Sso"}
        raise AssertionError(url)


def _enable_sso(owner, monkeypatch, required=False):
    _staff(owner, monkeypatch, {"plan": "enterprise"})
    owner.refresh()
    r = owner.put("/api/firm/sso", json={"issuer": "https://idp.test", "client_id": "lintel", "client_secret": "s3cret",
                                         "domains": "studio.test", "required": required, "default_role": "member"})
    assert r.status_code == 200, r.text
    assert r.json()["sso"]["domains"] == ["studio.test"] and "client_secret" not in r.json()["sso"]


def test_sso_needs_enterprise(sample):
    owner, _ = sample
    r = owner.put("/api/firm/sso", json={"issuer": "https://idp.test", "client_id": "x", "client_secret": "y", "domains": "a.test"})
    assert r.status_code == 402 and r.json()["error"]["limit"] == "sso"


def test_sso_sign_in_creates_member_and_session(app, sample, monkeypatch):
    from backend import sso
    owner, _ = sample
    _enable_sso(owner, monkeypatch)
    idp = FakeIdP("sam@studio.test")
    monkeypatch.setattr(sso, "fetch_json", idp)
    u = User(app)
    assert u.c.post("/api/auth/sso/start", json={"email": "x@other.test"}).status_code == 404
    url = u.c.post("/api/auth/sso/start", json={"email": "sam@studio.test"}).json()["url"]
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://idp.test/auth?") and q["code_challenge_method"] == ["S256"] and q["client_id"] == ["lintel"]
    r = u.c.get("/api/auth/sso/callback", params={"code": "c1", "state": q["state"][0]}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/app"
    assert idp.token_calls[0]["code_verifier"] and idp.token_calls[0]["client_secret"] == "s3cret"
    me = u.refresh().json()
    assert me["user"]["email"] == "sam@studio.test" and me["role"] == "member" and me["firm"]["id"] == owner.fid
    # the state is single use
    r = User(app).c.get("/api/auth/sso/callback", params={"code": "c1", "state": q["state"][0]}, follow_redirects=False)
    assert r.status_code == 303 and "sso_error" in r.headers["location"]


def test_sso_rejects_other_domains_and_unverified_email(app, sample, monkeypatch):
    from backend import sso
    owner, _ = sample
    _enable_sso(owner, monkeypatch)
    for idp in (FakeIdP("eve@evil.test"), FakeIdP("sam@studio.test", verified=False)):
        monkeypatch.setattr(sso, "fetch_json", idp)
        u = User(app)
        state = parse_qs(urlparse(u.c.post("/api/auth/sso/start", json={"email": "sam@studio.test"}).json()["url"]).query)["state"][0]
        r = u.c.get("/api/auth/sso/callback", params={"code": "c", "state": state}, follow_redirects=False)
        assert "sso_error" in r.headers["location"] and u.refresh().status_code == 401


def test_required_sso_blocks_member_passwords_but_not_owner(app, sample, invite, monkeypatch):
    owner, _ = sample
    member = invite(owner, "member", name="Mia")
    from backend import db
    db.run("update users set email=? where id=?", ("mia@studio.test", member.me["user"]["id"]))
    db.run("update users set email=? where id=?", ("boss@studio.test", owner.me["user"]["id"]))
    _enable_sso(owner, monkeypatch, required=True)
    r = User(app).c.post("/api/auth/login", json={"email": "mia@studio.test", "password": PASSWORD})
    assert r.status_code == 403 and r.json()["error"]["code"] == "sso_required"
    assert User(app).c.post("/api/auth/login", json={"email": "boss@studio.test", "password": PASSWORD}).status_code == 200


# ---- host helpers ------------------------------------------------------------

def test_common_helpers():
    import common
    r = common.room("R1", "Corridor 2", [[0, 0], [6000, 0], [6000, 1200], [0, 1200]])
    assert r["props"]["use"] == "corridor" and r["props"]["area_m2"] == 7.2 and r["props"]["clear_width_mm"] == 1200
    d = common.door("D1", "D1", [3000, 1250], 900)
    els = common.link_doors([r, d])
    assert els[1]["props"]["rooms"] == ["R1"]
    assert common.risers_for(3420, 178) == 20 and common.risers_for(3560, 178) == 20
    assert common.guess_use("Exam 1") == "exam" and common.guess_use("Plant") == ""
