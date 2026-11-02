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

## Web app build (2026-11-03)
Built from the docs in this folder: accounts and firms, sessions with CSRF, five roles enforced on the server, invites, personal plugin tokens (hashed, revocable), plan entitlements, two-approval mode, comments, project rule overrides, audit filters and CSV, chat over server-sent events, Stripe checkout/webhook code, and the drawing-sheet web app at `/app`.

| Check | Result |
|---|---|
| `pytest -q tests`: core flows, sign-up/login/reset, CSRF, the role matrix (every write × every role), firm isolation (firm B gets 404 on firm A's ids), invites, tokens, plan limits, two approvals, webhook signature | 47 passed |
| `scripts/e2e.py`: sign up → personal token → fixture host over HTTP → propose → approve → applied → reject → drift refused → revert → firm rule → audit | ALL OK |
| Browser (preview on :8022): sign up → onboarding → sample clinic → issue zooms the plan → propose → approve → applied; model, chat (not set up), rules, audit, invite link, token shown once; 1024 px layout | Works |
| Postgres (`DATABASE_URL`) | **Not run.** Same SQL; needs a Neon database |
| Stripe checkout and Resend email | **Not run.** Need 👤 accounts and keys |
| Playwright suite, axe, Rhino 8 | **Not done** |
