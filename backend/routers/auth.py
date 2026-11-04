"""Sign up, sign in (password or SSO), sessions, password reset, the current user, and invite acceptance."""
import secrets
import time
import urllib.parse

from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.responses import RedirectResponse

from .. import auth, emails, plans, sso, store
from ..auth import Ctx
from ..errors import ApiError, forbidden, invalid, not_found, unauthenticated
from . import email, text
from .rules import seed_rules

router = APIRouter(prefix="/api")


def _ip(request):
    return request.client.host if request.client else "?"


def firm_payload(firm):
    lim = plans.limits(firm)
    return {"id": firm["id"], "name": firm["name"], "plan": plans.effective(firm), "plan_raw": firm["plan"],
            "seats": firm["seats"], "two_approvals": firm["two_approvals"], "chat_enabled": firm["chat_enabled"],
            "trial_days_left": plans.trial_days_left(firm), "limits": lim, "seats_used": store.seats_in_use(firm["id"]),
            "seat_cap": plans.seat_cap(firm), "region": firm.get("region") or "", "chat_cap_override": firm.get("chat_cap_override"),
            "pilot": bool(firm.get("pilot")),
            "sso": sso_summary(firm.get("sso"))}


def sso_summary(cfg):
    """What the browser may see of the SSO settings: never the client secret."""
    if not cfg:
        return None
    return {"issuer": cfg.get("issuer", ""), "client_id": cfg.get("client_id", ""), "domains": cfg.get("domains", []),
            "required": bool(cfg.get("required")), "default_role": cfg.get("default_role", "member")}


def me_payload(c: Ctx):
    return {"user": c.user, "firm": firm_payload(c.firm), "role": c.role, "firms": store.firms_for_user(c.uid),
            "csrf": c.csrf, "usage": dict(store.usage(c.fid), chat_cap=store.chat_cap(c.firm), warn_at=plans.WARN_AT)}


def _start_session(request, response, uid, fid):
    token = store.create_session(uid, fid, request.headers.get("user-agent", ""))
    auth.set_session_cookie(response, request, token)
    store.update_user(uid, last_login_at=time.time())
    return token


@router.post("/auth/signup", status_code=201)
def signup(request: Request, response: Response, body: dict = Body(...)):
    auth.rate_limit(f"signup:{_ip(request)}", 10, 3600)
    name, firm_name = text(body, "name", "Name", max_len=100), text(body, "firm_name", "Firm name", max_len=120)
    mail = email(body)
    auth.check_password(body.get("password"))
    if store.user_by_email(mail):
        raise invalid("Email already in use.", email="Email already in use. Sign in instead.")
    with store.db.tx():
        uid = store.create_user(mail, name, auth.hash_password(body["password"]))
        fid = store.create_firm(firm_name, plan="pro", seats=plans.TRIAL_SEATS,
                                trial_ends_at=time.time() + plans.TRIAL_DAYS * 86400)
        store.add_member(fid, uid, "owner")
        seed_rules(fid)
        store.audit(fid, None, uid, "auth.signup", uid, {"firm": firm_name}, actor_name=name)
    _start_session(request, response, uid, fid)
    return {"user": store.user(uid), "firm": firm_payload(store.firm(fid))}


@router.post("/auth/login")
def login(request: Request, response: Response, body: dict = Body(...)):
    mail = str(body.get("email", "")).strip().lower()
    auth.rate_limit(f"login:{mail}:{_ip(request)}", 5, 900)
    u = store.user_by_email(mail) if mail else None
    if not u or not auth.verify_password(u["password_hash"], str(body.get("password", ""))):
        raise unauthenticated("Email or password is wrong.")
    firms = store.firms_for_user(u["id"])
    if not firms:
        raise forbidden("This account isn't a member of any firm.")
    pinned = sso.firm_for_email(mail)
    if pinned and pinned["sso"].get("required") and store.role(pinned["id"], u["id"]) not in (None, "owner"):
        # Owners keep their password so a broken identity provider can't lock the firm out.
        raise ApiError(403, "sso_required", f"{pinned['name']} signs in with single sign-on. Use \"Sign in with SSO\".")
    old = request.cookies.get(auth.COOKIE)
    if old:
        store.delete_session(old)  # rotate on login
    _start_session(request, response, u["id"], firms[0]["id"])
    store.audit(firms[0]["id"], None, u["id"], "auth.login", u["id"], {}, actor_name=u["name"])
    return {"user": store.user(u["id"]), "firms": firms}


def _sso_redirect_uri():
    return emails.app_url() + "/api/auth/sso/callback"


@router.post("/auth/sso/start")
def sso_start(request: Request, body: dict = Body(...)):
    mail = str(body.get("email", "")).strip().lower()
    auth.rate_limit(f"sso:{_ip(request)}", 20, 900)
    firm = sso.firm_for_email(mail)
    if not firm or not plans.limits(firm)["sso"]:
        raise not_found("Single sign-on isn't set up for that email domain. Sign in with your password.")
    return {"url": sso.start(firm, _sso_redirect_uri(), mail)}


@router.get("/auth/sso/callback")
def sso_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    try:
        if error:
            raise ApiError(400, "sso_error", "The identity provider cancelled the sign-in.")
        firm, mail, name = sso.finish(code, state, _sso_redirect_uri())
        u = store.user_by_email(mail)
        with store.db.tx():
            if not u:
                uid = store.create_user(mail, name, auth.hash_password(secrets.token_urlsafe(32)))
            else:
                uid = u["id"]
            if store.role(firm["id"], uid) is None:
                role = firm["sso"].get("default_role", "member")
                if role != "viewer" and store.seats_in_use(firm["id"]) >= plans.seat_cap(firm):
                    role = "viewer"  # no free seat: they can read until an admin gives them one
                store.add_member(firm["id"], uid, role)
                store.audit(firm["id"], None, uid, "member.joined", uid, {"role": role, "via": "sso"}, actor_name=name)
        response = RedirectResponse("/app", status_code=303)
        old = request.cookies.get(auth.COOKIE)
        if old:
            store.delete_session(old)
        _start_session(request, response, uid, firm["id"])
        store.audit(firm["id"], None, uid, "auth.login", uid, {"via": "sso"}, actor_name=name)
        return response
    except ApiError as e:
        return RedirectResponse("/login?" + urllib.parse.urlencode({"sso_error": e.message}), status_code=303)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, c: Ctx = Depends(auth.current)):
    store.delete_session(c.token)
    r = Response(status_code=204)
    auth.clear_session_cookie(r)
    return r


@router.post("/auth/reset/request", status_code=202)
def reset_request(request: Request, body: dict = Body(...)):
    mail = str(body.get("email", "")).strip().lower()
    auth.rate_limit(f"reset:{mail}", 3, 3600)
    u = store.user_by_email(mail) if mail else None
    if u:
        emails.reset(u["email"], store.create_reset(u["id"]))
    return {"ok": True}  # same answer whether or not the email exists


@router.post("/auth/reset/confirm", status_code=204)
def reset_confirm(body: dict = Body(...)):
    auth.check_password(body.get("password"))
    uid = store.use_reset(str(body.get("token", "")))
    if not uid:
        raise invalid("This reset link is invalid or has expired. Ask for a new one.", token="Expired or already used.")
    store.update_user(uid, password_hash=auth.hash_password(body["password"]))
    store.delete_user_sessions(uid)
    for f in store.firms_for_user(uid):
        store.audit(f["id"], None, uid, "auth.password_reset", uid, {})
    return Response(status_code=204)


@router.get("/me")
def me(c: Ctx = Depends(auth.current)):
    return me_payload(c)


@router.patch("/me")
def update_me(body: dict = Body(...), c: Ctx = Depends(auth.current)):
    store.update_user(c.uid, name=text(body, "name", "Name", max_len=100))
    return {"user": store.user(c.uid)}


@router.post("/me/password", status_code=204)
def change_password(body: dict = Body(...), c: Ctx = Depends(auth.current)):
    if not auth.verify_password(store.password_hash(c.uid), str(body.get("current", ""))):
        raise invalid("Your current password is wrong.", current="Wrong password.")
    if body.get("password") is not None:
        auth.check_password(body.get("password"))
    else:
        raise invalid("Enter a new password.", password="Required.")
    store.update_user(c.uid, password_hash=auth.hash_password(body["password"]))
    store.delete_user_sessions(c.uid, keep_token=c.token)
    c.audit(None, "auth.password_changed", c.uid)
    return Response(status_code=204)


@router.post("/me/firm")
def switch_firm(body: dict = Body(...), c: Ctx = Depends(auth.current)):
    fid = str(body.get("firm_id", ""))
    if not store.role(fid, c.uid) or not store.firm(fid):
        raise not_found("No such firm.")
    store.set_session_firm(c.token, fid)
    return {"ok": True}


# ---- invites (public side) -------------------------------------------------

def _live_invite(token):
    inv = store.invite_by_token(token)
    if not inv or inv["cancelled_at"]:
        raise not_found("This invite link isn't valid.")
    if inv["accepted_at"]:
        raise ApiError(409, "conflict", "This invite has already been used. Sign in instead.")
    if inv["expires_at"] < time.time():
        raise ApiError(410, "expired", "This invite has expired. Ask your admin to send a new one.")
    return inv


@router.get("/invites/{token}")
def invite_info(token: str):
    inv = _live_invite(token)
    return {"firm_name": inv["firm_name"], "email": inv["email"], "role": inv["role"],
            "has_account": bool(store.user_by_email(inv["email"]))}


@router.post("/invites/{token}/accept")
def accept_invite(token: str, request: Request, response: Response, body: dict = Body(default={})):
    inv = _live_invite(token)
    signed_in = auth.load_session(request)
    existing = store.user_by_email(inv["email"])
    if signed_in:
        if signed_in.user["email"].lower() != inv["email"].lower():
            raise forbidden(f"This invite is for {inv['email']}. Sign out and open the link again.")
        uid = signed_in.uid
    elif existing:
        auth.rate_limit(f"login:{inv['email']}:{_ip(request)}", 5, 900)
        if not auth.verify_password(existing["password_hash"], str(body.get("password", ""))):
            raise unauthenticated("Password is wrong for this account.")
        uid = existing["id"]
    else:
        name = text(body, "name", "Name", max_len=100)
        auth.check_password(body.get("password"))
        uid = None
    with store.db.tx():
        if uid is None:
            uid = store.create_user(inv["email"], name, auth.hash_password(body["password"]))
        if not store.role(inv["firm_id"], uid):
            store.add_member(inv["firm_id"], uid, inv["role"])
        store.mark_invite(inv["id"], "accepted_at")
        u = store.user(uid)
        store.audit(inv["firm_id"], None, uid, "member.joined", uid, {"role": inv["role"], "email": inv["email"]},
                    actor_name=u["name"])
    if signed_in:
        store.set_session_firm(signed_in.token, inv["firm_id"])
    else:
        _start_session(request, response, uid, inv["firm_id"])
    return {"ok": True, "firm_id": inv["firm_id"]}
