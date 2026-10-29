# 06 · Infrastructure

**Status:** ⬜ Not started

| Sub-item | Status | Next action / summary |
|---|---|---|
| [Cloud hosting](cloud-hosting/) | ⬜ | 🤖 Pilot: one small VM or Fly.io/Railway app, managed Postgres and HTTPS. The plugin points `LINTEL_URL` at it. Keep a local mode for firms that won't  |
| [Devops](devops/) | ⬜ | 🤖 A Dockerfile, a `.env` template, and automated DB backups. |
| [Ci cd](ci-cd/) | ⬜ | 🤖 GitHub Actions: pytest + `scripts/e2e.py` on every push, and `py_compile` for the Rhino scripts. Push with the `gh` credential helper (see the works |
| [Monitoring](monitoring/) | ⬜ | 🤖 Error tracking (Sentry), uptime checks, and Claude token usage per firm (from `response.usage`) to price the credit top-ups. |
| [Security](security/) | 🟡 | Done: |
