# Lintel

Lintel is a design-review assistant that works inside your CAD model:
- It reads rooms, doors, stairs and walls.
- It checks them against your firm's rules (each one a number plus the code section it comes from).
- It proposes fixes as a diff.
- It changes the model only after a person approves.
- Every proposal, decision and edit goes into an audit log.

It's an original product built after studying the public pages of heronaiapp.com (an agency concept site). See [`saas/01-idea/competitor-analysis`](saas/01-idea/competitor-analysis/).

**Status:** SaaS web app (2026-11-03): accounts, firms, roles, invites, personal plugin tokens, plan limits, and the drawing-sheet workspace. Rhino 8 is the first host. Verified end to end with the **fixture host** (a simulator of the same plugin protocol). The Rhino plugin is written but **not yet run inside Rhino**: Rhino isn't installed on the dev machine.

**Docs:** the full SaaS spec, app design, style guide, architecture, API, security, billing, operations and testing are in [`docs/`](docs/README.md).

## Run

```
start.bat            → http://127.0.0.1:8002/app
```

1. Open http://127.0.0.1:8002/signup and create your firm. New firms get 14 days of Pro.
2. Click **Try the sample clinic** to load a model with 9 issues. The built-in sample host applies approved changes at once.
3. To connect a CAD app, create a personal token in **Settings › Plugins**.

Configuration (all optional locally):
- `ANTHROPIC_API_KEY`: the chat assistant. Everything else (checks, fixes, approvals, rules, audit) works without it.
- `DATABASE_URL`: Postgres (production). Unset means SQLite at `LINTEL_DB` (default `data/lintel.db`). A database from the single-user MVP is kept: its old tables are renamed `*_v1`.
- `APP_URL`: the address used in invite and reset emails.
- `RESEND_API_KEY`, `MAIL_FROM`: email. Unset means emails print to the console, and the app shows invite links to copy.
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_{PRO,FIRM}_{MONTH,YEAR}`: payments (see `docs/billing.md`).
- `LINTEL_MODEL` (default `claude-sonnet-5-5`), `LINTEL_STAFF_TOKEN` (reads the waitlist via `GET /api/waitlist`).

### Try the plugin protocol without CAD
Create a token in **Settings › Plugins**, then:
```
set LINTEL_TOKEN=<your token>
.venv\Scripts\python hosts\fixture_host.py samples\clinic.json --watch
```
The project appears in the app. Click **Propose fix** on an issue, then **Approve**. The fixture host applies the change to `data/fixture-sample-clinic.json` on its next poll.

### Rhino 8
1. Start Lintel (`start.bat`), sign in, and create a plugin token in **Settings › Plugins**. Save it as `LINTEL_TOKEN` or in `data/plugin-token.txt`.
2. In Rhino 8, create a new model in millimetres, then run `_-RunPythonScript "<this folder>\hosts\rhino\build_sample.py"` to draw the sample clinic. You can also draw your own using the convention below.
3. Run `_-RunPythonScript "<this folder>\hosts\rhino\lintel_rhino.py"`. A floating Lintel window opens beside the model; sign in there once. Run it again to disconnect.
4. Approved edits are applied inside one undo record each, so Ctrl+Z undoes a Lintel edit.

**Rhino model convention** (Rhino has no BIM objects):

| Layer | Objects | Attribute User Text |
|---|---|---|
| `Lintel::Rooms` | closed planar curves | `name`, `use` (corridor, exam, bedroom, office…), optional `clear_width_mm` |
| `Lintel::Doors` | `LintelDoor` block instances (1000 mm at scale 1) or any object | `name`, `clear_width_mm`, `exit` (true/false), optional `rooms` |
| `Lintel::Stairs` | any object | `name`, `riser_mm`, `tread_mm`, `risers`, `width_mm`, `total_rise_mm` |
| `Lintel::Walls` | curves | `thickness_mm`, `height_mm` |

## Hosted demo (Vercel)
Live: **https://lintel-ruddy-five.vercel.app** (the app at `/app`; `/` and old `/site/` links go there).

- The whole app runs as one Python function (`api/index.py`, `vercel.json`) in **demo mode** (`LINTEL_DEMO=1`, `backend/demo.py`).
- The database lives in the function's `/tmp` and is wiped on cold starts, so accounts, projects and pilot sign-ups do **not** persist. Set `DATABASE_URL` to a Neon Postgres database for real use.
- No CAD plugin can stay connected to a serverless function, so the sample host applies approved change sets immediately (same drift guard, logged as `host:sample`).
- Chat needs `ANTHROPIC_API_KEY` set in the Vercel project's environment variables.
- `.vercelignore` keeps local data, tests, the private study build and the cloned repos out of the upload.

Deploy (the installed global CLI is too old for Vercel's API):
```
npx vercel@latest deploy --prod
```
For real use, move the database to a hosted Postgres and run the backend somewhere long-lived so plugins can stay connected.

## Verify
```
.venv\Scripts\python -m pytest -q tests          # 47 tests: core, accounts, roles, firm isolation, plans
.venv\Scripts\python scripts\e2e.py              # sign up + token + server + fixture host over HTTP, prints ALL OK
.venv\Scripts\python scripts\preview.py          # the app on :8022 with a throwaway database, for UI checks
.venv\Scripts\python scripts\e2e.py --live       # also has Claude propose a fix (needs a valid API key)
```

## How it fits together
- **`backend/`** (FastAPI; SQLite locally, Postgres in production):
  - `db.py` + `migrations/`: the connection and numbered SQL migrations.
  - `store.py`: the repository layer; every query is scoped by firm.
  - `auth.py`: argon2id passwords, sessions, CSRF, role checks, rate limits. `plans.py`: plan entitlements.
  - `checker.py`: deterministic rules and the egress door graph.
  - `service.py`: the change-set lifecycle (proposed → approved → applied/failed → reverted; or rejected), with two-approval mode.
  - `agent.py`: Claude with tools. It can read, check and *propose*, and has no approve or apply tool. Replies stream as server-sent events.
  - `routers/`: the API (`docs/data-and-api.md`). `app.py` mounts them, sets security headers and serves the pages.
- **`web/`:** the drawing-sheet app (`docs/style.md`), vanilla JS modules with no build step: sign-in, projects with onboarding, the project workspace (issues · plan canvas with crosshair, rulers and box select · inspector; approvals, history, model and chat tabs), cross-project approvals, rules, audit and settings. `/?panel=<project>` opens the compact view shown inside the CAD app.
- **`hosts/`:**
  - `lintel_client.py`: the host-agnostic protocol, with the all-or-nothing apply and drift guard.
  - `fixture_host.py`: the test host.
  - `rhino/`: the Rhino 8 plugin and the sample builder.

### Building codes
- Lintel ships no code text. A rule is a number, a scope and a reference such as "IBC §1010.1.1 (verify against your adopted edition)".
- Starter values are examples. Confirm each one against the edition and amendments your jurisdiction adopted, or replace them with your own.

### Known limits
- Egress distance is approximate: straight lines between doors across each room. Corridor width and room area are flagged with advice; Lintel won't guess wall moves.
- The plugin polls every 2 s on Rhino's UI thread.
- The Postgres path is written but hasn't been run against a real database yet. Stripe checkout and Resend email are wired but need accounts.
- Rate limits are in memory, per server process.
