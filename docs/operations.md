# Lintel operations: deploy, migrate, monitor, back up

---

## 1. Environments

| Env | URL | Database | Deploys when |
|---|---|---|---|
| Local | http://127.0.0.1:8002 | SQLite `data/lintel.db` | `start.bat` |
| Preview | Vercel preview URL (login-protected) | Neon branch per PR | every push to a non-main branch |
| Production | lintel-ruddy-five.vercel.app → custom domain later | Neon main | every push to `main` (GitHub ↔ Vercel connected) |
| Public demo | separate Vercel project, `LINTEL_DEMO=1` | `/tmp` SQLite, resets | manual |

---

## 2. Deploy checklist

1. CI green on the branch (tests, migrations dry run, secret scan, `pip-audit`).
2. Merge to `main` → Vercel builds and deploys automatically.
3. The migration step runs `python -m backend.migrate` against `DATABASE_URL` before the new version takes traffic. Migrations must be backward-compatible (add columns, never rename or drop in the same release).
4. Smoke test (scripted in CI after deploy):
   1. `GET /api/health` returns `{ok:true, db:"ok"}`.
   2. Sign in as the smoke-test user.
   3. Load the sample project.
   4. Propose → approve → apply (via the fixture host).
5. On failure: Vercel "Instant Rollback" to the previous deployment. The database stays compatible because of rule 3.

---

## 3. Database

- **Neon Postgres**, same region as Vercel functions.
- Point-in-time restore (7 days on the free tier, 30 on paid) plus a nightly `pg_dump` to private storage (GitHub Actions → encrypted artifact or S3).
- **Connection pooling:** use Neon's pooled connection string (`-pooler` host) from serverless functions.
- **Jobs (nightly, GitHub Actions cron):** prune snapshots beyond 50 per project; delete expired sessions, invites and resets; purge firms deleted more than 30 days ago.

---

## 4. Monitoring

| What | Tool | Alert when |
|---|---|---|
| Uptime | Better Stack / UptimeRobot on `/api/health` | down 2 min |
| Errors | Sentry (Python + browser) | new issue, or > 10 events/min |
| Performance | Vercel analytics; p95 per route in logs | p95 > 1.5 s on `/api/projects/:id` |
| Plugin health | count of `plugin/pending` polls per hour | 0 polls for an active firm for 24 h (onboarding nudge) |
| AI cost | `usage` table, daily total tokens | > budget for the day |
| Billing | Stripe webhook failures | any failure |

**Logs:** structured JSON (`ts, level, route, status, ms, user_id, firm_id, request_id`); no tokens, passwords or chat text.

---

## 5. Email

- Resend with a verified domain (SPF, DKIM, DMARC records added in your DNS 🔑).
- Templates: invite, password reset, trial ending (3 days before), payment failed, weekly digest (open issues and approvals, opt-out).
- Locally emails print to the console.

---

## 6. Support

- In-app "Report a problem" adds the page, firm id and request id (no model data unless the user ticks "include current project").
- Shared inbox `support@<domain>`; response target 1 business day (Pro), 4 hours (Firm).

---

## 7. Runbooks

| Situation | Steps |
|---|---|
| Site down | Check the Vercel status page and the Neon status page → roll back the last deploy → check `/api/health` |
| Database migration failed | Deploy is blocked automatically; fix the migration in a new PR; never edit an applied migration |
| Leaked plugin token | User revokes it in Settings › Plugins; an admin can revoke all of a user's tokens |
| Leaked `SESSION_SECRET` | Rotate it in Vercel → redeploy (all users signed out) |
| AI provider outage | Chat shows "The assistant is unavailable"; checks, fixes and approvals keep working (they don't use AI) |
| Restore deleted data | Neon point-in-time branch at the time before deletion → copy rows back with a script |
