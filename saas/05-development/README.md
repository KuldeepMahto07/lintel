# 05 · Development

**Status:** 🟡 In progress

| Sub-item | Status | Next action / summary |
|---|---|---|
| [Frontend](frontend/) | ✅ | `web/`: vanilla JS single page, no build step. Hash routes; the panel mode is embedded in Rhino's Eto WebView. 🤖 Later: move to React + Vite when the  |
| [Backend](backend/) | ✅ | `backend/`: FastAPI. `checker.py` (rules + egress graph), `service.py` (change-set state machine with drift-safe ops), `agent.py` (Claude tool loop, p |
| [Apis](apis/) | ✅ | Dashboard API under `/api/projects`, `/api/changesets`, `/api/rules` (+ import/export) and `/api/audit`. The plugin API under `/api/plugin/{snapshot,p |
| [Database](database/) | ✅ | SQLite (`data/lintel.db`): projects, snapshots, rules, change sets, audit and chat. 🤖 Postgres plus migrations when it's hosted (stage 06). |
| [Authentication](authentication/) | ⬜ | MVP: local single user; plugin token in `data/plugin-token.txt`. 🤖 Hosted: email magic-link accounts, firms, roles (member, approver, admin), a per-se |
| [Integrations](integrations/) | 🟡 | Rhino 8 plugin written (`hosts/rhino/`), not yet run in Rhino. 🤖 Next hosts, in the order the stage 02 demand test picks: |
