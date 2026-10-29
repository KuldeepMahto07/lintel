# Development plan

**Status:** ✅ Drafted

Part of [03 · Planning](../README.md) in the [Lintel SaaS plan](../../README.md).

| # | Task | Owner | Done when |
|---|---|---|---|
| 1 | Backend skeleton: store, projects, snapshots, audit | 🤖 | pytest green |
| 2 | Rule store + starter rules + checker (6 checks) | 🤖 | Fixture model yields the expected issues |
| 3 | Change sets: propose / approve / reject / apply-result / revert, with drift guard | 🤖 | State-machine tests green |
| 4 | Agent with tools (Claude), chat endpoint | 🤖 | Chat proposes a change set on the fixture model |
| 5 | Dashboard + host panel page | 🤖 | Manual browser run |
| 6 | Fixture host + e2e script | 🤖 | `scripts/e2e.py` prints ALL OK |
| 7 | Rhino 8 plugin + sample model builder script | 🤖 code, 👤 runs in Rhino | Same e2e inside Rhino |
| 8 | Stages 04–16 docs | 🤖 | Every stage has a Status line and next actions |
