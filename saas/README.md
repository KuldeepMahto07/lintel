# Lintel: SaaS lifecycle plan

**What Lintel is:** an assistant inside CAD/BIM tools.
- It reads the model and checks it against the firm's own rules (a number plus a code-section reference, never code text).
- It proposes fixes as a diff and edits only after a person approves.
- It logs every decision.

The first host is Rhino 8. Code: [`../backend`](../backend), [`../web`](../web), [`../hosts`](../hosts). Plan and verification: [`../docs/plan.md`](../docs/plan.md).

**Reference:** heronaiapp.com, which turned out to be an agency concept site (Bearplus) with no shipped product. Real competitors are UpCodes, Solibri and Revit Model Review. See [01-idea/competitor-analysis](01-idea/competitor-analysis/).

| # | Stage | Status | Next action |
|---|---|---|---|
| 01 | [Idea](01-idea/) | ✅ Done | 🤖 Firm up the market numbers (marketplace listing counts, forum complaints) |
| 02 | [Validation](02-validation/) | 🟡 In progress | 👤 Run 12–15 interviews with the script; 🤖 build the landing page with the MVP demo GIF; 👤 $300 ad test |
| 03 | [Planning](03-planning/) | ✅ Done | Stack, Rhino-first and MVP scope approved 2026-10-29 |
| 04 | [Design](04-design/) | 🟡 In progress | 🤖 Onboarding and team-approval wireframes; logo and dark panel theme |
| 05 | [Development](05-development/) | 🟡 In progress | SaaS web app built 2026-11-03 (accounts, firms, roles, tokens, workspace; see `docs/`). 👤 Install the Rhino 8 trial; 🤖 first real run of `hosts/rhino/lintel_rhino.py` with a personal token |
| 06 | [Infrastructure](06-infrastructure/) | ⬜ Not started | 🤖 CI running pytest + e2e; Dockerfile; hosted pilot backend |
| 07 | [Testing](07-testing/) | 🟡 In progress | 47 tests (roles, firm isolation, CSRF, plans) + e2e ALL OK. 🤖 Postgres run and Playwright flows; 👤 valid `ANTHROPIC_API_KEY`, then `e2e.py --live` |
| 08 | [Launch](08-launch/) | ⬜ Not started | Gate: 10 active pilots + Food4Rhino listing |
| 09 | [Acquisition](09-acquisition/) | ⬜ Not started | 🤖 SEO calculator pages per check |
| 10 | [Distribution](10-distribution/) | ⬜ Not started | 🤖 yak package → Food4Rhino; then SketchUp Extension Warehouse, Autodesk App Store |
| 11 | [Conversion](11-conversion/) | 🟡 In progress | Draft pricing: Free / Pro $39 per seat / Firm $99 per seat / Enterprise. 👤 Test the price in interviews |
| 12 | [Revenue](12-revenue/) | ⬜ Not started | 👤 Pick a merchant of record (Lemon Squeezy or Paddle) |
| 13 | [Analytics](13-analytics/) | ⬜ Not started | North star: approved fixes per active seat per week (the audit log already records the events) |
| 14 | [Retention](14-retention/) | 🟡 In progress | Onboarding checklist and "Try the sample clinic" are in the web app. 🤖 Weekly digest email |
| 15 | [Growth](15-growth/) | ⬜ Not started | Exportable QA report with a "Checked with Lintel" footer |
| 16 | [Scaling](16-scaling/) | ⬜ Not started | Not before product-market fit |

**Statuses:**
- ✅ **Done:** every sub-item is done.
- 🟡 **In progress:** at least one sub-item is done, partial or drafted.
- ⬜ **Not started:** nothing executed yet.

👤 the owner does it · 🤖 Claude does it. Each stage folder has a README with its sub-items. Last updated 2026-10-29.
