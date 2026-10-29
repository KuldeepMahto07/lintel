# Ux flows

**Status:** ✅ Done

Part of [04 · Design](../README.md) in the [Lintel SaaS plan](../../README.md).

Core loop as built:
1. **Observe:** the plugin pushes a snapshot.
2. **Advise:** issues with a reference, and a plan highlight on click.
3. **Act:** Propose fix or chat → change set → Approve/Reject → the host applies in one undo record → re-check.
4. **Learn:** the user states a standard → the agent proposes a rule → the user activates it.

Revert creates an approved inverse change set. Drift (the model changed after approval) is refused and shown as failed.
