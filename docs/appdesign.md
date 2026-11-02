# Lintel app design: screens, flows and states

Companion to [app-spec.md](app-spec.md) (what the app does) and [style.md](style.md) (how it looks).
This file says **what is on each screen, how people move between them, and what every state looks like.**

---

## 1. Information architecture

```
lintel.app
├─ /                     marketing site (public)
├─ /login  /signup  /reset  /invite/:token     auth (public)
└─ /app                  signed-in app (one firm at a time)
   ├─ Projects           /app
   │  └─ Project         /app/p/:id
   │     ├─ Issues       (default tab)
   │     ├─ Approvals    /app/p/:id/approvals
   │     ├─ History      /app/p/:id/history
   │     ├─ Model        /app/p/:id/model
   │     └─ Chat         /app/p/:id/chat
   ├─ Approvals (all)    /app/approvals
   ├─ Rules              /app/rules
   ├─ Audit              /app/audit
   └─ Settings           /app/settings
      ├─ Profile  ├─ Firm  ├─ Members  ├─ Plugins  └─ Billing
```

Global elements on every `/app` page:
- **Header row of cells:** logo · Projects · Approvals (badge with count) · Rules · Audit · Settings · firm switcher · account cell.
- **Command bar:** `Ctrl/⌘ K` to jump to a project, rule or setting.
- **Toast area:** bottom right, ink box, 4 s, never covers primary buttons.

---

## 2. Screens

Wireframes use cells: `┃` = hairline border, `▣` = accent (orange) element.

### 2.1 Sign up / Sign in
```
┌──────────────────────────────────────────────────────────┐ ruler ticks on all edges
│ +                                                      + │
│        LINTEL                                            │
│        CREATE YOUR FIRM                                  │
│        ┌───────────────────────────────┐                 │
│        │ NAME            [            ]│                 │
│        │ WORK EMAIL      [            ]│                 │
│        │ PASSWORD        [            ]│  ≥ 10 chars     │
│        │ FIRM NAME       [            ]│                 │
│        │ [▣ CREATE ACCOUNT        →]   │                 │
│        └───────────────────────────────┘                 │
│        Already have an account? Sign in                  │
│ +                                                      + │
└──────────────────────────────────────────────────────────┘
```
- Sign in: email, password, "Forgot password", the Sign in button.
- Errors appear under the field in accent mono text ("Email already in use"). Never clear the fields on error.
- After sign-up: the empty Projects page with the onboarding checklist (§3.1).

### 2.2 Projects
```
┃ LINTEL ┃ PROJECTS ┃ APPROVALS ③ ┃ RULES ┃ AUDIT ┃ SETTINGS ┃ STUDIO NORTH ▾ ┃ AK ┃
┃ PROJECTS                                   [+ NEW PROJECT] [CONNECT RHINO →] ┃
┃ ┌─────────────────┐┌─────────────────┐┌─────────────────┐                    ┃
┃ │ RHINO8   [01]   ││ RHINO8   [02]   ││ MANUAL   [03]   │                    ┃
┃ │ CLINIC GF       ││ RESIDENCE 04    ││ STUDIO FIT-OUT  │                    ┃
┃ │ ▣ 8 ISSUES      ││ 0 ISSUES        ││ 2 ISSUES        │                    ┃
┃ │ 3 AWAITING      ││ —               ││ 1 AWAITING      │                    ┃
┃ │ SYNCED 2 MIN AGO││ SYNCED YESTERDAY││ NEVER SYNCED    │                    ┃
┃ └─────────────────┘└─────────────────┘└─────────────────┘                    ┃
```
- Sort: last synced (default) · name · most issues. Filter: has issues, awaiting approval, archived.
- A card menu (⋯): rename, archive, copy project ID (for the plugin).

### 2.3 Project workspace (the core screen)
```
┃ CLINIC GF · RHINO8 · SYNCED 2 MIN AGO        [ISSUES][APPROVALS ③][HISTORY][MODEL][CHAT] ┃
┃ ISSUES (8)          ┃ + ┊┊┊┊┊┊┊┊┊┊┊┊┊ PLAN ┊┊┊┊┊┊┊┊┊┊┊┊ + ┃ INSPECTOR                ┃
┃ ▣ DOOR CLEAR WIDTH  ┃ ┊                                 ┊ ┃ D-03 · EXAM 1 DOOR       ┃
┃   Exam 1 door       ┃ ┊   ┌────┬─────┬──┐               ┊ ┃ CLEAR WIDTH   760 MM     ┃
┃   760 < 813 MM      ┃ ┊   │    │  ▣1 │  │   crosshair   ┊ ┃ REQUIRED      ≥ 813 MM   ┃
┃   §1010.1.1  [FIX→] ┃ ┊   ├────┼─────┼──┤   X 3 512 MM  ┊ ┃ RULE  DOOR CLEAR WIDTH   ┃
┃ ▣ CORRIDOR WIDTH    ┃ ┊   │      ▣2     │   Y 1 004 MM  ┊ ┃ REF   IBC §1010.1.1      ┃
┃   advice only       ┃ ┊   └─────────────┘               ┊ ┃ [▣ PROPOSE FIX →]        ┃
┃ ...                 ┃ + ┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊┊ + ┃                          ┃
```
- **Left (300 px):** issue list grouped by severity; each row shows rule, element, measured vs required, reference, and Fix or "advice only".
- **Centre (fluid):** plan canvas. Pan by dragging with space held or the middle mouse button; zoom with the wheel or pinch; `F` fits the view; `+`/`-` zoom. Flagged elements are drawn in accent. Drag a box to select (lists the issues inside).
- **Right (340 px):** inspector. Shows the selected element's properties, its issues and buttons, or the selected change set's diff.
- **Tabs** switch the left column's content; the plan and inspector stay.
- Below 1100 px the inspector becomes a drawer; below 760 px the plan hides behind a "Show plan" button (the app is desktop-first).

### 2.4 Approvals (per project and across all projects)
```
┃ AWAITING YOUR APPROVAL (3)                                         [APPROVE ALL ▾] ┃
┃ ┌▣ WIDEN EXAM 1 DOOR ──────────────────────── proposed by Priya · rule fix · 9:14 ┐ ┃
┃ │ ELEMENT        PROPERTY          BEFORE        AFTER                            │ ┃
┃ │ Exam 1 door    clear_width_mm    760 (struck)  813 (bold)                       │ ┃
┃ │ Reason: below 813 mm, IBC §1010.1.1 per your rule set                           │ ┃
┃ │ [▣ APPROVE →] [REJECT] [COMMENT]                         2 comments ▸           │ ┃
┃ └──────────────────────────────────────────────────────────────────────────────────┘ ┃
```
- Members see the cards without Approve/Reject, plus "waiting for an approver".
- "Approve all" opens a confirm listing every change set; never one-click.
- With the firm setting "two approvals" on, the first approval shows "1 of 2".

### 2.5 History
Timeline of change sets (applied, failed, rejected, reverted), newest first. Applied rows have Revert. Failed rows show the host's reason ("D-03 changed since the proposal; re-run checks").

### 2.6 Model
Tables of rooms, doors, stairs and walls with their properties and computed travel distance; search and sort; click a row to select it on the plan.

### 2.7 Chat
- Panel listing the conversation, with streamed replies, rule references as chips, and proposed change sets as inline cards with "Review".
- Suggested prompts when empty: "Which doors are under our minimum?", "Is stair 1 OK?", "Summarise open issues".
- Shows "Chat isn't set up" with a link to Settings when no AI key is configured.

### 2.8 Rules
```
┃ FIRM RULES (7)                    [+ ADD RULE] [IMPORT CSV/JSON] [EXPORT] ┃
┃ NAME                 APPLIES TO        CHECK              REF        STATUS ┃
┃ Door clear width     door              width ≥ 813 mm     §1010.1.1  ACTIVE ┃
┃ Exam room area       room use=exam     area ≥ 11 m²       Firm       ACTIVE ┃
┃ Door width (learned) door              width ≥ 900 mm     Firm       ▣ PROPOSED [ACTIVATE] ┃
```
- Add/edit opens a drawer: name, check type (minimum/maximum/travel distance), applies to, only where, property, value, unit, reference, severity, one-click fix yes/no.
- Import shows a preview table and the errors per row before saving.

### 2.9 Audit
Table: when · project · who · action · target · detail. Filters for project, person, action and date range; Export CSV.

### 2.10 Settings
- **Profile:** name, email, password change.
- **Firm:** name, two-approvals toggle, delete firm (type the name to confirm).
- **Members:** list with role dropdowns; invite by email with a role; pending invites with resend/cancel.
- **Plugins:** create token (name it, e.g. "Ana's Rhino"); the token is shown once with Copy; list with last used and Revoke; Rhino setup steps.
- **Billing:** current plan, seats used, upgrade (see [billing.md](billing.md)).

---

## 3. Key flows

### 3.1 First run (onboarding checklist on empty Projects)
1. ☐ Connect Rhino → Settings › Plugins → create token → install steps.
2. ☐ Or try the sample clinic → one click loads the sample project.
3. ☐ Review your rules → Rules page with the starter set.
4. ☐ Invite a teammate → Members.
5. ☐ Approve your first fix.
The checklist hides when all are done or dismissed.

### 3.2 Find and fix (core loop)
Sync (plugin) → issue appears → click → plan zooms to it → Propose fix → Approvals tab badge +1 → Approver opens card → Approve → plugin applies within ~2 s → History "applied" → issue disappears on the next sync.

### 3.3 Chat to change
Ask → assistant reads the model → answers with references → proposes a change set → inline card → Review → same approve flow.

### 3.4 Teach a standard
Say "we always use 900 mm doors" in chat → assistant proposes a rule → Rules shows it as PROPOSED → Admin activates it → the next check flags doors under 900 mm.

### 3.5 Invite and roles
Admin invites by email + role → email with a link → the invitee sets a password → joins the firm → the role limits their buttons.

### 3.6 Revert
History → Revert → confirm → an approved inverse change set is created → the plugin applies it → the original is marked reverted.

---

## 4. States (every screen must handle all of these)

| State | Treatment |
|---|---|
| **Loading** | Skeleton cells with a slow shimmer (none if reduced motion); keep the header live |
| **Empty** | One sentence on what this is, plus one primary action (e.g. "No projects yet. Connect Rhino or try the sample clinic.") |
| **Error (load)** | Inline cell: what failed in plain words + Retry. Never a blank page |
| **Error (action)** | Toast with the reason from the API (409 / 422 text); the button returns to normal |
| **No permission** | Hide buttons the role can't use; if a URL is opened directly, show "You don't have access to this" with a link back |
| **Offline / server down** | Banner "Can't reach Lintel. Retrying…" with exponential retry |
| **Stale model** | If the last sync is > 24 h old, the workspace header shows "Model last synced yesterday" in muted mono |
| **Plugin disconnected** | Approvals waiting > 2 min with no plugin poll: "No plugin connected. Approved changes will apply when Rhino reconnects." |

---

## 5. Interaction rules

- **Keyboard:**
  - Workspace: `J`/`K` next/previous issue, `F` fit plan, `A` approve the focused change set (Approver), `R` reject, `/` focus search, `Ctrl/⌘ K` command bar, `Esc` close drawer.
  - Every action also has a button.
- **Confirmations:** only for destructive or bulk actions (delete rule, revoke token, approve all, delete firm, revert). Single approve and reject don't ask.
- **Undo:** toasts for reject and rule disable carry "Undo" for 6 s.
- **Real-time:** project pages poll every 5 s for new snapshots and change-set status (server-sent events later).
- **Numbers:** measurements in mm with thin-space thousands (`3 512 MM`), areas in m² to one decimal, travel distance in m.

---

## 6. Copy guidelines

- Plain words, short sentences, no exclamation marks. Say what happened and what to do next.
- Name the rule and its reference; never quote code text. Always "verify against your adopted edition" on code-based rules.
- Buttons are verbs: Propose fix, Approve, Reject, Revert, Activate, Revoke.
- The AI is "the assistant" in the UI, never "Lintel decided". Approvals are always "you approved".

---

## 7. Responsive and accessibility

- Desktop first (≥ 1280 px). Usable down to 1024 px. Tablet and phone: read-only views of projects, approvals (with Approve/Reject) and audit.
- Keyboard focus is always visible (2 px accent outline).
- Plan canvas: every flagged element is also in the issue list, so screen-reader users never rely on the canvas.
- Colour is never the only signal: issue markers carry numbers, statuses carry words.
