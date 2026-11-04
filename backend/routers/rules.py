"""Firm rules: list, save, activate/disable, delete, import (CSV or JSON, with a dry run), export."""
import csv
import io
import json
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from .. import auth, learn, plans, store
from ..auth import Ctx
from ..errors import ApiError, invalid, not_found

router = APIRouter(prefix="/api")
STARTER = Path(__file__).resolve().parent.parent / "starter_rules.json"
FIELDS = ["id", "name", "kind", "applies_to", "where", "prop", "value", "unit", "severity", "fixable", "ref", "source"]


def seed_rules(fid):
    for r in json.loads(STARTER.read_text(encoding="utf-8")):
        store.put_rule(fid, r)


def clean_rule(r):
    """Validates one rule; raises ApiError(422) with per-field messages."""
    errs = {}
    name = str(r.get("name") or "").strip()
    if not name:
        errs["name"] = "Required."
    if r.get("kind") not in ("min", "max", "egress"):
        errs["kind"] = "Use min, max or egress."
    if r.get("applies_to") not in ("room", "door", "stair"):
        errs["applies_to"] = "Use room, door or stair."
    if r.get("kind") != "egress" and not r.get("prop"):
        errs["prop"] = "Required for min and max rules."
    try:
        value = float(r.get("value"))
        if value != value or value < 0:
            raise ValueError
    except (TypeError, ValueError):
        errs["value"] = "Enter a number."
        value = None
    if r.get("severity") not in (None, "", "error", "warning"):
        errs["severity"] = "Use error or warning."
    where = r.get("where")
    if isinstance(where, str):
        where = dict(kv.strip().split("=", 1) for kv in where.split(";") if "=" in kv)
    if where is not None and not isinstance(where, dict):
        errs["where"] = "Use key=value pairs, separated by semicolons."
    if errs:
        raise invalid(next(iter(errs.values())) if len(errs) == 1 else "Some fields need attention.", **errs)
    fixable = r.get("fixable")
    if isinstance(fixable, str):
        fixable = fixable.strip().lower() in ("1", "true", "yes", "y")
    out = dict(r, name=name[:120], value=value, where=where or None, fixable=bool(fixable),
               severity=r.get("severity") or "error", ref=str(r.get("ref") or "")[:300], unit=str(r.get("unit") or "")[:10])
    return {k: out[k] for k in FIELDS if out.get(k) not in (None, "")}


def _needs_custom(c, rule):
    if (rule.get("source") or "firm") != "starter":
        plans.require(c.firm, "custom_rules")


@router.get("/rules")
def list_rules(c: Ctx = Depends(auth.current)):
    return store.rules(c.fid)


@router.post("/rules")
def save_rule(body: dict = Body(...), c: Ctx = Depends(auth.need("admin"))):
    existing = store.get_rule(c.fid, body["id"]) if body.get("id") else None
    if body.get("id") and not existing:
        raise not_found("No such rule.")
    rule = clean_rule(body)
    rule["source"] = existing.get("source", "firm") if existing else "firm"
    if existing and existing["source"] == "starter":
        rule["source"] = "firm"  # an edited starter rule is the firm's own now
    _needs_custom(c, rule)
    status = existing["status"] if existing and existing["status"] != "proposed" else "active"
    with store.db.tx():
        rid = store.put_rule(c.fid, rule, status, by=c.uid)
        c.audit(None, "rule.updated" if existing else "rule.created", rid, rule)
    return {"id": rid, "rule": store.get_rule(c.fid, rid)}


@router.post("/rules/{rid}/status")
def rule_status(rid: str, body: dict = Body(...), c: Ctx = Depends(auth.need("admin"))):
    rule = store.get_rule(c.fid, rid)
    if not rule:
        raise not_found("No such rule.")
    status = body.get("status")
    if status not in ("active", "disabled"):
        raise invalid("Status must be active or disabled.", status="Use active or disabled.")
    if status == "active":
        _needs_custom(c, rule)
    with store.db.tx():
        store.put_rule(c.fid, rule, status)
        c.audit(None, "rule.activated" if status == "active" else "rule.disabled", rid, {"name": rule["name"]})
    return {"ok": True, "status": status}


@router.delete("/rules/{rid}")
def remove_rule(rid: str, c: Ctx = Depends(auth.need("admin"))):
    rule = store.get_rule(c.fid, rid)
    if not rule:
        raise not_found("No such rule.")
    with store.db.tx():
        learn.dismiss(c.fid, rule)
        store.delete_rule(c.fid, rid)
        c.audit(None, "rule.deleted", rid, {"name": rule["name"]})
    return {"ok": True}


def _parse(text):
    text = text.strip()
    if not text:
        raise invalid("The file is empty.")
    if text.startswith("["):
        try:
            rows = json.loads(text)
        except ValueError:
            raise ApiError(400, "bad_request", "That isn't valid JSON.")
        if not all(isinstance(r, dict) for r in rows):
            raise invalid("Each item in the JSON list must be a rule object.")
        return rows
    return [dict(r) for r in csv.DictReader(io.StringIO(text))]


@router.post("/rules/import")
async def import_rules(request: Request, dry_run: int = 0, c: Ctx = Depends(auth.need("admin"))):
    """JSON list of rules, or CSV with a header row of rule field names. ?dry_run=1 returns the preview only."""
    rows = _parse((await request.body()).decode("utf-8-sig"))
    if len(rows) > 500:
        raise invalid("Import at most 500 rules at a time.")
    preview = []
    for n, r in enumerate(rows, start=1):
        r = {k: v for k, v in r.items() if k}
        try:
            preview.append({"row": n, "rule": clean_rule(dict(r, source="firm")), "errors": None})
        except ApiError as e:
            preview.append({"row": n, "rule": r, "errors": e.extra.get("fields") or {"_": e.message}})
    bad = [p for p in preview if p["errors"]]
    if dry_run:
        return {"rows": preview, "valid": len(preview) - len(bad), "invalid": len(bad)}
    if bad:
        raise invalid(f"{len(bad)} row(s) have errors. Fix them and import again.", rows=bad)
    plans.require(c.firm, "custom_rules")
    with store.db.tx():
        ids = [store.put_rule(c.fid, p["rule"], "active", by=c.uid) for p in preview]
        c.audit(None, "rules.imported", "", {"count": len(ids)})
    return {"imported": len(ids), "ids": ids}


@router.get("/rules/export")
def export_rules(c: Ctx = Depends(auth.current)):
    data = [{k: r[k] for k in FIELDS + ["status"] if k in r} for r in store.rules(c.fid)]
    return JSONResponse(data, headers={"Content-Disposition": "attachment; filename=lintel-rules.json"})
