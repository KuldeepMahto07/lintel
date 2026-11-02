# Lintel documentation

Everything needed to build Lintel as a fully working SaaS web app. Read in this order:

| # | Doc | What it answers |
|---|---|---|
| 1 | [app-spec.md](app-spec.md) | What the app does: features, roles, acceptance criteria, build order |
| 2 | [appdesign.md](appdesign.md) | Every screen, user flow, state (empty/loading/error), keyboard and copy rule |
| 3 | [style.md](style.md) | The drawing-sheet design system: tokens, type, layout, components, motion, accessibility |
| 4 | [architecture.md](architecture.md) | Stack, code layout, request flow, change-set lifecycle, environment variables |
| 5 | [data-and-api.md](data-and-api.md) | Postgres schema, plugin snapshot format, full API reference and error codes |
| 6 | [security.md](security.md) | Auth, sessions, role matrix, tenancy isolation, privacy, headers, incidents |
| 7 | [billing.md](billing.md) | Plans, limits the server enforces, Stripe flow, what the owner sets up |
| 8 | [operations.md](operations.md) | Environments, deploys, migrations, backups, monitoring, email, runbooks |
| 9 | [testing.md](testing.md) | Test layers, end-to-end flows, release gate |
| — | [plan.md](plan.md) | The approved MVP record and what was verified (2026-10-29) |

Legend used across the docs: ✅ exists today · 🆕 to build · 👤 needs the owner (accounts, keys, money).

**What the owner must provide before launch (👤):** a Neon Postgres database, `ANTHROPIC_API_KEY`, a Resend account + domain DNS, a Stripe (or Lemon Squeezy) account with products, a custom domain, the legal pages, and a Rhino 8 install for the first real plugin test.
