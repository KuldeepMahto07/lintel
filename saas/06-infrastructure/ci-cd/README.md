# Ci cd

**Status:** ⬜ Not started

Part of [06 · Infrastructure](../README.md) in the [Lintel SaaS plan](../../README.md).

🤖 GitHub Actions: pytest + `scripts/e2e.py` on every push, and `py_compile` for the Rhino scripts. Push with the `gh` credential helper (see the workspace CLAUDE.md; the token lacks `workflow` scope).
