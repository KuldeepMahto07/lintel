# Opportunity mapping

**Status:** ✅ Done

Part of [01 · Idea](../README.md) in the [Lintel SaaS plan](../../README.md).

| Opportunity | Pain | Lintel answer | Moat |
|---|---|---|---|
| Firm standards as code | Standards live in PDFs | A rules store: numeric parameters + section reference + fix recipe, importable from CSV/JSON | The firm's rule library becomes sticky data |
| Approval-gated edits | "Don't touch my model" fear | Every change is a diff; nothing applies until approved; one-click revert | Trust, plus a complete audit trail for QA/QC and insurers |
| Host-agnostic agent | Tools differ per office | One backend and agent; thin per-host plugins that only read and apply | Each new host is a small plugin |
| Code Q&A tied to the project | Generic answers ignore occupancy and layout | Dashboard chat grounded in the project's model snapshot + firm rules, citing section numbers | Project context |
| Audit log | No record of who changed what and why | Every proposal, approval, rejection and applied edit is logged with a reason | Business-tier feature |

**Legal design constraint.** ICC model codes (IBC, IRC, IECC) and ANSI A117.1 are copyrighted. Lintel never ships code text.
- Rules carry **numeric parameters + a section reference** (e.g. "IBC §1005.1 — verify against adopted edition").
- Users enter or import their local, adopted requirements.
- Starter values are labelled "verify", and the firm owns its rule set.
