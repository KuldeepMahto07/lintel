# Problem discovery

**Status:** ✅ Done (desk research; to be confirmed in interviews)

Part of [01 · Idea](../README.md) in the [Lintel SaaS plan](../../README.md).

## The problem
Architects and designers spend a lot of their week on work that is **rule-based and repetitive**. Design tools wait for instructions and give nothing back. The work falls into three groups:

1. **Code and standards checking.** Door clear widths, corridor widths, stair riser/tread, egress travel distance, minimum room areas, accessible clearances.
   - Today it's done by eye, on a printed checklist, or late in the process by a plan reviewer.
   - Errors found at permit stage cost redesign time and fees.
2. **Firm standards.** Every office has its own minimums: 900 mm doors, 1500 mm corridors, a bedroom of at least 9.5 m². They live in a PDF or in a BIM manager's head, so juniors miss them.
3. **Fiddly edits.** Widen 14 doors, re-space a stair, rename rooms to a convention. Each is a handful of clicks, repeated dozens of times.

## Why existing help falls short
- **Generic chatbots:** can't see the model, so you copy and paste dimensions and re-explain context.
- **Model checkers** (Solibri, Revit Model Review): report-only and Revit/IFC-centric. Rules are hard to author and they never fix anything.
- **Scripts** (Grasshopper, pyRevit, Dynamo): powerful but need a BIM specialist. No natural language and no audit trail of who changed what.

## Who feels it most
Small and mid-size firms (1–50 people) with no dedicated BIM manager. Their project architects are the QA layer.

## Hypotheses to validate (stage 02)
- H1: Project architects spend ≥ 2 h/week on compliance and standards checks they consider mechanical.
- H2: They'd trust an AI that **proposes** edits, but not one that edits without approval.
- H3: Firms want their **own** rules encoded, not just the model code.
- H4: Rhino and SketchUp users are underserved compared with Revit users.
