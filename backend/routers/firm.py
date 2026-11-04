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

from .. import auth, emails, plans, sso, store
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


# ---- Enterprise: single sign-on and staff-set terms --------------------------

@router.put("/firm/sso")
def put_sso(body: dict = Body(...), c: Ctx = Depends(auth.need("owner"))):
    plans.require(c.firm, "sso")
    cfg = sso.clean_config(body, c.firm.get("sso"))
    for f in store.sso_firms():
        if f["id"] != c.fid and set(f["sso"].get("domains", [])) & set(cfg["domains"]):
            raise conflict("Another firm already uses one of these email domains for single sign-on.")
    with store.db.tx():
        store.update_firm(c.fid, sso=cfg)
        c.audit(None, "firm.sso_saved", c.fid, {k: v for k, v in cfg.items() if k != "client_secret"})
    return firm_payload(store.firm(c.fid))


@router.delete("/firm/sso")
def delete_sso(c: Ctx = Depends(auth.need("owner"))):
    with store.db.tx():
        store.db.run("update firms set sso=null where id=?", (c.fid,))
        c.audit(None, "firm.sso_removed", c.fid)
    return firm_payload(store.firm(c.fid))


def _staff(request):
    staff = os.environ.get("LINTEL_STAFF_TOKEN", "")
    if not staff or not hmac.compare_digest(request.headers.get("x-staff-token", ""), staff):
        raise forbidden()


@router.patch("/staff/firms/{fid}")
def staff_firm(fid: str, request: Request, body: dict = Body(...)):
    """Lintel staff only (LINTEL_STAFF_TOKEN): put a firm on Enterprise terms after a contract is signed."""
    _staff(request)
    if not store.firm(fid):
        raise not_found("No such firm.")
    changes = {}
    if "plan" in body:
        if body["plan"] not in plans.PLANS:
            raise invalid("Unknown plan.", plan="Use free, pro, firm or enterprise.")
        changes.update(plan=body["plan"], trial_ends_at=None)
    for k in ("seats", "chat_cap_override"):
        if k in body:
            v = body[k]
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 1):
                raise invalid(f"{k} must be a positive whole number.", **{k: "Use a positive whole number."})
            changes[k] = v
    if "region" in body:
        changes["region"] = str(body["region"] or "")[:40] or None
    if "pilot" in body:  # accepted onto the founding pilot: their Billing page offers the pilot price
        changes["pilot"] = 1 if body["pilot"] else 0
    with store.db.tx():
        store.update_firm(fid, **changes)
        store.audit(fid, None, "staff", "firm.terms_changed", fid, changes, actor_name="Lintel staff")
    return firm_payload(store.firm(fid))


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
            "configured": bool(os.environ.get("STRIPE_SECRET_KEY")), "usage": store.usage(c.fid),
            "chat_cap": store.chat_cap(c.firm), "topup": plans.TOPUP, "pilot": plans.PILOT}


@router.post("/billing/checkout")
def checkout(body: dict = Body(...), c: Ctx = Depends(auth.need("owner"))):
    plan, interval = body.get("plan"), body.get("interval", "month")
    if plan == "pilot":
        return _pilot_checkout(c)
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


def _pilot_checkout(c):
    """Founding pilot: Pro for up to 3 seats, one yearly price, locked because the Stripe price never changes."""
    if not c.firm.get("pilot"):
        raise forbidden("The pilot price is for firms on the founding pilot. Apply from the pricing page.")
    if store.seats_in_use(c.fid) > plans.PILOT["seats"]:
        raise invalid(f"The pilot covers up to {plans.PILOT['seats']} seats. Move extra members to Viewer first.")
    base = emails.app_url()
    meta = {"firm_id": c.fid, "plan": plans.PILOT["plan"], "pilot": "1"}
    s = _stripe("checkout/sessions", {
        "mode": "subscription", "line_items[0][price]": os.environ.get("STRIPE_PRICE_PILOT_YEAR", ""), "line_items[0][quantity]": 1,
        "success_url": base + "/app/settings/billing?upgraded=1", "cancel_url": base + "/app/settings/billing",
        "client_reference_id": c.fid, **{f"metadata[{k}]": v for k, v in meta.items()},
        **{f"subscription_data[metadata][{k}]": v for k, v in meta.items()}})
    return {"url": s["url"]}


@router.post("/billing/topup")
def topup(c: Ctx = Depends(auth.need("admin"))):
    """500 more assistant messages for this month, as a one-off payment."""
    if plans.effective(c.firm) == "free":
        raise ApiError(402, "plan_limit", "Message top-ups are for paid plans. Upgrade to Pro for 300 messages per seat.",
                       limit="topup", plan="free")
    base = emails.app_url()
    s = _stripe("checkout/sessions", {
        "mode": "payment", "line_items[0][price]": os.environ.get("STRIPE_PRICE_TOPUP", ""), "line_items[0][quantity]": 1,
        "success_url": base + "/app/settings/billing?topup=1", "cancel_url": base + "/app/settings/billing",
        "client_reference_id": c.fid, "metadata[firm_id]": c.fid, "metadata[kind]": "topup",
        "metadata[messages]": plans.TOPUP["messages"], "metadata[by]": c.uid})
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
    if ev["type"] == "checkout.session.completed" and meta.get("kind") == "topup":
        if obj.get("payment_status") == "paid":
            n = int(meta.get("messages") or plans.TOPUP["messages"])
            with store.db.tx():
                store.add_topup(fid, n)
                store.audit(fid, None, meta.get("by") or "system", "billing.topup", fid, {"messages": n}, actor_name="Billing")
        return {"ok": True}
    pilot = meta.get("pilot") == "1"  # one flat price covers the pilot's seats, so the quantity isn't the seat count
    if ev["type"] == "checkout.session.completed":
        changes = {"plan": meta.get("plan", "pro"), "billing_customer_id": obj.get("customer"), "trial_ends_at": None}
        if pilot:
            changes["seats"] = plans.PILOT["seats"]
    elif ev["type"] == "customer.subscription.updated":
        qty = (obj.get("items", {}).get("data") or [{}])[0].get("quantity")
        seats = plans.PILOT["seats"] if pilot else (int(qty) if qty else None)
        changes = {"plan": meta.get("plan", firm["plan"]), **({"seats": seats} if seats else {})}
    elif ev["type"] == "customer.subscription.deleted":
        changes = {"plan": "free"}
    if changes:
        with store.db.tx():
            store.update_firm(fid, **changes)
            store.audit(fid, None, "system", "billing.plan_changed", fid, {"event": ev["type"], **changes}, actor_name="Billing")
    return {"ok": True}
