# Lintel web app: functional specification

**Status:** built 2026-11-03 except Postgres (written, not run), Stripe and Resend (need 🔑 accounts), the Rhino run (needs 🔑 Rhino) and the Playwright suite. See [plan.md](plan.md).
**Goal:** turn today's single-user demo into a web app that firms can actually use: real accounts, saved data, team approvals, a working CAD plugin connection, and the drawing-sheet look of lintel-arc.

Legend: ✅ exists today · 🆕 to build · 🔑 needs an external account or key

---

## 1. What Lintel does

Lintel checks architectural drawings against a firm's own rules, proposes fixes, and changes the drawing only after a person approves. Every decision is logged.

| Problem | What Lintel does |
|---|---|
| Code and standards mistakes are found late (plan check, site) | Checks every model sync against the firm's rules and flags issues with the rule, the measured value and the code reference |
| Checks are manual and repetitive | Runs checks automatically; one click proposes the fix |
| Office standards live in a PDF | Rules live in the app: number + scope + reference, editable and importable |
| Fixes are the same small edits over and over | Drafts the edit as a before/after change; the plugin applies it as one undo step |
| AI chat can't see the drawing | Chat answers from the actual model and can draft changes |
| No record of who changed what | Full audit log; any applied change can be reverted |

**Hard rule:** neither the AI nor the system applies a change on its own. Only a person with approval rights can approve.

**Codes:** Lintel never stores building-code text. A rule is a number plus a section reference ("verify against your adopted edition"). Firms enter or import their own.

---

## 2. Users and roles

| Role | Can |
|---|---|
| **Owner** | Everything below, plus billing, delete firm, transfer ownership |
| **Admin** | Invite/remove members, set roles, manage rules and plugin tokens |
| **Approver** | Approve/reject/revert change sets, propose fixes, chat |
| **Member** | View projects, propose fixes, chat, comment |
| **Viewer** | Read-only |

A user belongs to one or more **firms** (workspaces). Everything (projects, rules, audit) is scoped to a firm.

---

## 3. Features and acceptance criteria

### 3.1 Accounts and firms 🆕
- Sign up with email + password (hashed with argon2/bcrypt), sign in, sign out, reset password by email (🔑 email provider).
- First sign-up creates a firm; owners invite teammates by email; invite links expire after 7 days.
- Sessions: secure HTTP-only cookie, 30-day expiry, CSRF token on every write.
- **Done when:** two users in one firm see the same projects; a user in another firm sees none of them; a viewer gets 403 on any write.

### 3.2 Projects ✅ (single-user) → 🆕 (per firm)
- Project list as a grid of cells: name, host app, last sync, open issues, waiting approvals.
- Create a project manually or automatically on first plugin sync; rename; archive.
- **Done when:** projects persist across restarts and deploys; archived projects are hidden but restorable.

### 3.3 Model sync (plugin API) ✅ → 🆕 per-user tokens
- The CAD plugin sends snapshots: `{id, type, props, geom}` per element (rooms, doors, stairs, walls) in mm.
- Each user creates personal plugin tokens in Settings → Plugins (shown once, revocable, last-used time).
- The plugin polls for approved change sets, applies them all-or-nothing with the drift guard, and reports results.
- **Done when:** a revoked token gets 401 within one request; a drifted change set is marked failed with the reason.

### 3.4 Rule checks ✅
- Checks: door clear width, corridor width, stair riser max, stair tread min, room area by use, exit travel distance (door-graph approximation).
- 🆕 per-project overrides (e.g. a sprinklered building uses a longer travel distance).
- 🆕 check presets the firm can switch on per project (Residential, Office, Healthcare starter sets, numbers only).
- **Done when:** changing a rule value re-runs checks on the next page load and the issue list updates.

### 3.5 Issues and plan view ✅ basic → 🆕 full workspace
- Issue list with severity, rule, measured value, required value, reference, element.
- Plan canvas: rooms, doors, stairs, walls drawn from the snapshot; flagged elements in orange; click an issue to zoom to it; click an element to see its properties.
- 🆕 CAD crosshair cursor with live X/Y in mm, ruler ticks on the canvas frame, drag a box to select elements and list their issues.
- **Done when:** every issue can be located on the plan in one click.

### 3.6 Change sets (propose → approve → apply) ✅
- Propose a fix from an issue (deterministic) or from chat (AI). Before/after table per property.
- Approve / reject (Approver+), revert applied changes, statuses: proposed, approved, applied, failed, rejected, reverted.
- 🆕 comments on a change set; 🆕 "requires two approvals" option per firm.
- **Done when:** a Member cannot approve; an Approver can; an applied change can be reverted and the revert is applied by the plugin.

### 3.7 Firm rules ✅ → 🆕 per firm
- List, add, edit, disable, delete; import CSV/JSON; export JSON. Rules the AI proposes arrive as "proposed" until an Admin activates them.
- **Done when:** importing the CSV template adds rules that immediately flag matching elements.

### 3.8 Assistant (chat) ✅ → 🆕 per user
- Chat per project, answers from the model, cites rule references, can propose change sets and rules, never approves.
- 🆕 streaming replies; 🆕 usage counter per firm (for plan limits).
- 🔑 `ANTHROPIC_API_KEY` in the server environment.
- **Done when:** asking "which doors are too narrow?" lists the right doors and offers a change set.

### 3.9 Audit log ✅ → 🆕 filters and export
- Every snapshot, proposal, decision, apply, revert, rule change, invite and sign-in, with who and when.
- 🆕 filter by project, person and action; export CSV.

### 3.10 Settings 🆕
- Profile, firm name, members and roles, invites, plugin tokens, danger zone.
- Billing placeholder; real payments later (🔑 merchant account).

### 3.11 Marketing site (removed 2026-11-03)
- Removed. `/` and old `/site/` links redirect to `/app`. The `/api/waitlist` endpoint remains for a future site.

---

## 4. Screens (all in the drawing-sheet theme, section 7)

| Screen | Route | Layout |
|---|---|---|
| Sign in / Sign up / Reset | `/login`, `/signup`, `/reset` | Centred card on the paper sheet, ruler frame around the page |
| Projects | `/app` | Header of grid cells (Projects, Rules, Audit, Settings, account); project cards as cells with mono meta rows |
| Project workspace | `/app/p/:id` | 3 columns: issues list · plan canvas with crosshair and rulers · inspector (element props or change-set diff); tabs for Approvals, History, Chat |
| Approvals queue | `/app/p/:id/approvals` and `/app/approvals` (all projects) | Rows of change sets with before/after, Approve/Reject buttons |
| Rules | `/app/rules` | Table of rules, edit drawer, import/export |
| Audit | `/app/audit` | Filterable table, CSV export |
| Settings | `/app/settings/*` | Profile, Firm, Members, Plugins (tokens), Billing |
| Plugin connect | `/app/settings/plugins` | Create token, copy once, setup steps for Rhino |

---

## 5. Data model (Postgres) 🆕

```
users(id, email unique, name, password_hash, created_at, last_login_at)
firms(id, name, plan, created_at)
memberships(user_id, firm_id, role, created_at)          -- role: owner|admin|approver|member|viewer
invites(id, firm_id, email, role, token_hash, expires_at, accepted_at)
sessions(id, user_id, firm_id, expires_at, csrf)
plugin_tokens(id, user_id, firm_id, name, token_hash, last_used_at, revoked_at)
projects(id, firm_id, name, host, archived_at, created_at)
snapshots(id, project_id, host, taken_at, elements jsonb)
rules(id, firm_id, data jsonb, status, created_by, created_at)
project_rule_overrides(project_id, rule_id, value, enabled)
changesets(id, project_id, title, reason, ops jsonb, status, source, rule_id, reverts,
           created_by, decided_by, decided_at, error, created_at, updated_at)
comments(id, changeset_id, user_id, body, created_at)
chat_messages(id, project_id, user_id, messages jsonb, updated_at)
audit(id, firm_id, project_id, actor, action, target, detail jsonb, at)
waitlist(id, email unique, data jsonb, at)
```
Existing SQLite stays for local runs; Postgres is used when `DATABASE_URL` is set.

---

## 6. API (all JSON, all scoped to the signed-in firm)

| Area | Endpoints |
|---|---|
| Auth 🆕 | `POST /api/auth/signup`, `/login`, `/logout`, `/reset/request`, `/reset/confirm`; `GET /api/me` |
| Firm 🆕 | `GET/PATCH /api/firm`; `GET /api/members`; `PATCH/DELETE /api/members/:id`; `POST /api/invites`; `POST /api/invites/:token/accept` |
| Tokens 🆕 | `GET/POST /api/tokens`; `DELETE /api/tokens/:id` |
| Projects | `GET /api/projects` ✅; `POST /api/projects` 🆕; `GET/PATCH /api/projects/:id` ✅/🆕 |
| Issues/fixes ✅ | `POST /api/projects/:id/issues/:iid/fix` |
| Change sets | `POST /api/changesets/:id/{approve,reject,revert}` ✅; `GET /api/approvals` 🆕; `POST /api/changesets/:id/comments` 🆕 |
| Rules ✅ | `GET/POST /api/rules`, `POST /api/rules/:id/status`, `DELETE /api/rules/:id`, `POST /api/rules/import`, `GET /api/rules/export`; overrides 🆕 |
| Chat ✅ | `GET/POST /api/projects/:id/chat` (🆕 streaming) |
| Audit | `GET /api/audit` ✅ (🆕 filters, `?format=csv`) |
| Plugin ✅ | `POST /api/plugin/snapshot`, `GET /api/plugin/pending`, `POST /api/plugin/result` (🆕 per-user token) |

Errors: `401` not signed in, `403` role too low, `404` other firm's data (never reveal it exists), `409` invalid state, `422` invalid input.

---

## 7. Theme: the drawing sheet

Taken from the lintel-arc main page's look and applied to an app. Layouts are new and built for a working tool.

| Token | Value |
|---|---|
| Paper (background) | `#f2f1eb` with a faint paper grain |
| Ink (text, lines) | `#282828`; secondary `rgba(40,40,40,.72)`; muted `rgba(40,40,40,.64)` (meets contrast) |
| Hairlines | `rgba(40,40,40,.18)` and `.32` |
| Accent | `#fa3600`: issues, primary actions, focus rings, cursor |
| Success | ink-filled check (no green, keeps the palette) |
| Display font | Schibsted Grotesk 700, uppercase, tight tracking |
| Labels / data | Geist Mono 11–13px, uppercase labels, tabular numbers for measurements |
| Body | Schibsted Grotesk 15px |

Components:
- **Header:** a row of bordered cells (logo · nav cells · account cell). A cell fills ink on hover; dropdowns wipe down.
- **Sheet frame:** ruler ticks along the main canvas edges, "+" corner marks.
- **Cards:** bordered cells, mono meta rows, no shadows, no rounded corners.
- **Buttons:** bordered box with mono label and arrow. The fill rises from the bottom on hover. Primary is the accent fill.
- **Issue marker:** orange square with a mono number; selected = enlarged with an orange outline.
- **Change-set card:** orange header strip, before (struck through) → after (bold) table.
- **Cursor:** on the plan canvas only, crosshair lines plus X/Y readout in mm. A normal cursor everywhere else, for usability.
- **Motion:** short (100–300ms) reveals and slides. No preloader, no scroll-jacking or pinning in the app (they slow down work). `prefers-reduced-motion` respected.
- **Accessibility:** text at least 11px, contrast at least 4.5:1 for body text, every action reachable by keyboard, visible focus.

---

## 8. "Actually works": requirements

| Area | Requirement |
|---|---|
| Persistence | Postgres in production (🔑 create a Neon/Supabase database, free tier); data survives deploys and cold starts |
| Hosting | Vercel (already connected to GitHub, auto-deploy on push) |
| Security | Hashed passwords, HTTP-only secure cookies, CSRF, per-firm data isolation on every query, rate limits on login and plugin endpoints, tokens stored as hashes |
| Secrets | `DATABASE_URL`, `ANTHROPIC_API_KEY`, `SESSION_SECRET` (+ `RESEND_API_KEY` for email) in Vercel env vars (🔑 ) |
| Tests | Unit tests for checks and state machine (✅ 13 today); 🆕 auth and firm-isolation tests; 🆕 end-to-end browser test of sign up → sync → fix → approve → applied |
| Plugin | Rhino 8 plugin connects with a personal token (🔑 Rhino install for the first real test) |

---

## 9. Build order

| # | Milestone | Done when |
|---|---|---|
| 1 | Postgres + accounts + firms + sessions | Sign up, sign in, two firms isolated (tests) |
| 2 | Theme + app shell | All existing screens restyled in the drawing-sheet theme |
| 3 | Project workspace | 3-column layout, plan canvas with crosshair, inspector, approvals tab |
| 4 | Team | Invites, roles enforced on every write, all-projects approval queue |
| 5 | Plugin tokens | Rhino plugin syncs with a personal token; revocation works |
| 6 | Rules overrides + presets, audit filters/CSV, chat streaming | Acceptance criteria in section 3 |
| 7 | Deploy + end-to-end test | Live on Vercel with Postgres; e2e test passes against production |

Out of scope for this build: payments, SSO, SketchUp/Revit plugins, IFC import, mobile app.
