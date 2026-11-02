"""Accounts, sessions, roles, firm isolation, invites, plugin tokens, plans (docs/security.md, docs/testing.md)."""
import time

import pytest

from conftest import PASSWORD, SAMPLE, User, plugin_token

P = "/api/projects/sample-clinic"


# ---- accounts and sessions -------------------------------------------------

def test_signup_validation_and_duplicate_email(app):
    u = User(app)
    r = u.c.post("/api/auth/signup", json={"name": "A", "email": "a@b.test", "password": "short", "firm_name": "F"})
    assert r.status_code == 422 and "password" in r.json()["error"]["fields"]
    r = u.c.post("/api/auth/signup", json={"name": "A", "email": "a@b.test", "password": "password123", "firm_name": "F"})
    assert r.status_code == 422 and "common" in r.json()["error"]["message"]
    assert u.c.post("/api/auth/signup", json={"name": "A", "email": "a@b.test", "password": PASSWORD, "firm_name": "F"}).status_code == 201
    r = User(app).c.post("/api/auth/signup", json={"name": "B", "email": "A@B.test", "password": PASSWORD, "firm_name": "G"})
    assert r.status_code == 422 and r.json()["error"]["fields"]["email"].startswith("Email already in use")


def test_session_cookie_flags_and_password_hash(app):
    u = User(app)
    r = u.c.post("/api/auth/signup", json={"name": "A", "email": "a@b.test", "password": PASSWORD, "firm_name": "F"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age=2592000" in cookie
    from backend import db
    h = db.val("select password_hash from users")
    assert h.startswith("$argon2id$") and PASSWORD not in h
    assert db.val("select count(*) from sessions") == 1
    assert u.c.cookies.get("lintel_session") not in str(db.all("select id_hash from sessions"))  # only the hash is stored


def test_login_logout_and_bad_password(app, make_owner):
    owner = make_owner()
    email = owner.me["user"]["email"]
    u = User(app)
    assert u.c.post("/api/auth/login", json={"email": email, "password": "wrong password!"}).status_code == 401
    assert u.c.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    u.refresh()
    assert u.get("/api/me").status_code == 200
    assert u.post("/api/auth/logout").status_code == 204
    assert u.get("/api/me").status_code == 401


def test_login_rate_limit(app, make_owner, monkeypatch):
    monkeypatch.delenv("LINTEL_NO_RATE_LIMIT")
    from backend import auth
    auth.reset_rate_limits()
    email = make_owner().me["user"]["email"]
    u = User(app)
    codes = [u.c.post("/api/auth/login", json={"email": email, "password": "nope nope nope"}).status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
    auth.reset_rate_limits()


def test_writes_need_csrf(make_owner):
    owner = make_owner()
    assert owner.c.post("/api/projects", json={"name": "x"}).status_code == 403
    assert owner.c.post("/api/projects", json={"name": "x"}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert owner.post("/api/projects", json={"name": "x"}).status_code == 201


def test_password_reset_flow(app, make_owner):
    from backend import emails
    owner = make_owner()
    email = owner.me["user"]["email"]
    anon = User(app)
    assert anon.c.post("/api/auth/reset/request", json={"email": "nobody@x.test"}).status_code == 202
    assert anon.c.post("/api/auth/reset/request", json={"email": email}).status_code == 202
    token = emails.OUTBOX[-1]["text"].split("token=")[1].split()[0]
    assert anon.c.post("/api/auth/reset/confirm", json={"token": token, "password": "a brand new pass"}).status_code == 204
    assert anon.c.post("/api/auth/reset/confirm", json={"token": token, "password": "another new pass"}).status_code == 422
    assert owner.get("/api/me").status_code == 401  # all sessions ended
    assert anon.c.post("/api/auth/login", json={"email": email, "password": "a brand new pass"}).status_code == 200


def test_change_password_keeps_this_session(make_owner):
    owner = make_owner()
    assert owner.post("/api/me/password", json={"current": "wrong", "password": "x" * 12}).status_code == 422
    assert owner.post("/api/me/password", json={"current": PASSWORD, "password": "another long one"}).status_code == 204
    assert owner.get("/api/me").status_code == 200


# ---- firm isolation --------------------------------------------------------

def test_firms_are_isolated(sample, make_owner):
    a, h = sample
    pid = a.get(P).json()["project"]["id"]
    cid = a.post(f"{P}/issues/door-clear-width:D-03/fix").json()["changeset"]
    b = make_owner(firm="Other Firm", name="Zed")
    assert b.get("/api/projects").json() == []
    assert b.get("/api/approvals").json()["changesets"] == []
    for method, url in [("get", f"/api/projects/{pid}"), ("get", P), ("patch", f"/api/projects/{pid}"),
                        ("post", f"/api/projects/{pid}/issues/door-clear-width:D-05/fix"),
                        ("get", f"/api/changesets/{cid}"), ("post", f"/api/changesets/{cid}/approve"),
                        ("post", f"/api/changesets/{cid}/reject"), ("post", f"/api/changesets/{cid}/revert"),
                        ("get", f"/api/changesets/{cid}/comments"), ("post", f"/api/changesets/{cid}/comments"),
                        ("get", f"/api/projects/{pid}/chat"), ("put", f"/api/projects/{pid}/rules/door-clear-width"),
                        ("get", f"/api/audit?project={pid}")]:
        r = getattr(b, method)(url, **({} if method == "get" else {"json": {"name": "x", "body": "x", "value": 1}}))
        assert r.status_code == 404, (method, url, r.status_code)
    assert all(e["firm_id"] == b.fid for e in b.get("/api/audit").json()["entries"])
    # B's plugin token can't see or report on A's project or change sets
    hb = plugin_token(b)
    assert b.c.get(f"/api/plugin/pending?project={pid}", headers=hb).status_code == 404
    a.post(f"/api/changesets/{cid}/approve")
    assert b.c.post("/api/plugin/result", json={"changeset": cid, "ok": True}, headers=hb).status_code == 404
    # the same plugin key in firm B makes B's own project, not A's
    b.c.post("/api/plugin/snapshot", json=dict(SAMPLE, host="test"), headers=hb)
    assert b.get(P).json()["project"]["id"] != pid


# ---- roles -----------------------------------------------------------------

WRITES = [  # (method, url template, body, minimum role)
    ("post", "/api/projects", {"name": "New"}, "member"),
    ("post", P + "/issues/door-clear-width:D-05/fix", {}, "member"),
    ("post", "/api/changesets/{cid}/comments", {"body": "Looks right"}, "member"),
    ("post", "/api/tokens", {"name": "x"}, "member"),
    ("post", "/api/changesets/{cid}/approve", {}, "approver"),
    ("post", "/api/changesets/{cid2}/reject", {}, "approver"),
    ("post", "/api/rules", {"name": "R", "kind": "min", "applies_to": "door", "prop": "clear_width_mm", "value": 850}, "admin"),
    ("post", "/api/rules/door-clear-width/status", {"status": "disabled"}, "admin"),
    ("put", P + "/rules/door-clear-width", {"value": 850}, "admin"),
    ("patch", P, {"name": "Renamed"}, "admin"),
    ("patch", "/api/firm", {"name": "Renamed firm"}, "admin"),
    ("post", "/api/invites", {"email": "new@x.test", "role": "viewer"}, "admin"),
]
RANK = ["viewer", "member", "approver", "admin", "owner"]


def _open_fix(owner, issue):
    """The id of a proposed change set for this issue, proposing one if none is open."""
    cid = owner.post(f"{P}/issues/{issue}/fix").json().get("changeset")
    element = issue.split(":")[1]
    return cid or next(c["id"] for c in owner.get(P).json()["changesets"]
                       if c["status"] == "proposed" and any(o["element"] == element for o in c["ops"]))


@pytest.mark.parametrize("role", ["viewer", "member", "approver", "admin"])
def test_role_matrix(sample, invite, role):
    owner, _ = sample
    u = invite(owner, role)
    for method, url, body, minimum in WRITES:
        cid, cid2 = _open_fix(owner, "door-clear-width:D-03"), _open_fix(owner, "stair-tread-min:S-01")
        r = getattr(u, method)(url.format(cid=cid, cid2=cid2), json=body)
        allowed = RANK.index(role) >= RANK.index(minimum)
        assert (r.status_code < 400) == allowed, (role, method, url, r.status_code, r.text)
        if not allowed:
            assert r.status_code == 403
        # put state back for the next row
        owner.post("/api/rules/door-clear-width/status", json={"status": "active"})
        for c in owner.get(P).json()["changesets"]:
            if c["status"] == "approved":
                owner.c.post("/api/plugin/result", json={"changeset": c["id"], "ok": False, "error": "reset"},
                             headers=plugin_token(owner))


def test_member_sees_no_approve_but_can_propose(sample, invite):
    owner, _ = sample
    m = invite(owner, "member")
    cid = m.post(f"{P}/issues/door-clear-width:D-03/fix").json()["changeset"]
    r = m.post(f"/api/changesets/{cid}/approve")
    assert r.status_code == 403 and r.json()["error"]["message"] == "Approvers only."


def test_last_owner_cannot_be_demoted_or_removed(sample, invite):
    owner, _ = sample
    admin = invite(owner, "admin")
    uid = owner.me["user"]["id"]
    assert owner.patch(f"/api/members/{uid}", json={"role": "admin"}).status_code == 409
    assert admin.patch(f"/api/members/{uid}", json={"role": "viewer"}).status_code == 403
    assert admin.delete(f"/api/members/{uid}").status_code == 409
    assert admin.patch(f"/api/members/{admin.me['user']['id']}", json={"role": "owner"}).status_code == 403


def test_removed_member_loses_access_and_tokens(sample, invite):
    owner, _ = sample
    m = invite(owner, "member")
    h = plugin_token(m)
    assert m.c.get("/api/plugin/pending?project=sample-clinic", headers=h).status_code == 200
    assert owner.delete(f"/api/members/{m.me['user']['id']}").status_code == 200
    assert m.get("/api/me").status_code == 401
    assert m.c.get("/api/plugin/pending?project=sample-clinic", headers=h).status_code == 401


# ---- invites ---------------------------------------------------------------

def test_invite_flow(app, sample):
    owner, _ = sample
    r = owner.post("/api/invites", json={"email": "cara@x.test", "role": "approver"})
    token = r.json()["link"].rsplit("/", 1)[1]
    anon = User(app)
    info = anon.c.get(f"/api/invites/{token}").json()
    assert info["firm_name"] == "Studio North" and info["role"] == "approver" and info["has_account"] is False
    assert anon.c.post(f"/api/invites/{token}/accept", json={"name": "Cara", "password": "short"}).status_code == 422
    assert anon.c.post(f"/api/invites/{token}/accept", json={"name": "Cara", "password": PASSWORD}).status_code == 200
    anon.refresh()
    assert anon.me["firm"]["id"] == owner.fid and anon.me["role"] == "approver"
    assert len(anon.get("/api/projects").json()) == 1
    assert User(app).c.get(f"/api/invites/{token}").status_code == 409  # single use


def test_invite_expiry_and_email_binding(app, sample, make_owner):
    owner, _ = sample
    token = owner.post("/api/invites", json={"email": "dan@x.test", "role": "member"}).json()["link"].rsplit("/", 1)[1]
    other = make_owner(firm="Elsewhere", name="Eve")
    assert other.post(f"/api/invites/{token}/accept", json={}).status_code == 403  # bound to the invited email
    from backend import db, store
    db.run("update invites set expires_at=? where token_hash=?", (time.time() - 1, store.sha(token)))
    assert User(app).c.get(f"/api/invites/{token}").status_code == 410


def test_existing_user_joins_second_firm_and_switches(app, sample, make_owner):
    owner, _ = sample
    other = make_owner(firm="Second Firm", name="Fay")
    email = other.me["user"]["email"]
    token = owner.post("/api/invites", json={"email": email, "role": "viewer"}).json()["link"].rsplit("/", 1)[1]
    assert other.post(f"/api/invites/{token}/accept", json={}).status_code == 200
    other.refresh()
    assert other.me["firm"]["id"] == owner.fid and len(other.me["firms"]) == 2
    second = next(f["id"] for f in other.me["firms"] if f["id"] != owner.fid)
    assert other.post("/api/me/firm", json={"firm_id": second}).status_code == 200
    assert other.refresh().json()["firm"]["name"] == "Second Firm"
    assert other.post("/api/me/firm", json={"firm_id": "frm_nope"}).status_code == 404


# ---- plugin tokens ---------------------------------------------------------

def test_token_shown_once_hashed_and_revocable(sample):
    owner, _ = sample
    r = owner.post("/api/tokens", json={"name": "Ana's Rhino"}).json()
    listed = owner.get("/api/tokens").json()
    assert all("token" not in t for t in listed) and any(t["prefix"] == r["token"][:8] for t in listed)
    from backend import db
    assert r["token"] not in str(db.all("select * from plugin_tokens"))
    h = {"Authorization": "Bearer " + r["token"]}
    assert owner.c.get("/api/plugin/pending?project=sample-clinic", headers=h).status_code == 200
    assert next(t for t in owner.get("/api/tokens").json() if t["id"] == r["id"])["last_used_at"]
    assert owner.delete(f"/api/tokens/{r['id']}").status_code == 200
    assert owner.c.get("/api/plugin/pending?project=sample-clinic", headers=h).status_code == 401


def test_viewer_token_cannot_sync(sample, invite):
    owner, _ = sample
    v = invite(owner, "viewer")
    assert v.post("/api/tokens", json={"name": "x"}).status_code == 403


# ---- plans -----------------------------------------------------------------

def _expire_trial(fid):
    from backend import store
    store.update_firm(fid, trial_ends_at=time.time() - 1)


def test_free_plan_limits(sample):
    owner, _ = sample
    _expire_trial(owner.fid)
    assert owner.refresh().json()["firm"]["plan"] == "free"
    r = owner.post("/api/projects", json={"name": "Second"})
    assert r.status_code == 402 and r.json()["error"]["limit"] == "projects"
    cid = owner.post(f"{P}/issues/door-clear-width:D-03/fix").json()["changeset"]  # proposing still works
    r = owner.post(f"/api/changesets/{cid}/approve")
    assert r.status_code == 402 and r.json()["error"]["code"] == "plan_limit" and r.json()["error"]["limit"] == "apply"
    assert owner.post("/api/rules", json={"name": "R", "kind": "min", "applies_to": "door", "prop": "clear_width_mm",
                                          "value": 900}).status_code == 402
    assert owner.post("/api/invites", json={"email": "x@y.test", "role": "member"}).status_code == 402
    assert owner.post("/api/invites", json={"email": "x@y.test", "role": "viewer"}).status_code == 201  # viewers are free
    assert len(owner.get(P).json()["issues"]) == 9  # data kept


def test_two_approvals_needs_firm_plan_then_two_people(sample, invite):
    owner, _ = sample
    assert owner.patch("/api/firm", json={"two_approvals": True}).status_code == 402
    from backend import store
    store.update_firm(owner.fid, plan="firm", seats=5, billing_customer_id="cus_test")
    assert owner.patch("/api/firm", json={"two_approvals": True}).status_code == 200
    approver = invite(owner, "approver")
    cid = owner.post(f"{P}/issues/door-clear-width:D-03/fix").json()["changeset"]
    first = owner.post(f"/api/changesets/{cid}/approve").json()
    assert first == {"status": "proposed", "approvals": 1, "needed": 2}
    assert owner.post(f"/api/changesets/{cid}/approve").json()["approvals"] == 1  # same person twice counts once
    assert approver.post(f"/api/changesets/{cid}/approve").json()["status"] == "approved"


def test_audit_filters_and_csv(sample):
    owner, _ = sample
    owner.post(f"{P}/issues/door-clear-width:D-03/fix")
    entries = owner.get("/api/audit?action=changeset").json()["entries"]
    assert entries and all(e["action"].startswith("changeset") for e in entries)
    assert owner.get("/api/audit.csv").status_code == 402  # Firm plan
    from backend import store
    store.update_firm(owner.fid, plan="firm", billing_customer_id="cus_test")
    r = owner.get("/api/audit.csv")
    assert r.status_code == 200 and r.text.startswith("when_utc,project,who,action")


def test_comments(sample, invite):
    owner, _ = sample
    m = invite(owner, "member")
    cid = owner.post(f"{P}/issues/door-clear-width:D-03/fix").json()["changeset"]
    assert m.post(f"/api/changesets/{cid}/comments", json={"body": "Check the frame size first."}).status_code == 201
    assert owner.post(f"/api/changesets/{cid}/comments", json={"body": "x" * 4001}).status_code == 422
    cs = owner.get(f"/api/changesets/{cid}").json()
    assert cs["comments"][0]["name"] == "Ben" and owner.get("/api/approvals").json()["changesets"][0]["comment_count"] == 1


def test_delete_firm_needs_name(sample):
    owner, _ = sample
    assert owner.delete("/api/firm", json={"confirm": "wrong"}).status_code == 422
    assert owner.delete("/api/firm", json={"confirm": "Studio North"}).status_code == 204
    assert owner.get("/api/me").status_code == 401


def test_health_and_headers(app):
    r = User(app).c.get("/api/health")
    assert r.json() == {"ok": True, "db": "ok", "version": r.json()["version"]}
    assert "frame-ancestors 'self'" in r.headers["content-security-policy"] and r.headers["x-content-type-options"] == "nosniff"


def test_billing_webhook_signature_and_idempotency(sample, monkeypatch):
    import hashlib
    import hmac
    import json as _json
    owner, _ = sample
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    ev = {"id": "evt_1", "type": "checkout.session.completed",
          "data": {"object": {"customer": "cus_1", "client_reference_id": owner.fid, "metadata": {"firm_id": owner.fid, "plan": "firm"}}}}
    body = _json.dumps(ev).encode()
    t = str(int(time.time()))
    sig = hmac.new(b"whsec_test", f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    assert owner.c.post("/api/billing/webhook", content=body, headers={"Stripe-Signature": f"t={t},v1=bad"}).status_code == 400
    assert owner.c.post("/api/billing/webhook", content=body, headers={"Stripe-Signature": f"t={t},v1={sig}"}).json() == {"ok": True}
    assert owner.c.post("/api/billing/webhook", content=body, headers={"Stripe-Signature": f"t={t},v1={sig}"}).json()["duplicate"]
    assert owner.refresh().json()["firm"]["plan"] == "firm"
