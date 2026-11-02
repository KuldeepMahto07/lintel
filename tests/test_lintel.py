"""Core behaviour: checks, the change-set state machine, the plugin protocol, rules, the agent."""
import copy
import json
import sys
from types import SimpleNamespace

import pytest

from conftest import ROOT, User

P = "/api/projects/sample-clinic"  # the plugin's own project key works as well as the prj_ id


def issues(u):
    return u.get(P).json()["issues"]


def test_checker_flags_expected_issues(sample):
    owner, _ = sample
    assert {i["id"] for i in issues(owner)} == {
        "door-clear-width:D-03", "door-clear-width:D-05", "corridor-width:R-corr", "stair-riser-max:S-01",
        "stair-tread-min:S-01", "egress-travel:R-office", "egress-travel:R-corr", "bedroom-area:R-oncall", "firm-exam-room:R-exam1",
    }


def test_egress_distance_is_door_graph_length(sample):
    owner, _ = sample
    # far corner (70000,6000) -> office door (66000,1000) -> lobby door (0,500) -> exit (-8000,500)
    assert owner.get(P).json()["egress"]["R-office"] == pytest.approx(6403.1 + 66001.9 + 8000, abs=1)


def test_plugin_needs_token(sample):
    owner, _ = sample
    assert owner.get("/api/plugin/pending?project=sample-clinic").status_code == 401
    assert owner.get("/api/plugin/pending?project=sample-clinic", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_fix_requires_approval_then_host_applies(sample):
    owner, h = sample
    cid = owner.post(f"{P}/issues/door-clear-width:D-03/fix").json()["changeset"]
    assert owner.get("/api/plugin/pending?project=sample-clinic", headers=h).json() == []  # not approved yet
    assert owner.post(f"/api/changesets/{cid}/approve").json()["status"] == "approved"
    pending = owner.get("/api/plugin/pending?project=sample-clinic", headers=h).json()
    assert pending[0]["ops"] == [{"op": "set_prop", "element": "D-03", "element_name": "Exam 1 door",
                                  "prop": "clear_width_mm", "from": 760, "to": 813.0}]
    assert owner.get(P).json()["plugin_seen_at"]  # the poll is recorded
    assert owner.c.post("/api/plugin/result", json={"changeset": cid, "ok": True, "host": "test"}, headers=h).status_code == 204
    assert owner.post(f"/api/changesets/{cid}/approve").status_code == 409  # no double approval
    actions = [a["action"] for a in owner.get("/api/audit?project=sample-clinic").json()["entries"]]
    assert {"changeset.proposed", "changeset.approved", "changeset.applied"} <= set(actions)


def test_stair_riser_fix_recomputes_count(sample):
    owner, _ = sample
    assert owner.post(f"{P}/issues/stair-riser-max:S-01/fix").status_code == 201
    ops = {o["prop"]: o for o in owner.get(P).json()["changesets"][0]["ops"]}
    assert ops["risers"]["to"] == 20 and ops["riser_mm"]["to"] == 171.0


def test_geometry_issues_are_advice_only(sample):
    owner, _ = sample
    r = owner.post(f"{P}/issues/corridor-width:R-corr/fix")
    assert r.status_code == 409 and "design decision" in r.json()["error"]["message"]


def test_reject_and_revert(sample):
    owner, h = sample
    a = owner.post(f"{P}/issues/door-clear-width:D-05/fix").json()["changeset"]
    owner.post(f"/api/changesets/{a}/reject")
    assert owner.get("/api/plugin/pending?project=sample-clinic", headers=h).json() == []
    b = owner.post(f"{P}/issues/door-clear-width:D-05/fix").json()["changeset"]
    owner.post(f"/api/changesets/{b}/approve")
    owner.c.post("/api/plugin/result", json={"changeset": b, "ok": True}, headers=h)
    rv = owner.post(f"/api/changesets/{b}/revert").json()["changeset"]
    pend = owner.get("/api/plugin/pending?project=sample-clinic", headers=h).json()
    assert pend[0]["id"] == rv and pend[0]["ops"][0]["from"] == 813.0 and pend[0]["ops"][0]["to"] == 711
    owner.c.post("/api/plugin/result", json={"changeset": rv, "ok": True}, headers=h)
    statuses = {c["id"]: c["status"] for c in owner.get(P).json()["changesets"]}
    assert statuses == {a: "rejected", b: "reverted", rv: "applied"}


def test_undo_reject(sample):
    owner, _ = sample
    a = owner.post(f"{P}/issues/door-clear-width:D-05/fix").json()["changeset"]
    owner.post(f"/api/changesets/{a}/reject")
    assert owner.post(f"/api/changesets/{a}/undo-reject").json()["status"] == "proposed"


def test_failed_apply_records_reason(sample):
    owner, h = sample
    cid = owner.post(f"{P}/issues/stair-tread-min:S-01/fix").json()["changeset"]
    owner.post(f"/api/changesets/{cid}/approve")
    owner.c.post("/api/plugin/result", json={"changeset": cid, "ok": False, "error": "S-01.tread_mm is now 260"}, headers=h)
    cs = next(c for c in owner.get(P).json()["changesets"] if c["id"] == cid)
    assert cs["status"] == "failed" and "260" in cs["error"]


def test_drift_guard_refuses_stale_change():
    sys.path.insert(0, str(ROOT / "hosts"))
    from lintel_client import apply_changeset
    model = {"D-03": 900}
    cs = {"title": "x", "ops": [{"element": "D-03", "prop": "w", "from": 760, "to": 813}]}
    ok, err = apply_changeset(cs, lambda e, p: model[e], lambda e, p, v: model.__setitem__(e, v))
    assert not ok and "expected 760" in err and model["D-03"] == 900


def test_rule_import_csv_dry_run_and_validation(sample):
    owner, _ = sample
    good = "name,kind,applies_to,prop,value,unit,where,ref,severity,fixable\n" \
           "Firm door width,min,door,clear_width_mm,900,mm,,Firm standard,error,true\n"
    bad = good + "Broken,between,door,clear_width_mm,abc,mm,,x,error,true\n"
    preview = owner.post("/api/rules/import?dry_run=1", content=bad).json()
    assert preview["valid"] == 1 and preview["invalid"] == 1 and "kind" in preview["rows"][1]["errors"]
    assert owner.post("/api/rules/import", content=bad).status_code == 422
    assert owner.post("/api/rules/import", content=good).json()["imported"] == 1
    assert "Firm door width" in {i["rule_name"] for i in issues(owner)}
    r = owner.post("/api/rules", json={"name": "x", "kind": "between", "applies_to": "door", "value": 1})
    assert r.status_code == 422 and "kind" in r.json()["error"]["fields"]


def test_disable_rule_clears_flags(sample):
    owner, _ = sample
    owner.post("/api/rules/door-clear-width/status", json={"status": "disabled"})
    assert not any(i["rule"] == "door-clear-width" for i in issues(owner))


def test_project_override_changes_check(sample):
    owner, _ = sample
    assert any(i["id"] == "egress-travel:R-office" for i in issues(owner))
    # a sprinklered building allows a longer travel distance
    assert owner.put(f"{P}/rules/egress-travel", json={"value": 91440, "enabled": True}).status_code == 200
    assert not any(i["id"] == "egress-travel:R-office" for i in issues(owner))
    owner.delete(f"{P}/rules/egress-travel")
    assert any(i["id"] == "egress-travel:R-office" for i in issues(owner))


def test_waitlist(app):
    u = User(app)
    assert u.c.post("/api/waitlist", json={"email": "not-an-email"}).status_code == 422
    assert u.c.post("/api/waitlist", json={"email": "Ana@Studio.example", "host": "Rhino"}).json() == {"ok": True, "new": True}
    assert u.c.post("/api/waitlist", json={"email": "ana@studio.example"}).json()["new"] is False
    assert u.c.get("/api/waitlist").status_code == 403  # staff only


def test_sample_project_applies_on_approval(make_owner):
    owner = make_owner()
    pid = owner.post("/api/projects/sample").json()["project"]["id"]
    assert len(owner.get(f"/api/projects/{pid}").json()["issues"]) == 9
    cid = owner.post(f"/api/projects/{pid}/issues/door-clear-width:D-03/fix").json()["changeset"]
    assert owner.post(f"/api/changesets/{cid}/approve").json()["status"] == "applied"
    d = owner.get(f"/api/projects/{pid}").json()
    assert next(e for e in d["elements"] if e["id"] == "D-03")["props"]["clear_width_mm"] == 813
    rv = owner.post(f"/api/changesets/{cid}/revert").json()["changeset"]
    statuses = {x["id"]: x["status"] for x in owner.get(f"/api/projects/{pid}").json()["changesets"]}
    assert statuses == {cid: "reverted", rv: "applied"}


def test_demo_mode_applies_every_project(sample, monkeypatch):
    owner, _ = sample
    monkeypatch.setenv("LINTEL_DEMO", "1")
    cid = owner.post(f"{P}/issues/door-clear-width:D-03/fix").json()["changeset"]
    assert owner.post(f"/api/changesets/{cid}/approve").json()["status"] == "applied"


# ---- agent loop with a scripted stand-in for the Claude client ----------------------------------

class Block(SimpleNamespace):
    def model_dump(self, exclude_none=False):
        return dict(self.__dict__)


class FakeClaude:
    """Returns a scripted sequence of responses and records the requests."""
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(copy.deepcopy(kw))
        return self.script.pop(0)


def _ctx(owner):
    from backend import auth, store
    return auth.Ctx(user=store.user(owner.me["user"]["id"]), firm=store.firm(owner.fid), role="owner")


def _pid(owner):
    return owner.get(P).json()["project"]["id"]


WIDEN = [
    SimpleNamespace(stop_reason="tool_use", content=[
        Block(type="text", text="Checking."),
        Block(type="tool_use", id="tu1", name="propose_changes", input={
            "title": "Widen WC door", "reason": "Below 813 mm (IBC §1010.1.1 per your rules)",
            "ops": [{"element": "D-05", "prop": "clear_width_mm", "to": 900}]})]),
    SimpleNamespace(stop_reason="end_turn", content=[Block(type="text", text="Proposed; waiting for your approval.")]),
]


def test_agent_can_only_propose(sample):
    owner, _ = sample
    from backend import agent
    fake = FakeClaude(WIDEN)
    out = agent.chat(_ctx(owner), _pid(owner), "widen the WC door to 900", client=fake)
    assert len(out["changesets"]) == 1 and out["replies"][-1].startswith("Proposed")
    cs = owner.get(P).json()["changesets"][0]
    assert cs["status"] == "proposed" and cs["source"] == "agent" and cs["ops"][0]["from"] == 711
    tool_result = fake.calls[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "tu1" and not tool_result["is_error"]
    assert not any(t["name"] in ("approve", "apply") for t in fake.calls[0]["tools"])
    # the transcript shows the proposal inline, and usage is counted
    chat = owner.get(f"{P}/chat").json()["messages"]
    assert [m["role"] for m in chat] == ["user", "assistant", "changeset", "assistant"]
    assert owner.refresh().json()["usage"]["chat_messages"] == 1


def test_agent_tool_errors_are_returned_not_raised(sample):
    owner, _ = sample
    from backend import agent
    fake = FakeClaude([
        SimpleNamespace(stop_reason="tool_use", content=[Block(type="tool_use", id="tu1", name="propose_changes", input={
            "title": "t", "reason": "r", "ops": [{"element": "R-corr", "prop": "clear_width_mm", "to": 1200}]})]),
        SimpleNamespace(stop_reason="end_turn", content=[Block(type="text", text="That needs walls moved.")]),
    ])
    agent.chat(_ctx(owner), _pid(owner), "make the corridor wider", client=fake)
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] and "not editable" in result["content"]


def test_chat_endpoint_streams_events(sample, monkeypatch):
    owner, _ = sample
    from backend import agent
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(agent.anthropic, "Anthropic", lambda: FakeClaude(copy.deepcopy(WIDEN)))
    r = owner.post(f"{P}/chat", json={"message": "which doors are too narrow?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    types = [json.loads(line[6:])["type"] for line in r.text.splitlines() if line.startswith("data: ")]
    assert types == ["text", "changeset", "text", "done"]


def test_chat_without_key_says_so(sample):
    owner, _ = sample
    r = owner.post(f"{P}/chat", json={"message": "hi"})
    assert r.status_code == 503 and "isn't set up" in r.json()["error"]["message"]
    assert owner.get(f"{P}/chat").json()["configured"] is False
