"""Lintel's chat agent: Claude with tools over the project model, rules and change sets.

The agent can read, check and *propose*. It has no tool that approves or applies,
so every model edit still needs a person to click Approve.
"""
import json
import os
from collections import Counter

import anthropic

from . import checker, service, store

MODEL = os.environ.get("LINTEL_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 8

SYSTEM = """You are Lintel, a design-review assistant that works inside an architect's CAD/BIM model.

How you work:
- Read the model with tools before answering; never guess dimensions.
- Units: lengths in mm, areas in m².
- Code compliance comes from the firm's rule set (run_checks / list_rules). Each rule has a numeric value and a code
  section reference. Cite the reference (e.g. "IBC §1010.1.1 per your rule set") and remind the user to confirm it
  against the edition and amendments their jurisdiction adopted. Never quote or reproduce building-code text.
- To change the model, call propose_changes. It creates a change set the user must approve; nothing changes until
  they do. Say clearly that the change is waiting for their approval. Never claim an edit has been made.
- Only these properties are editable: door clear_width_mm/name; stair riser_mm/tread_mm/risers/width_mm;
  room name/use. Room areas, corridor widths and travel distance depend on geometry: explain which walls or doors
  to move instead of proposing an edit.
- When the user states a standard their firm follows ("we always use 900 mm doors"), call propose_rule so it can be
  saved after they confirm it on the Rules page.
- Be brief and concrete. Ask one question when the request is ambiguous."""

TOOLS = [
    {"name": "get_model_summary", "description": "Counts of rooms, doors, stairs and walls in the current model snapshot, plus when it was taken.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "query_elements", "description": "List elements of one type with their properties. Optional exact-match filter on properties, e.g. {\"use\": \"corridor\"}.",
     "input_schema": {"type": "object", "properties": {
         "type": {"type": "string", "enum": ["room", "door", "stair", "wall"]},
         "where": {"type": "object", "description": "Property filters", "additionalProperties": {"type": "string"}}},
         "required": ["type"], "additionalProperties": False}},
    {"name": "run_checks", "description": "Run the firm's active rules against the model. Returns every issue with the rule reference and whether a one-click fix exists.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "list_rules", "description": "The firm's rule set: active, disabled and proposed rules.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "propose_changes", "description": "Create a change set for the user to approve. Does not modify the model.",
     "input_schema": {"type": "object", "properties": {
         "title": {"type": "string"},
         "reason": {"type": "string", "description": "Why, including the rule reference if any"},
         "ops": {"type": "array", "items": {"type": "object", "properties": {
             "element": {"type": "string", "description": "Element id"},
             "prop": {"type": "string"},
             "to": {"type": ["number", "string"]}},
             "required": ["element", "prop", "to"], "additionalProperties": False}}},
         "required": ["title", "reason", "ops"], "additionalProperties": False}},
    {"name": "propose_rule", "description": "Propose a firm standard as a reusable rule. It is saved as 'proposed' until the user activates it.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string"},
         "kind": {"type": "string", "enum": ["min", "max"]},
         "applies_to": {"type": "string", "enum": ["room", "door", "stair"]},
         "where": {"type": "object", "additionalProperties": {"type": "string"}},
         "prop": {"type": "string"},
         "value": {"type": "number"},
         "unit": {"type": "string"},
         "ref": {"type": "string", "description": "Source, e.g. 'Firm standard' or a code section number"}},
         "required": ["name", "kind", "applies_to", "prop", "value", "unit", "ref"], "additionalProperties": False}},
]


def run_tool(pid, name, args, created):
    els = service.elements(pid)
    if name == "get_model_summary":
        snap = store.latest_snapshot(pid)
        return {"counts": Counter(e["type"] for e in els), "host": snap and snap["host"],
                "taken": snap and snap["taken"]}
    if name == "query_elements":
        out = [e for e in els if e["type"] == args["type"]]
        for k, v in (args.get("where") or {}).items():
            out = [e for e in out if str(e["props"].get(k, "")).lower() == str(v).lower()]
        return [{"id": e["id"], "props": e["props"]} for e in out]
    if name == "run_checks":
        return service.issues(pid)
    if name == "list_rules":
        return store.rules()
    if name == "propose_changes":
        cid = service.propose(pid, args["title"], args["reason"], args["ops"], "agent", "agent")
        created["changesets"].append(cid)
        return {"changeset": cid, "status": "proposed: waiting for the user's approval"}
    if name == "propose_rule":
        rid = store.put_rule(dict(args, source="learned", severity="warning", fixable=args["applies_to"] != "room"),
                             status="proposed")
        store.audit(pid, "agent", "rule.proposed", rid, args)
        created["rules"].append(rid)
        return {"rule": rid, "status": "proposed: the user activates it on the Rules page"}
    raise ValueError(f"unknown tool {name}")


def chat(pid, text, client=None):
    client = client or anthropic.Anthropic()
    messages = store.chat_messages(pid)
    messages.append({"role": "user", "content": text})
    created = {"changesets": [], "rules": []}
    replies = []
    for _ in range(MAX_STEPS):
        resp = client.beta.messages.create(
            model=MODEL, max_tokens=16000, system=SYSTEM, tools=TOOLS, messages=messages,
            thinking={"type": "adaptive"}, output_config={"effort": "medium"},
            cache_control={"type": "ephemeral"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        # Append the content unchanged so thinking blocks stay valid on the next turn.
        messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})
        replies += [b.text for b in resp.content if b.type == "text" and b.text.strip()]
        if resp.stop_reason == "refusal":
            replies.append("I can't help with that request.")
            break
        calls = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason != "tool_use" or not calls:
            break
        results = []
        for call in calls:
            try:
                out, err = run_tool(pid, call.name, call.input, created), False
            except (service.ChangeError, KeyError, ValueError) as e:
                out, err = {"error": str(e)}, True
            results.append({"type": "tool_result", "tool_use_id": call.id,
                            "content": json.dumps(out, default=str), "is_error": err})
        messages.append({"role": "user", "content": results})
    store.save_chat(pid, messages)
    store.audit(pid, "user", "chat.message", "", {"text": text[:500], **created})
    return {"replies": replies, **created}


def transcript(pid):
    """User/assistant text only, for display."""
    out = []
    for m in store.chat_messages(pid):
        if isinstance(m["content"], str):
            out.append({"role": m["role"], "text": m["content"]})
        elif m["role"] == "assistant":
            text = "\n".join(b.get("text", "") for b in m["content"] if b.get("type") == "text").strip()
            if text:
                out.append({"role": "assistant", "text": text})
    return out
