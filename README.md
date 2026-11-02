# Lintel

Lintel is a design-review assistant that works inside your CAD model:
- It reads rooms, doors, stairs and walls.
- It checks them against your firm's rules (each one a number plus the code section it comes from).
- It proposes fixes as a diff.
- It changes the model only after a person approves.
- Every proposal, decision and edit goes into an audit log.

It's an original product built after studying the public pages of heronaiapp.com (an agency concept site). See [`saas/01-idea/competitor-analysis`](saas/01-idea/competitor-analysis/).

**Status:** MVP. Rhino 8 is the first host. Verified end to end with the **fixture host** (a simulator of the same plugin protocol). The Rhino plugin is written but **not yet run inside Rhino**: Rhino isn't installed on the dev machine.

## Run

```
start.bat            → http://127.0.0.1:8002
```

- Set `ANTHROPIC_API_KEY` for the chat assistant. Everything else (checks, fixes, approvals, rules, audit) works without it.
- Optional: `LINTEL_MODEL` (default `claude-sonnet-5-5`), `LINTEL_DB`, `LINTEL_TOKEN`.

### Marketing site
`site/` is the public website: home with a live revision-cloud demo, assistant, dashboard, pricing, about, and a pilot sign-up form that posts to `/api/waitlist`. The design and copy are Lintel's own. Run `python siteuild.py` to build `site/public/` (start.bat does this), then open http://127.0.0.1:8002/site/. The output is static and can be deployed to any static host; the form needs the backend.

### Try it without CAD
```
.venv\Scripts\python hosts\fixture_host.py samples\clinic.json --watch
```
Open the dashboard, click **Propose fix** on an issue, then **Approve** under Approvals. The fixture host applies the change to `data/fixture-sample-clinic.json` on its next poll.

### Rhino 8
1. Start Lintel (`start.bat`).
2. In Rhino 8, create a new model in millimetres, then run `_-RunPythonScript "<this folder>\hosts\rhino\build_sample.py"` to draw the sample clinic. You can also draw your own using the convention below.
3. Run `_-RunPythonScript "<this folder>\hosts\rhino\lintel_rhino.py"`. A floating Lintel window opens beside the model. Run it again to disconnect.
4. Approved edits are applied inside one undo record each, so Ctrl+Z undoes a Lintel edit.

**Rhino model convention** (Rhino has no BIM objects):

| Layer | Objects | Attribute User Text |
|---|---|---|
| `Lintel::Rooms` | closed planar curves | `name`, `use` (corridor, exam, bedroom, office…), optional `clear_width_mm` |
| `Lintel::Doors` | `LintelDoor` block instances (1000 mm at scale 1) or any object | `name`, `clear_width_mm`, `exit` (true/false), optional `rooms` |
| `Lintel::Stairs` | any object | `name`, `riser_mm`, `tread_mm`, `risers`, `width_mm`, `total_rise_mm` |
| `Lintel::Walls` | curves | `thickness_mm`, `height_mm` |

## Hosted demo (Vercel)
Live: **https://lintel-ruddy-five.vercel.app** (dashboard at `/`, marketing site at `/site/`).

- The whole app runs as one Python function (`api/index.py`, `vercel.json`) in **demo mode** (`LINTEL_DEMO=1`, `backend/demo.py`).
- The database lives in the function's `/tmp`. It is re-seeded with the sample clinic on every cold start, so changes, rules and pilot sign-ups do **not** persist.
- No CAD plugin can stay connected to a serverless function, so a demo host applies approved change sets immediately (same drift guard, logged as `host:demo`).
- Chat needs `ANTHROPIC_API_KEY` set in the Vercel project's environment variables.
- `.vercelignore` keeps local data, tests, the private study build and the cloned repos out of the upload.

Deploy (build the marketing site first; the installed global CLI is too old for Vercel's API):
```
.venv\Scripts\python siteuild.py
npx vercel@latest deploy --prod
```
For real use, move the database to a hosted Postgres and run the backend somewhere long-lived so plugins can stay connected.

## Verify
```
.venv\Scripts\python -m pytest -q tests          # 11 tests
.venv\Scripts\python scripts\e2e.py              # server + fixture host over HTTP, prints ALL OK
.venv\Scripts\python scripts\e2e.py --live       # also has Claude propose a fix (needs a valid API key)
```

## How it fits together
- **`backend/`** (FastAPI + SQLite):
  - `checker.py`: deterministic rules and the egress door graph.
  - `service.py`: the change-set lifecycle (proposed → approved → applied/failed → reverted; or rejected).
  - `agent.py`: Claude with tools. It can read, check and *propose*, and has no approve or apply tool.
  - `app.py`: the API.
- **`web/`:** the dashboard (projects, issues with a plan view, approvals diff, history and revert, model tables, chat, firm rules with JSON/CSV import and export, audit log). `/?panel=<project>` is the compact view shown inside the CAD app.
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
- Single-user and local. There are no accounts yet; the plugin authenticates with a token in `data/plugin-token.txt`.
