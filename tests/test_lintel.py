import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = json.loads((ROOT / "samples" / "clinic.json").read_text())


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("LINTEL_TOKEN", "t")
    from backend import store
    store.reset(tmp_path / "t.db")
    from backend.app import app
    with TestClient(app) as c:
        c.post("/api/plugin/snapshot", json=dict(SAMPLE, host="test"), headers={"X-Lintel-Token": "t"})
        yield c


def issues(api):
    return api.get("/api/projects/sample-clinic").json()["issues"]


def test_checker_flags_expected_issues(api):
    found = {i["id"] for i in issues(api)}
    assert found == {
        "door-clear-width:D-03", "door-clear-width:D-05", "corridor-width:R-corr", "stair-riser-max:S-01",
        "stair-tread-min:S-01", "egress-travel:R-office", "egress-travel:R-corr", "bedroom-area:R-oncall", "firm-exam-room:R-exam1",
    }


def test_egress_distance_is_door_graph_length(api):
    eg = api.get("/api/projects/sample-clinic").json()["egress"]
    # far corner (70000,6000) -> office door (66000,1000) -> lobby door (0,500) -> exit (-8000,500)
    assert eg["R-office"] == pytest.approx(6403.1 + 66001.9 + 8000, abs=1)


def test_plugin_needs_token(api):
    assert api.get("/api/plugin/pending?project=sample-clinic").status_code == 401


def test_fix_requires_approval_then_host_applies(api):
    h = {"X-Lintel-Token": "t"}
    cid = api.post("/api/projects/sample-clinic/issues/door-clear-width:D-03/fix", json={"actor": "ana"}).json()["changeset"]
    assert api.get("/api/plugin/pending?project=sample-clinic", headers=h).json() == []  # not approved yet
    assert api.post(f"/api/changesets/{cid}/approve", json={"actor": "ana"}).json()["status"] == "approved"
    pending = api.get("/api/plugin/pending?project=sample-clinic", headers=h).json()
    assert pending[0]["ops"] == [{"op": "set_prop", "element": "D-03", "element_name": "Exam 1 door",
                                  "prop": "clear_width_mm", "from": 760, "to": 813.0}]
    api.post("/api/plugin/result", json={"changeset": cid, "ok": True, "host": "test"}, headers=h)
    assert api.post(f"/api/changesets/{cid}/approve", json={}).status_code == 409  # no double approval
    actions = [a["action"] for a in api.get("/api/audit?project=sample-clinic").json()]
    assert {"changeset.proposed", "changeset.approved", "changeset.applied"} <= set(actions)


def test_stair_riser_fix_recomputes_count(api):
    cid = api.post("/api/projects/sample-clinic/issues/stair-riser-max:S-01/fix", json={}).json()["changeset"]
    ops = {o["prop"]: o for o in api.get("/api/projects/sample-clinic").json()["changesets"][0]["ops"]}
    assert cid and ops["risers"]["to"] == 20 and ops["riser_mm"]["to"] == 171.0


def test_geometry_issues_are_advice_only(api):
    r = api.post("/api/projects/sample-clinic/issues/corridor-width:R-corr/fix", json={})
    assert r.status_code == 409


def test_reject_and_revert(api):
    h = {"X-Lintel-Token": "t"}
    a = api.post("/api/projects/sample-clinic/issues/door-clear-width:D-05/fix", json={}).json()["changeset"]
    api.post(f"/api/changesets/{a}/reject", json={})
    assert api.get("/api/plugin/pending?project=sample-clinic", headers=h).json() == []
    b = api.post("/api/projects/sample-clinic/issues/door-clear-width:D-05/fix", json={}).json()["changeset"]
    api.post(f"/api/changesets/{b}/approve", json={})
    api.post("/api/plugin/result", json={"changeset": b, "ok": True}, headers=h)
    rv = api.post(f"/api/changesets/{b}/revert", json={}).json()["changeset"]
    pend = api.get("/api/plugin/pending?project=sample-clinic", headers=h).json()
    assert pend[0]["id"] == rv and pend[0]["ops"][0]["from"] == 813.0 and pend[0]["ops"][0]["to"] == 711
    api.post("/api/plugin/result", json={"changeset": rv, "ok": True}, headers=h)
    statuses = {c["id"]: c["status"] for c in api.get("/api/projects/sample-clinic").json()["changesets"]}
    assert statuses == {a: "rejected", b: "reverted", rv: "applied"}


def test_drift_guard_refuses_stale_change():
    import sys
    sys.path.insert(0, str(ROOT / "hosts"))
    from lintel_client import apply_changeset
    model = {"D-03": 900}
    cs = {"title": "x", "ops": [{"element": "D-03", "prop": "w", "from": 760, "to": 813}]}
    ok, err = apply_changeset(cs, lambda e, p: model[e], lambda e, p, v: model.__setitem__(e, v))
    assert not ok and "expected 760" in err and model["D-03"] == 900


def test_rule_import_csv_and_validation(api):
    csv_text = "name,kind,applies_to,prop,value,unit,where,ref,severity,fixable\n" \
               "Firm door width,min,door,clear_width_mm,900,mm,,Firm standard,error,true\n"
    assert api.post("/api/rules/import", content=csv_text).json()["imported"] == 1
    assert "Firm door width" in {i["rule_name"] for i in issues(api)}
    assert api.post("/api/rules", json={"name": "x", "kind": "between", "applies_to": "door", "value": 1}).status_code == 422


def test_waitlist(api):
    assert api.post("/api/waitlist", json={"email": "not-an-email"}).status_code == 422
    r = api.post("/api/waitlist", json={"email": "Ana@Studio.example", "host": "Rhino", "firm_size": "1–5"}).json()
    assert r == {"ok": True, "new": True}
    assert api.post("/api/waitlist", json={"email": "ana@studio.example"}).json()["new"] is False
    assert [w["email"] for w in api.get("/api/waitlist").json()] == ["ana@studio.example"]


def test_demo_mode_seeds_and_applies_on_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("LINTEL_DEMO", "1")
    monkeypatch.setenv("LINTEL_TOKEN", "t")
    from backend import store
    store.reset(tmp_path / "demo.db")
    from backend.app import app
    with TestClient(app) as c:
        assert [p["id"] for p in c.get("/api/projects").json()] == ["sample-clinic"]
        cid = c.post("/api/projects/sample-clinic/issues/door-clear-width:D-03/fix", json={}).json()["changeset"]
        assert c.post(f"/api/changesets/{cid}/approve", json={}).json()["status"] == "applied"
        d = c.get("/api/projects/sample-clinic").json()
        assert next(e for e in d["elements"] if e["id"] == "D-03")["props"]["clear_width_mm"] == 813
        rv = c.post(f"/api/changesets/{cid}/revert", json={}).json()["changeset"]
        statuses = {x["id"]: x["status"] for x in c.get("/api/projects/sample-clinic").json()["changesets"]}
        assert statuses == {cid: "reverted", rv: "applied"}


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


def test_agent_can_only_propose(api):
    from backend import agent
    fake = FakeClaude([
        SimpleNamespace(stop_reason="tool_use", content=[
            Block(type="text", text="Checking."),
            Block(type="tool_use", id="tu1", name="propose_changes", input={
                "title": "Widen WC door", "reason": "Below 813 mm (IBC §1010.1.1 per your rules)",
                "ops": [{"element": "D-05", "prop": "clear_width_mm", "to": 900}]})]),
        SimpleNamespace(stop_reason="end_turn", content=[Block(type="text", text="Proposed; waiting for your approval.")]),
    ])
    out = agent.chat("sample-clinic", "widen the WC door to 900", client=fake)
    assert len(out["changesets"]) == 1 and out["replies"][-1].startswith("Proposed")
    cs = api.get("/api/projects/sample-clinic").json()["changesets"][0]
    assert cs["status"] == "proposed" and cs["source"] == "agent" and cs["ops"][0]["from"] == 711
    tool_result = fake.calls[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "tu1" and not tool_result["is_error"]
    assert not any(t["name"] in ("approve", "apply") for t in fake.calls[0]["tools"])


def test_agent_tool_errors_are_returned_not_raised(api):
    from backend import agent
    fake = FakeClaude([
        SimpleNamespace(stop_reason="tool_use", content=[Block(type="tool_use", id="tu1", name="propose_changes", input={
            "title": "t", "reason": "r", "ops": [{"element": "R-corr", "prop": "clear_width_mm", "to": 1200}]})]),
        SimpleNamespace(stop_reason="end_turn", content=[Block(type="text", text="That needs walls moved.")]),
    ])
    agent.chat("sample-clinic", "make the corridor wider", client=fake)
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] and "not editable" in result["content"]
