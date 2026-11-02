"""End-to-end run over real HTTP: backend server + fixture host + approval flow.

    .venv\\Scripts\\python scripts\\e2e.py           # deterministic flow, no Claude calls
    .venv\\Scripts\\python scripts\\e2e.py --live    # also asks Claude to propose a fix (uses ANTHROPIC_API_KEY)

Uses a throwaway database and port 8012; your real data/ is untouched.
"""
import http.cookiejar
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hosts"))
PORT = 8012
URL = f"http://127.0.0.1:{PORT}"
_jar = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
_csrf = {"v": ""}


def call(method, path, body=None):
    """A signed-in browser: session cookie plus the CSRF header on writes."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-CSRF-Token": _csrf["v"]})
    with _jar.open(req, timeout=300) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def sign_up():
    call("POST", "/api/auth/signup", {"name": "E2E Owner", "email": "owner@e2e.test", "password": "e2e-sheet-password",
                                      "firm_name": "E2E Studio"})
    _csrf["v"] = call("GET", "/api/me")["csrf"]
    return call("POST", "/api/tokens", {"name": "e2e fixture host"})["token"]


def check(label, cond):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        raise SystemExit(1)


def main():
    live = "--live" in sys.argv
    tmp = tempfile.mkdtemp(prefix="lintel-e2e-")
    env = dict(os.environ, LINTEL_DB=os.path.join(tmp, "e2e.db"), LINTEL_URL=URL)
    env.pop("LINTEL_DEMO", None)
    os.environ.update(LINTEL_URL=URL)
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app:app", "--port", str(PORT), "--log-level", "warning"],
                              cwd=ROOT, env=env)
    try:
        for _ in range(50):
            try:
                call("GET", "/api/health")
                break
            except OSError:
                time.sleep(0.2)
        print("0. Sign up, create a personal plugin token")
        token = sign_up()
        check("token issued", token.startswith("lnt_"))
        from fixture_host import FixtureHost
        host = FixtureHost(str(ROOT / "samples" / "clinic.json"), url=URL, token=token, fresh=True)

        print("1. Observe: host pushes the model")
        host.sync()
        d = call("GET", "/api/projects/sample-clinic")
        check(f"{len(d['elements'])} elements received", len(d["elements"]) == 19)
        ids = {i["id"] for i in d["issues"]}
        check(f"{len(ids)} issues flagged (doors, corridor, stair, egress, areas)",
              {"door-clear-width:D-03", "corridor-width:R-corr", "stair-riser-max:S-01", "egress-travel:R-office",
               "bedroom-area:R-oncall"} <= ids)

        print("2. Advise: propose a fix, nothing changes yet")
        cid = call("POST", "/api/projects/sample-clinic/issues/door-clear-width:D-03/fix")["changeset"]
        host.sync()
        check("door still 760 mm before approval", host.get("D-03", "clear_width_mm") == 760)

        print("3. Act: approve, host applies in one undo step")
        call("POST", f"/api/changesets/{cid}/approve")
        applied = host.sync()
        check("host applied the change set", applied == [(cid, True, None)])
        check("door now 813 mm in the host model", host.get("D-03", "clear_width_mm") == 813)
        saved = json.loads(Path(host.path).read_text())
        check("host file saved", next(e for e in saved["elements"] if e["id"] == "D-03")["props"]["clear_width_mm"] == 813)
        d = call("GET", "/api/projects/sample-clinic")
        check("issue cleared after re-check", "door-clear-width:D-03" not in {i["id"] for i in d["issues"]})

        print("4. Reject and drift guard")
        r = call("POST", "/api/projects/sample-clinic/issues/door-clear-width:D-05/fix", {})["changeset"]
        call("POST", f"/api/changesets/{r}/reject")
        host.sync()
        check("rejected change never reaches the host", host.get("D-05", "clear_width_mm") == 711)
        s = call("POST", "/api/projects/sample-clinic/issues/stair-tread-min:S-01/fix", {})["changeset"]
        call("POST", f"/api/changesets/{s}/approve")
        host.set("S-01", "tread_mm", 260)  # someone edits the model after approval
        refused = host.sync()
        check("drifted change set refused", refused and refused[0][1] is False and "expected 254" in refused[0][2])
        check("tread untouched by Lintel", host.get("S-01", "tread_mm") == 260)

        print("5. Revert an applied change")
        rv = call("POST", f"/api/changesets/{cid}/revert")["changeset"]
        host.sync()
        check("door back to 760 mm", host.get("D-03", "clear_width_mm") == 760)
        statuses = {c["id"]: c["status"] for c in call("GET", "/api/projects/sample-clinic")["changesets"]}
        check("statuses: reverted / rejected / failed / applied",
              statuses[cid] == "reverted" and statuses[r] == "rejected" and statuses[s] == "failed" and statuses[rv] == "applied")

        print("6. Learn: a firm standard becomes a rule")
        call("POST", "/api/rules", {"name": "Firm door width", "kind": "min", "applies_to": "door", "prop": "clear_width_mm",
                                    "value": 900, "unit": "mm", "ref": "Firm standard", "fixable": "true"})
        d = call("GET", "/api/projects/sample-clinic")
        check("firm rule now flags 813/864 mm doors", sum(i["rule_name"] == "Firm door width" for i in d["issues"]) >= 4)

        print("7. Audit log")
        actions = [a["action"] for a in call("GET", "/api/audit?project=sample-clinic")["entries"]]
        actions += [a["action"] for a in call("GET", "/api/audit?action=rule")["entries"]]
        for a in ("model.snapshot", "changeset.proposed", "changeset.approved", "changeset.applied", "changeset.rejected",
                  "changeset.failed", "changeset.revert_requested", "rule.created"):
            check(f"logged {a}", a in actions)

        if live:
            print("8. Live Claude: ask the agent to fix the WC door")
            out = call("POST", "/api/projects/sample-clinic/chat",
                       {"message": "The accessible WC door looks narrow. Check it against our rules and propose a fix."})
            print("   Claude:", (out["replies"] or [""])[-1][:400].replace("\n", " "))
            check("agent proposed a change set", len(out["changesets"]) >= 1)
            cs = next(c for c in call("GET", "/api/projects/sample-clinic")["changesets"] if c["id"] == out["changesets"][0])
            check("agent change set waits for approval", cs["status"] == "proposed")
            host.sync()
            check("WC door unchanged until approved", host.get("D-05", "clear_width_mm") == 711)
        print("ALL OK")
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
