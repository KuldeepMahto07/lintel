# Niche selection

**Status:** ✅ Done

Part of [01 · Idea](../README.md) in the [Lintel SaaS plan](../../README.md).

## Beachhead
**Small architecture and interiors firms (1–20 people) who design in Rhino or SketchUp and have no BIM manager.** They do residential, multifamily and small commercial work.

Why this niche:
- **Underserved:** most model checkers target Revit/IFC and enterprise budgets.
- **Easier to ship:**
  - Rhino's Python and RhinoCommon API is free to develop against and Rhino has a 90-day trial.
  - SketchUp's Ruby API is free, and its IFC classifier gives semantic tags (IfcDoor, IfcSpace, IfcStair).
  - Revit needs a licence and a C# add-in.
- **Fast feedback:** small firms decide in a week. No procurement.

## Expansion path
1. Rhino → SketchUp (same plugin protocol).
2. Revit (C# add-in, Autodesk App Store) for mid-size firms.
3. ArchiCAD (C++ Add-On API, or Python via the ArchiCAD JSON/Tapir interface).
4. Firm-wide plan: shared standards, team approvals, SSO (Business tier).
