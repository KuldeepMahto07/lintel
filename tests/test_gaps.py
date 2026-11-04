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


# ---- founding pilot price ---------------------------------------------------

def test_pilot_price_is_only_for_accepted_firms_and_keeps_three_seats(sample, monkeypatch):
    owner, _ = sample
    r = owner.post("/api/billing/checkout", json={"plan": "pilot"})
    assert r.status_code == 403  # not on the pilot
    assert _staff(owner, monkeypatch, {"pilot": True}).json()["pilot"] is True
    assert owner.refresh().json()["firm"]["pilot"] is True
    assert owner.post("/api/billing/checkout", json={"plan": "pilot"}).json()["error"]["code"] == "billing_unavailable"
    meta = {"firm_id": owner.fid, "plan": "pro", "pilot": "1"}
    _webhook(owner, monkeypatch, {"id": "evt_p1", "type": "checkout.session.completed",
                                  "data": {"object": {"customer": "cus_p", "metadata": meta}}})
    f = owner.refresh().json()["firm"]
    assert (f["plan"], f["seats"], f["trial_days_left"]) == ("pro", 3, None)
    _webhook(owner, monkeypatch, {"id": "evt_p2", "type": "customer.subscription.updated",
                                  "data": {"object": {"metadata": meta, "items": {"data": [{"quantity": 1}]}}}})
    assert owner.refresh().json()["firm"]["seats"] == 3  # one flat price, still three seats


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


# ---- Free plan: read-only extra projects, custom rules off ---------------------

def test_free_plan_extra_projects_are_read_only_until_one_is_archived(make_owner):
    from backend import db
    owner = make_owner()
    h = plugin_token(owner)
    from conftest import SAMPLE
    owner.c.post("/api/plugin/snapshot", json=dict(SAMPLE, host="test"), headers=h)
    second = owner.post("/api/projects", json={"name": "Second"}).json()["project"]
    db.run("update firms set trial_ends_at=? where id=?", (time.time() - 10, owner.fid))
    P = f"/api/projects/{SAMPLE['project']}"
    assert owner.get(P).json()["read_only"] is False
    assert owner.get(f"/api/projects/{second['id']}").json()["read_only"] is True
    r = owner.patch(f"/api/projects/{second['id']}", json={"name": "Renamed"})
    assert r.status_code == 402 and r.json()["error"]["limit"] == "projects_readonly"
    r = owner.c.post("/api/plugin/snapshot", json={"project": second["id"], "name": "x", "host": "test", "elements": []}, headers=h)
    assert r.status_code == 402  # a plugin can't sync into a read-only project either
    assert owner.patch(P, json={"archived": True}).status_code == 200  # archiving frees the place
    assert owner.get(f"/api/projects/{second['id']}").json()["read_only"] is False


def test_custom_rules_and_overrides_pause_on_free_and_return_on_upgrade(sample, monkeypatch):
    owner, _ = sample
    from backend import db
    P = "/api/projects/sample-clinic"
    owner.post("/api/rules", json={"name": "Wide doors", "kind": "min", "applies_to": "door", "prop": "clear_width_mm", "value": 3000})
    assert any(i["rule_name"] == "Wide doors" for i in owner.get(P).json()["issues"])
    db.run("update firms set trial_ends_at=? where id=?", (time.time() - 10, owner.fid))
    assert not any(i["rule_name"] == "Wide doors" for i in owner.get(P).json()["issues"])
    _staff(owner, monkeypatch, {"plan": "pro"})
    assert any(i["rule_name"] == "Wide doors" for i in owner.get(P).json()["issues"])


# ---- moving walls ---------------------------------------------------------------

def _sample_project(owner):
    return owner.post("/api/projects/sample").json()["project"]["id"]


def test_room_area_issue_gets_a_wall_move_that_resizes_the_room(make_owner):
    owner = make_owner()
    pid = _sample_project(owner)
    P = f"/api/projects/{pid}"
    exam = next(i for i in owner.get(P).json()["issues"] if i["element"] == "R-exam1" and i["rule"] == "firm-exam-room")
    assert exam["fixable"]
    cid = owner.post(f"{P}/issues/{exam['id']}/fix").json()["changeset"]
    cs = owner.get(f"/api/changesets/{cid}").json()
    op = cs["ops"][0]
    assert (op["element"], op["prop"], op["from"], op["to"]) == ("W-09", "offset_mm", 0, -270)
    assert "moves 270 mm north" in cs["reason"] and "10.2 → 11.01" in cs["reason"] and "Resolves" in cs["reason"]
    assert op["rooms"] == ["R-exam1"]
    assert owner.post(f"/api/changesets/{cid}/approve").json()["status"] == "applied"  # the sample host applies it
    d = owner.get(P).json()
    room = next(e for e in d["elements"] if e["id"] == "R-exam1")
    assert room["props"]["area_m2"] == 11.01 and [2000, 4670] in room["geom"]["outline"]
    assert not any(i["element"] == "R-exam1" and i["rule"] == "firm-exam-room" for i in d["issues"])
    owner.post(f"/api/changesets/{cid}/revert")
    room = next(e for e in owner.get(P).json()["elements"] if e["id"] == "R-exam1")
    assert room["props"]["area_m2"] == 10.2  # the revert moves the wall back by the same distance


def test_a_wall_move_reports_the_rooms_it_shrinks(make_owner):
    owner = make_owner()
    pid = _sample_project(owner)
    from backend import service, store
    c = type("C", (), {"fid": owner.fid, "uid": owner.me["user"]["id"], "audit": lambda *a, **k: None})()
    cid = service.propose(c, pid, "Widen Exam 1 east", "Site example", [{"element": "W-08", "prop": "offset_mm", "to": -270}], "manual")
    reason = store.changeset(owner.fid, cid)["reason"]
    assert "moves 270 mm east" in reason and "Exam 2: 12 → 10.92" in reason and "New issue: Exam 2" in reason


def test_wall_moves_are_validated(make_owner):
    owner = make_owner()
    pid = _sample_project(owner)
    from backend import service
    c = type("C", (), {"fid": owner.fid, "uid": owner.me["user"]["id"], "audit": lambda *a, **k: None})()
    for bad in (0, 9000, "far"):
        try:
            service.propose(c, pid, "t", "r", [{"element": "W-08", "prop": "offset_mm", "to": bad}], "manual")
            raise AssertionError(bad)
        except service.ChangeError:
            pass


def test_fixture_host_moves_walls():
    from backend import geometry
    from conftest import SAMPLE
    moved = geometry.move_wall(SAMPLE["elements"], "W-08", -270)
    rooms = {e["id"]: e["props"]["area_m2"] for e in moved if e["type"] == "room"}
    assert rooms["R-exam1"] == 11.12 and rooms["R-exam2"] == 10.92 and rooms["R-corr"] == 70.0
    wall = next(e for e in moved if e["id"] == "W-08")
    assert wall["geom"]["start"] == [5270, 1000]


# ---- occupant loads and exit capacity ------------------------------------------

def test_rooms_carry_occupant_load_from_the_firms_factors(make_owner):
    owner = make_owner()
    pid = _sample_project(owner)
    els = {e["id"]: e["props"] for e in owner.get(f"/api/projects/{pid}").json()["elements"] if e["type"] == "room"}
    assert els["R-lobby"]["occupant_load"] == 52 and "1004.5" in els["R-lobby"]["load_ref"]  # 72 m² / 1.4
    assert els["R-exam1"]["occupant_load"] == 2 and els["R-corr"]["occupant_load"] == 0
    assert els["R-office"]["occupant_load"] == 3  # falls back to the business factor


def test_exit_capacity_flags_narrow_exits_and_widens_the_narrowest(make_owner):
    owner = make_owner()
    pid = _sample_project(owner)
    P = f"/api/projects/{pid}"
    r = owner.post("/api/rules", json={"id": "load-lobby", "name": "Lobby, standing", "kind": "load", "applies_to": "room",
                                       "where": "use=lobby", "value": 0.2, "unit": "m²/person", "ref": "test"})
    assert r.status_code == 200, r.text
    cap = next(i for i in owner.get(P).json()["issues"] if i["rule"] == "exit-capacity")
    assert cap["occupants"] > 360 and cap["required"] > cap["actual"] and cap["fixable"]
    cid = owner.post(f"{P}/issues/{cap['id']}/fix").json()["changeset"]
    op = owner.get(f"/api/changesets/{cid}").json()["ops"][0]
    assert op["prop"] == "clear_width_mm" and op["to"] > op["from"]


def test_load_and_capacity_rules_are_validated(sample):
    owner, _ = sample
    bad = owner.post("/api/rules", json={"name": "x", "kind": "load", "applies_to": "door", "value": 1})
    assert bad.status_code == 422 and "rooms" in bad.json()["error"]["fields"]["applies_to"]
    ok = owner.post("/api/rules", json={"name": "Clinic", "kind": "load", "applies_to": "room", "where": "use=clinic", "value": 9.3})
    assert ok.status_code == 200


def test_new_starter_rules_reach_existing_firms_but_deleted_ones_stay_gone(make_owner):
    from backend import db, service
    owner = make_owner()
    db.run("delete from rules where firm_id=? and id='exit-capacity'", (owner.fid,))  # a firm from before the rule existed
    service._topped_up.discard(owner.fid)
    assert "exit-capacity" in {r["id"] for r in owner.get("/api/rules").json()}  # opening Rules adds it
    assert owner.delete("/api/rules/load-exam").status_code == 200
    service._topped_up.discard(owner.fid)  # as after a restart
    assert "load-exam" not in {r["id"] for r in owner.get("/api/rules").json()}  # a deleted starter rule stays deleted


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
