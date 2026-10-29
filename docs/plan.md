# Lintel: approved plan and verification record

## Approval (2026-10-29)
The owner answered in the session that built the MVP:
- **First host:** Rhino 8 ("Rhino 8 (Recommended)"). No CAD app is installed on the dev machine yet; the owner will install the Rhino 8 trial.
- **Stack and MVP scope:** "Approve as proposed".
  - Stack: FastAPI + SQLite + vanilla JS dashboard.
  - Agent: Claude `claude-sonnet-5-5` with tools that can only propose.
  - Plugins: a host-agnostic protocol plus a fixture host.
  - Scope: 6 rule checks, approval-gated diffs with revert, an audit log, and firm rules with JSON/CSV import. Name: Lintel.

Details: [`saas/03-planning`](../saas/03-planning/).

## What was verified (2026-10-29)
| Check | Result |
|---|---|
| `pytest -q tests`: checker, egress distance, plugin token, approve/reject/revert state machine, stair fix maths, drift guard, CSV import, agent loop with a scripted Claude stand-in | 11 passed |
| `scripts/e2e.py`: real server + fixture host over HTTP. Observe → propose (no change) → approve → applied in host file → reject never reaches host → drift refused → revert → firm rule → audit entries | ALL OK |
| Dashboard in the browser: issues with plan, Approve click → fixture applies → History shows applied + Revert; Rules page; host panel mode; chat error message | Works |
| `scripts/e2e.py --live` (real Claude call) | **Not verified.** The `ANTHROPIC_API_KEY` in this environment is rejected (401 invalid bearer token). Re-run with a valid key |
| Rhino plugin inside Rhino 8 | **Not verified.** Rhino isn't installed. The scripts compile; RhinoCommon calls are untested |

## Next steps
1. 👤 Install the Rhino 8 trial and set a valid `ANTHROPIC_API_KEY`.
2. 🤖 Run `build_sample.py`, then `lintel_rhino.py`, then the same flow as `e2e.py` by hand in Rhino. Fix whatever RhinoCommon disagrees with.
3. 🤖 Package as a yak plugin for Food4Rhino (stage 10).
