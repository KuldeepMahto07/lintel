"""Passwords, sessions, CSRF, role checks and rate limits (docs/security.md)."""
import os
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request

from . import store
from .errors import ApiError, forbidden, invalid, unauthenticated

COOKIE = "lintel_session"
ROLES = ("viewer", "member", "approver", "admin", "owner")
RANK = {r: i for i, r in enumerate(ROLES)}
_ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=1)

# A short list of the most common passwords; the full top-10k list can replace it later.
COMMON = {
    "password", "password1", "password12", "password123", "1234567890", "12345678910", "qwertyuiop", "1q2w3e4r5t",
    "iloveyou12", "qwerty1234", "1qaz2wsx3edc", "abc1234567", "welcome123", "letmein123", "football12", "baseball12",
    "sunshine12", "princess12", "monkey1234", "dragon1234", "passw0rd12", "administrator", "changeme123", "lintel1234",
}


def hash_password(pw):
    return _ph.hash(pw)


def verify_password(hashed, pw):
    try:
        return _ph.verify(hashed, pw)
    except (VerificationError, InvalidHashError):
        return False


def check_password(pw):
    if not isinstance(pw, str) or len(pw) < 10:
        raise invalid("Use at least 10 characters.", password="Use at least 10 characters.")
    if len(pw) > 200:
        raise invalid("That password is too long.", password="Use at most 200 characters.")
    if pw.lower() in COMMON:
        raise invalid("That password is too common.", password="That password is too common. Pick another.")


# ---- rate limits (in memory, per process) ----------------------------------

_hits = defaultdict(deque)


def rate_limit(key, limit, window):
    if os.environ.get("LINTEL_NO_RATE_LIMIT") == "1":
        return
    q, t = _hits[key], time.time()
    while q and q[0] <= t - window:
        q.popleft()
    if len(q) >= limit:
        raise ApiError(429, "rate_limited", "Too many attempts. Try again in a few minutes.",
                       retry_after=int(window - (t - q[0])) + 1)
    q.append(t)


def reset_rate_limits():
    _hits.clear()


# ---- request context -------------------------------------------------------

@dataclass
class Ctx:
    user: dict
    firm: dict
    role: str
    token: str | None = None
    csrf: str | None = None
    host: str | None = None

    @property
    def uid(self):
        return self.user["id"]

    @property
    def fid(self):
        return self.firm["id"]

    @property
    def actor(self):
        return f"host:{self.host}" if self.host else self.uid

    @property
    def name(self):
        return f"{self.user['name']} via {self.host}" if self.host else self.user["name"]

    def can(self, need):
        return RANK[self.role] >= RANK[need]

    def audit(self, project, action, target="", detail=None):
        store.audit(self.fid, project, self.actor, action, target, detail, actor_name=self.name)


def secure_cookies(request: Request):
    return request.url.scheme == "https" or os.environ.get("APP_URL", "").startswith("https")


def set_session_cookie(response, request, token):
    response.set_cookie(COOKIE, token, max_age=30 * 86400, httponly=True, samesite="lax",
                        secure=secure_cookies(request), path="/")


def clear_session_cookie(response):
    response.delete_cookie(COOKIE, path="/")


def load_session(request: Request):
    """Ctx for the signed-in user, or None."""
    token = request.cookies.get(COOKIE)
    s = store.session(token)
    if not s:
        return None
    user, firm = store.user(s["user_id"]), store.firm(s["firm_id"])
    role = firm and store.role(firm["id"], s["user_id"])
    if not user or not firm or not role:
        return None
    return Ctx(user=user, firm=firm, role=role, token=token, csrf=s["csrf"])


def current(request: Request) -> Ctx:
    c = load_session(request)
    if not c:
        raise unauthenticated()
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not secrets.compare_digest(sent, c.csrf):
            raise forbidden("Missing or stale security token. Reload the page and try again.")
    return c


def need(min_role):
    """Route dependency: signed in, CSRF checked, and at least `min_role` in the current firm."""
    def dep(c: Ctx = Depends(current)) -> Ctx:
        if not c.can(min_role):
            raise forbidden(_ROLE_MSG.get(min_role, "Your role can't do this."))
        return c
    return dep


_ROLE_MSG = {
    "member": "Viewers have read-only access.",
    "approver": "Approvers only.",
    "admin": "Admins only.",
    "owner": "Only the firm owner can do this.",
}


def plugin(request: Request) -> Ctx:
    """Plugin calls: Authorization: Bearer <personal token> (X-Lintel-Token is accepted too)."""
    h = request.headers.get("authorization", "")
    token = h[7:].strip() if h.lower().startswith("bearer ") else request.headers.get("x-lintel-token", "")
    t = store.token_owner(token) if token else None
    if not t:
        raise unauthenticated("Invalid or revoked plugin token.")
    rate_limit(f"plugin:{t['id']}", 120, 60)
    user, firm = store.user(t["user_id"]), store.firm(t["firm_id"])
    if not user or not firm:
        raise unauthenticated("Invalid or revoked plugin token.")
    return Ctx(user=user, firm=firm, role=t["role"], host="plugin")
