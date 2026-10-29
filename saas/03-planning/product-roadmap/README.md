# Product roadmap

**Status:** ✅ Drafted

Part of [03 · Planning](../README.md) in the [Lintel SaaS plan](../../README.md).

| Phase | Scope | Exit criterion |
|---|---|---|
| **0. MVP** (this session) | Local backend + dashboard + agent; Rhino 8 plugin (Python 3) with a chat panel; fixture host for tests; 6 rule types; approval-gated diffs; audit log; firm rules | End-to-end run: flag → propose → approve → applied → logged |
| **1. Pilot** | Installer (yak package), per-firm API token, hosted backend, waitlist pilots | 10 firms weekly active |
| **2. Second host** | SketchUp (Ruby `HtmlDialog` + IFC classifier) or Revit (C# + WebView2), chosen by the stage 02 host split | Same e2e on the second host |
| **3. Team** | Accounts, firms, roles, shared approval queue, SSO (Business tier) | First Business-tier customer |
| **4. Depth** | IFC import, travel distance on real paths, accessibility clearances, rule packs per jurisdiction (user-supplied), learning firm standards from accepted/rejected fixes | Retention ≥ 80% at month 3 |
