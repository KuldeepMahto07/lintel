# Lintel testing strategy

What is tested, where, and what must pass before anything reaches production.

---

## 1. Test layers

| Layer | Tool | Scope | Runs |
|---|---|---|---|
| Unit | pytest | checker rules, egress graph, fix builder, state machine, entitlement checks, CSV import parsing | every push |
| API | pytest + FastAPI TestClient (SQLite and Postgres) | every endpoint: happy path, validation (422), state errors (409) | every push |
| Roles | pytest, table-driven | every write endpoint × every role → expected 2xx/403 | every push |
| Tenancy isolation | pytest | firm B calling every endpoint with firm A's ids → 404 | every push |
| Plugin protocol | `scripts/e2e.py` + fixture host | snapshot → fix → approve → apply → drift refused → revert | every push |
| Browser end-to-end | Playwright (`playwright-cli` skill) | the user flows in §2 against a running server | every push to main, and after each deploy |
| Visual / design | impeccable `detect` + screenshots at 1280 / 1024 / 390 px | no new anti-patterns, text ≥ 11 px, contrast | weekly and before release |
| Accessibility | axe-core via Playwright | no serious/critical violations | every push to main |
| AI agent | scripted fake client (unit) + a small live eval set (10 prompts) | tool calls are valid; agent never approves; answers cite rules | unit every push; live eval weekly |
| Load | k6 | 50 firms × 5 users polling + plugins at 2 s | before launch |

Coverage target: 85% lines on `backend/`, 100% of change-set state transitions.

---

## 2. End-to-end flows (Playwright)

1. **Sign-up and onboarding:** sign up → empty projects with checklist → "Try the sample clinic" → project shows 9 issues.
2. **Find and fix:** open issue "Door clear width, Exam 1" → plan zooms to the door → Propose fix → Approvals badge = 1 → Approve → fixture host applies → issue gone after sync → History shows APPLIED.
3. **Reject and drift:** propose → reject → never reaches the host. Propose → approve → edit the model in the fixture → host refuses → status FAILED with reason.
4. **Revert:** revert an applied change → the host applies the inverse → original REVERTED.
5. **Roles:** Member sees no Approve button; Member calling the approve API directly gets 403.
6. **Invites:** Admin invites → accept link → new member signs in to the same firm.
7. **Rules:** import the CSV template → new rule flags matching doors → disable it → flags gone.
8. **Plugin tokens:** create token → fixture host syncs with it → revoke → next sync gets 401.
9. **Chat (fake model):** ask "which doors are too narrow?" → assistant proposes a change set → inline card → approve.
10. **Billing (Stripe test mode):** Free firm hits Approve → upgrade prompt → checkout with test card `4242…` → webhook → plan Pro → Approve works.

---

## 3. Fixtures

- `samples/clinic.json`: the standard model (19 elements, 9 issues with starter rules).
- Factory helpers: `make_firm(role=…)`, `make_user(firm, role)`, `make_project(firm, sample=True)`, `make_token(user)`.
- The fake Claude client (already in `tests/test_lintel.py`) for agent tests; no network calls in CI.

---

## 4. Release gate (all must pass)

- [ ] Unit, API, roles and isolation tests green on SQLite **and** Postgres
- [ ] `scripts/e2e.py` ALL OK
- [ ] Playwright flows 1–9 green (10 when billing is live)
- [ ] axe: 0 serious/critical
- [ ] impeccable detect: no new findings compared with the last release
- [ ] Migrations dry run against a copy of production
- [ ] Smoke test after deploy green

---

## 5. Manual checks before launch

- Rhino 8 plugin on a real model (👤 needs Rhino): sync, fix, approve, Ctrl+Z undoes the Lintel edit.
- Password reset email arrives and the link works once.
- Invite email arrives; an expired link shows a clear message.
- Billing portal: change seats, cancel, resume.
