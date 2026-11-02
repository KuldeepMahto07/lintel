"""The firm, its members and invites, personal plugin tokens, and billing."""
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.error
import urllib.request

from fastapi import APIRouter, Body, Depends, Request, Response

from .. import auth, emails, plans, store
from ..auth import RANK, Ctx
from ..errors import ApiError, conflict, forbidden, invalid, not_found
from . import email, text
from .auth import firm_payload

router = APIRouter(prefix="/api")


# ---- firm ------------------------------------------------------------------

@router.get("/firm")
def get_firm(c: Ctx = Depends(auth.current)):
    return firm_payload(c.firm)


@router.patch("/firm")
def patch_firm(body: dict = Body(...), c: Ctx = Depends(auth.need("admin"))):
    changes = {}
    if "name" in body:
        changes["name"] = text(body, "name", "Firm name", max_len=120)
    if "two_approvals" in body:
        if body["two_approvals"]:
            plans.require(c.firm, "two_approvals")
        changes["two_approvals"] = 1 if body["two_approvals"] else 0
    if "chat_enabled" in body:
        changes["chat_enabled"] = 1 if body["chat_enabled"] else 0
    with store.db.tx():
        store.update_firm(c.fid, **changes)
        c.audit(None, "firm.updated", c.fid, changes)
    return firm_payload(store.firm(c.fid))


@router.delete("/firm", status_code=204)
def delete_firm(body: dict = Body(...), c: Ctx = Depends(auth.need("owner"))):
    if str(body.get("confirm", "")).strip() != c.firm["name"]:
        raise invalid("Type the firm name exactly to confirm.", confirm="Doesn't match the firm name.")
    with store.db.tx():
        c.audit(None, "firm.deleted", c.fid, {"name": c.firm["name"]})
        store.update_firm(c.fid, deleted_at=time.time())  # purged after 30 days by the nightly job
        store.db.run("delete from sessions where firm_id=?", (c.fid,))
    r = Response(status_code=204)
    auth.clear_session_cookie(r)
    return r


# ---- members ---------------------------------------------------------------

def _owners(fid):
    return [m for m in store.members(fid) if m["role"] == "owner"]


def _check_seat(c, new_role, old_role=None):
    """A seat is a member who can propose, approve or chat; viewers are free."""
    if new_role == "viewer" or (old_role and old_role != "viewer"):
        return
    pending = sum(1 for i in store.invites(c.fid) if i["role"] != "viewer")
    if store.seats_in_use(c.fid) + pending >= plans.seat_cap(c.firm):
        raise ApiError(402, "plan_limit", plans._MESSAGES["members"], limit="members", plan=plans.effective(c.firm))


@router.get("/members")
def list_members(c: Ctx = Depends(auth.current)):
    out = {"members": store.members(c.fid)}
    if c.can("admin"):
        out["invites"] = store.invites(c.fid)
    return out


@router.patch("/members/{uid}")
def change_role(uid: str, body: dict = Body(...), c: Ctx = Depends(auth.need("admin"))):
    new = body.get("role")
    if new not in RANK:
        raise invalid("Pick a role.", role="Pick a role.")
    old = store.role(c.fid, uid)
    if not old:
        raise not_found("No such member.")
    if (old == "owner" or new == "owner") and c.role != "owner":
        raise forbidden("Only the owner can change ownership.")
    if old == "owner" and new != "owner" and len(_owners(c.fid)) <= 1:
        raise conflict("A firm needs at least one owner. Make someone else owner first.")
    _check_seat(c, new, old)
    with store.db.tx():
        store.set_role(c.fid, uid, new)
        store.db.run("delete from sessions where firm_id=? and user_id=? and id_hash != ?", (c.fid, uid, store.sha(c.token)))
        c.audit(None, "member.role_changed", uid, {"from": old, "to": new})
    return {"ok": True}


@router.delete("/members/{uid}")
def remove_member(uid: str, c: Ctx = Depends(auth.need("admin"))):
    old = store.role(c.fid, uid)
    if not old:
        raise not_found("No such member.")
    if old == "owner" and (c.role != "owner" or len(_owners(c.fid)) <= 1):
        raise conflict("You can't remove the firm's only owner.")
    with store.db.tx():
        store.remove_member(c.fid, uid)
        c.audit(None, "member.removed", uid, {"role": old})
    return {"ok": True}


# ---- invites (admin side) --------------------------------------------------

def _send_invite(c, to, role, token):
    link = emails.invite(to, c.firm["name"], c.user["name"], role, token)
    return None if emails.configured() else link  # local runs: show the link so it can be copied


@router.post("/invites", status_code=201)
def create_invite(body: dict = Body(...), c: Ctx = Depends(auth.need("admin"))):
    to = email(body)
    role = body.get("role") or "member"
    if role not in RANK or role == "owner":
        raise invalid("Pick a role.", role="Invite as admin, approver, member or viewer.")
    if any(m["email"].lower() == to for m in store.members(c.fid)):
        raise invalid("This person is already a member.", email="Already a member.")
    if any(i["email"].lower() == to for i in store.invites(c.fid)):
        raise invalid("An invite to this email is already pending. Resend it from the list.", email="Invite already pending.")
    _check_seat(c, role)
    with store.db.tx():
        iid, token = store.create_invite(c.fid, to, role, c.uid)
        c.audit(None, "member.invited", iid, {"email": to, "role": role})
    return {"id": iid, "link": _send_invite(c, to, role, token)}


@router.post("/invites/{iid}/resend")
def resend_invite(iid: str, c: Ctx = Depends(auth.need("admin"))):
    inv = store.invite(c.fid, iid)
    if not inv or inv["accepted_at"] or inv["cancelled_at"]:
        raise not_found("No such pending invite.")
    token = store.rotate_invite(c.fid, iid)
    c.audit(None, "member.invite_resent", iid, {"email": inv["email"]})
    return {"ok": True, "link": _send_invite(c, inv["email"], inv["role"], token)}


@router.delete("/invites/{iid}")
def cancel_invite(iid: str, c: Ctx = Depends(auth.need("admin"))):
    inv = store.invite(c.fid, iid)
    if not inv or inv["accepted_at"] or inv["cancelled_at"]:
        raise not_found("No such pending invite.")
    store.mark_invite(iid, "cancelled_at")
    c.audit(None, "member.invite_cancelled", iid, {"email": inv["email"]})
    return {"ok": True}


# ---- plugin tokens ---------------------------------------------------------

@router.get("/tokens")
def list_tokens(c: Ctx = Depends(auth.current)):
    return store.tokens(c.uid, c.fid)


@router.post("/tokens", status_code=201)
def create_token(body: dict = Body(...), c: Ctx = Depends(auth.need("member"))):
    name = text(body, "name", "Token name", max_len=80)
    with store.db.tx():
        tid, token = store.create_token(c.uid, c.fid, name)
        c.audit(None, "token.created", tid, {"name": name, "prefix": token[:8]})
    return {"id": tid, "token": token, "prefix": token[:8], "name": name}


@router.delete("/tokens/{tid}")
def revoke_token(tid: str, c: Ctx = Depends(auth.current)):
    if not store.revoke_token(c.uid, c.fid, tid):
        raise not_found("No such token.")
    c.audit(None, "token.revoked", tid)
    return {"ok": True}


# ---- billing (docs/billing.md) ---------------------------------------------

def _stripe(path, params):
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise ApiError(503, "billing_unavailable", "Payments aren't set up yet. Contact us to upgrade.")
    req = urllib.request.Request("https://api.stripe.com/v1/" + path, data=urllib.parse.urlencode(params).encode(),
                                 method="POST", headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ApiError(502, "billing_error", f"The payment provider returned an error ({e.code}).")


@router.get("/billing")
def billing(c: Ctx = Depends(auth.current)):
    return {"firm": firm_payload(c.firm), "prices": plans.PRICES, "plans": plans.PLANS,
            "configured": bool(os.environ.get("STRIPE_SECRET_KEY")), "usage": store.usage(c.fid)}


@router.post("/billing/checkout")
def checkout(body: dict = Body(...), c: Ctx = Depends(auth.need("owner"))):
    plan, interval = body.get("plan"), body.get("interval", "month")
    if plan not in ("pro", "firm") or interval not in ("month", "year"):
        raise invalid("Pick Pro or Firm, monthly or yearly.")
    seats = int(body.get("seats") or 1)
    seats = max(seats, store.seats_in_use(c.fid), plans.PRICES[plan].get("min_seats", 1))
    price = os.environ.get(f"STRIPE_PRICE_{plan.upper()}_{'MONTH' if interval == 'month' else 'YEAR'}", "")
    base = emails.app_url()
    s = _stripe("checkout/sessions", {
        "mode": "subscription", "line_items[0][price]": price, "line_items[0][quantity]": seats,
        "success_url": base + "/app/settings/billing?upgraded=1", "cancel_url": base + "/app/settings/billing",
        "client_reference_id": c.fid, "metadata[firm_id]": c.fid, "metadata[plan]": plan,
        "subscription_data[metadata][firm_id]": c.fid, "subscription_data[metadata][plan]": plan})
    return {"url": s["url"]}


@router.post("/billing/portal")
def portal(c: Ctx = Depends(auth.need("owner"))):
    if not c.firm.get("billing_customer_id"):
        raise conflict("There's no subscription to manage yet.")
    s = _stripe("billing_portal/sessions", {"customer": c.firm["billing_customer_id"],
                                            "return_url": emails.app_url() + "/app/settings/billing"})
    return {"url": s["url"]}


def _verify_stripe(payload, header):
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    if not secret or "t" not in parts or abs(time.time() - int(parts["t"])) > 300:
        return False
    want = hmac.new(secret.encode(), f"{parts['t']}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(want, v) for k, v in (p.split("=", 1) for p in header.split(",")) if k == "v1")


@router.post("/billing/webhook")
async def webhook(request: Request):
    payload = await request.body()
    if not _verify_stripe(payload, request.headers.get("stripe-signature", "")):
        raise ApiError(400, "bad_signature", "Signature check failed.")
    ev = json.loads(payload)
    if store.billing_event_seen(ev["id"]):
        return {"ok": True, "duplicate": True}
    obj = ev["data"]["object"]
    meta = obj.get("metadata") or {}
    fid = meta.get("firm_id") or obj.get("client_reference_id")
    firm = fid and store.firm(fid)
    if not firm:
        return {"ok": True, "ignored": True}
    changes = {}
    if ev["type"] == "checkout.session.completed":
        changes = {"plan": meta.get("plan", "pro"), "billing_customer_id": obj.get("customer"), "trial_ends_at": None}
    elif ev["type"] == "customer.subscription.updated":
        qty = (obj.get("items", {}).get("data") or [{}])[0].get("quantity")
        changes = {"plan": meta.get("plan", firm["plan"]), **({"seats": int(qty)} if qty else {})}
    elif ev["type"] == "customer.subscription.deleted":
        changes = {"plan": "free"}
    if changes:
        with store.db.tx():
            store.update_firm(fid, **changes)
            store.audit(fid, None, "system", "billing.plan_changed", fid, {"event": ev["type"], **changes}, actor_name="Billing")
    return {"ok": True}
