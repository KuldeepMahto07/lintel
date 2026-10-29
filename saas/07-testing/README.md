# 07 · Testing

**Status:** 🟡 In progress

| Sub-item | Status | Next action / summary |
|---|---|---|
| [Unit testing](unit-testing/) | ✅ | `tests/test_lintel.py`: 11 tests (checker, egress, state machine, drift guard, import, agent loop with a scripted Claude stand-in). |
| [Integration testing](integration-testing/) | 🟡 | `scripts/e2e.py`: server + fixture host over HTTP, ALL OK. `--live` (real Claude) is not yet verified: this machine's API key is rejected. 👤 Set a val |
| [Bug fixing](bug-fixing/) | 🟡 | Fixed during the build: |
| [Performance testing](performance-testing/) | ⬜ | 🤖 Snapshot size and check time on a 5,000-element model; move the plugin's HTTP call off the UI thread if a sync takes more than 100 ms. |
| [Beta testing](beta-testing/) | ⬜ | 👤 Recruit 10 pilot firms from the waitlist (stage 02). 🤖 Weekly usage report from the audit log. |
