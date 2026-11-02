# Lintel architecture

How the pieces fit: what runs where, how data moves, and which choices are fixed.
Features: [app-spec.md](app-spec.md) · Data and endpoints: [data-and-api.md](data-and-api.md) · Security: [security.md](security.md).

---

## 1. System overview

```
 ┌───────────────────┐      HTTPS + plugin token       ┌──────────────────────────────────────────┐
 │ CAD app (Rhino 8) │ ──── snapshot / poll / result ─▶│  Lintel backend (FastAPI, Python 3.12)   │
 │  lintel plugin    │ ◀─── approved change sets ───── │  ├─ auth & sessions   ├─ rule checker    │
 │  + WebView panel ─┼─────── /app (embedded) ────────▶│  ├─ change-set engine ├─ AI agent (Claude)│
 └───────────────────┘                                  │  ├─ audit log         ├─ billing hooks    │
                                                        └──────┬──────────────────────┬────────────┘
 ┌───────────────────┐      HTTPS + session cookie            │                      │
 │ Browser           │ ────── /app (dashboard) ──────────────▶│               ┌──────▼──────┐
 │                   │ ────── /  (marketing site) ───────────▶│               │ Anthropic API│
 └───────────────────┘                                  ┌──────▼──────┐        └─────────────┘
                                                        │  Postgres   │   + email provider (Resend)
                                                        │ (Neon)      │   + payments (Stripe/Lemon)
                                                        └─────────────┘
```

- **One backend** serves the dashboard, the marketing site, the plugin API and the AI agent.
- **The plugin is thin:** it reads the model, applies approved operations and shows the dashboard in a WebView. All logic lives on the server, so new checks ship without plugin updates.
- **The rule checker is deterministic** (plain Python). The AI explains and proposes; it never decides pass or fail, and never applies changes.

---

## 2. Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn | Exists today; async-ready; easy to test |
| Database | Postgres (Neon) in production; SQLite for local and tests | Persistent, JSONB for snapshots/ops, row filters per firm |
| DB access | `psycopg` 3 + small repository layer (no heavy ORM) | Keeps SQL visible; the store layer already exists |
| Migrations | Numbered SQL files in `backend/migrations/`, applied on deploy by a migrate command | Reviewable, no magic |
| Frontend | Server-served static app: vanilla JS modules + the CSS design system ([style.md](style.md)) | No build step today; can move to React + Vite later without API changes |
| Plan canvas | SVG rendered from snapshot geometry | Crisp at any zoom, selectable elements, easy hit-testing |
| AI | Anthropic SDK, Claude via tool use (`backend/agent.py`) | Tools map to read, check, propose; the approval gate lives on the server |
| Email | Resend (invites, password reset) | Simple API, free tier |
| Payments | Stripe Billing or Lemon Squeezy (merchant of record) | See [billing.md](billing.md) |
| Hosting | Vercel (Python function) now; a long-running host (Fly.io/Render) when real-time plugin push is needed | Already deployed and auto-deploying from GitHub |
| CI | GitHub Actions: tests + migrations dry run on every push | See [operations.md](operations.md) |

---

## 3. Code layout (target)

```
lintel/
├─ api/index.py              Vercel entry (ASGI app)
├─ backend/
│  ├─ app.py                 FastAPI app, routes mounted from routers/
│  ├─ routers/               auth.py, firm.py, projects.py, changesets.py, rules.py, chat.py, audit.py, plugin.py, billing.py
│  ├─ auth.py                password hashing, sessions, CSRF, role checks (Depends)
│  ├─ db.py                  connection pool; Postgres or SQLite by DATABASE_URL
│  ├─ repo/                  one module per table group; every query takes firm_id
│  ├─ checker.py             deterministic rules (exists)
│  ├─ service.py             change-set state machine (exists)
│  ├─ agent.py               Claude tool loop (exists)
│  ├─ demo.py                hosted demo mode (exists)
│  ├─ emails.py              invite / reset templates
│  └─ migrations/0001_init.sql …
├─ web/                      app shell, pages/, components/, styles/ (tokens.css, components.css)
├─ site/                     marketing site (exists)
├─ hosts/                    lintel_client.py, fixture_host.py, rhino/ (exist)
├─ tests/                    unit, api, isolation, e2e (Playwright)
└─ docs/                     this folder
```

---

## 4. Request flow

1. **Browser → `/app/...`:** static shell loads, calls `GET /api/me`. 401 → redirect to `/login`.
2. **Every API call:**
   1. The session cookie gives the user and the current firm.
   2. The role check runs as a FastAPI dependency.
   3. The repository runs the query with `firm_id` bound.
   4. The audit entry is written in the same transaction as the change.
3. **Plugin → `/api/plugin/*`:** the bearer token is hashed and looked up to give the user and firm; the project must belong to that firm.
4. **Checks** run on read (`GET /api/projects/:id`) against the latest snapshot and active rules. They're cheap (milliseconds); a cache keyed by snapshot id + rules version comes later if needed.

---

## 5. Change-set lifecycle (server-enforced)

```
proposed ──approve (Approver+)──▶ approved ──plugin result ok──▶ applied ──revert──▶ (new approved inverse) → reverted
    │                                  └──plugin result fail──▶ failed
    └──reject (Approver+)──▶ rejected
```
- Every op carries the `from` value; the plugin refuses the whole set if any value drifted.
- Two-approval mode: `approved` only after the second distinct approver.
- Only allow-listed properties are editable (door width, stair riser/tread/count, names); geometry changes are advice only.

---

## 6. Environments and configuration

| Variable | Local | Preview | Production |
|---|---|---|---|
| `DATABASE_URL` | unset → SQLite `data/lintel.db` | Neon branch DB | Neon main DB |
| `SESSION_SECRET` | dev default | set | set (32+ random bytes) |
| `ANTHROPIC_API_KEY` | optional | optional | required for chat |
| `LINTEL_MODEL` | default `claude-sonnet-5-5` | same | same |
| `RESEND_API_KEY`, `MAIL_FROM` | unset → emails printed to the console | set | set |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | unset | test keys | live keys |
| `LINTEL_DEMO` | 0 | 0 | 0 (1 only for the public demo deployment) |
| `APP_URL` | http://127.0.0.1:8002 | preview URL | production domain |

Secrets live only in Vercel environment variables, never in git.

---

## 7. Decisions and limits

- **Polling, not push, for plugins** (every 2 s) until the backend moves to a long-running host; then server-sent events.
- **Snapshots are stored whole** (JSONB, typically < 1 MB). Keep the last 50 per project; older ones pruned nightly.
- **Single region** at first (Neon + Vercel in the same region).
- **Plan rendering limit:** about 5 000 elements before switching to canvas/WebGL rendering.
