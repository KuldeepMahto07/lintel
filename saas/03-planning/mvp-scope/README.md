# MVP scope

**Status:** ✅ Approved 2026-10-29 (Rhino 8 first); see [`docs/plan.md`](../../../docs/plan.md)

Part of [03 · Planning](../README.md) in the [Lintel SaaS plan](../../README.md).

**In:**
1. **Dashboard (web, local):**
   - Projects list.
   - Project page with: issues, an approval queue (diff view, approve/reject), applied history with revert, and chat.
   - Firm rules page (list, edit, add, import JSON/CSV, export).
   - Audit log page.
2. **Backend:**
   - Projects, model snapshots, rule store, deterministic checker, change sets (proposed → approved → applied / rejected / failed / reverted), audit log, and a plugin API with token.
3. **Agent:**
   - Claude with tools: summarise the model, query elements, run checks, propose a change set, propose a firm rule, list rules.
   - It **cannot** apply anything. Only a human approval moves a change set forward.
4. **Rhino 8 plugin** (Python 3 script in a Rhino panel):
   - Reads layer and user-text conventions into a snapshot.
   - Shows the Lintel chat panel (WebView).
   - Polls for approved change sets, applies them inside one undo record, and reports results.
5. **Fixture host:**
   - A Python simulator of the same plugin protocol, with a sample model, for automated end-to-end tests when no host is installed.

**Out:** auth/teams/SSO, billing, hosting, other hosts, IFC, real path-finding (egress uses a door-graph approximation, documented).

**Building codes:**
- Starter rules are **numeric parameters + a section reference + "verify against your adopted code"**. No code text.
- Users edit or import their own.
