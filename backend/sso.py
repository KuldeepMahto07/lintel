"""Single sign-on for Enterprise firms: OpenID Connect, authorization code flow with PKCE.

A firm owner saves the identity provider's issuer URL, a client id and secret, and the email
domains that belong to the firm. Signing in with SSO then goes:
  start(email) -> the provider's login page -> finish(code, state) -> a Lintel session.
The code is exchanged server to server over TLS with the client secret and the PKCE verifier,
and the person's identity comes from the provider's userinfo endpoint, so no token signatures
have to be checked here. The state is single use and expires after ten minutes.
"""
import base64
import hashlib
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from . import db, store
from .errors import ApiError, invalid

ROLES = ("member", "approver", "viewer")
STATE_TTL = 600


def fetch_json(url, data=None, headers=None):
    """GET (or POST a form) and parse JSON. Tests replace this."""
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"Accept": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, ValueError) as e:
        raise ApiError(502, "sso_error", f"The identity provider didn't answer as expected ({type(e).__name__}).")


def clean_config(body, existing=None):
    existing = existing or {}
    errs = {}
    issuer = str(body.get("issuer") or "").strip().rstrip("/")
    if not re.fullmatch(r"https://[^\s/]+(/[^\s]*)?", issuer):
        errs["issuer"] = "Use the provider's https issuer URL, e.g. https://login.example.com."
    client_id = str(body.get("client_id") or "").strip()
    if not client_id:
        errs["client_id"] = "Required."
    secret = str(body.get("client_secret") or "").strip() or existing.get("client_secret", "")
    if not secret:
        errs["client_secret"] = "Required."
    raw = body.get("domains") or []
    domains = sorted({d.strip().lower().lstrip("@") for d in (raw.split(",") if isinstance(raw, str) else raw) if str(d).strip()})
    if not domains or not all(re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", d) for d in domains):
        errs["domains"] = "List the firm's email domains, separated by commas."
    role = body.get("default_role") or "member"
    if role not in ROLES:
        errs["default_role"] = "Use member, approver or viewer."
    if errs:
        raise invalid(next(iter(errs.values())) if len(errs) == 1 else "Some fields need attention.", **errs)
    return {"issuer": issuer, "client_id": client_id[:300], "client_secret": secret[:500], "domains": domains,
            "required": bool(body.get("required")), "default_role": role}


def domain(email):
    return email.rsplit("@", 1)[-1].lower() if "@" in email else ""


def firm_for_email(email):
    d = domain(email)
    for f in store.sso_firms():
        if d and d in (f["sso"] or {}).get("domains", []):
            return f
    return None


def _discover(cfg):
    doc = fetch_json(cfg["issuer"] + "/.well-known/openid-configuration")
    if not all(doc.get(k) for k in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint")):
        raise ApiError(502, "sso_error", "The identity provider's configuration is missing an endpoint.")
    return doc


def start(firm, redirect_uri, login_hint=""):
    cfg = firm["sso"]
    doc = _discover(cfg)
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(16), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    db.run("delete from sso_states where expires_at < ?", (time.time(),))
    db.run("insert into sso_states (state_hash, firm_id, nonce, verifier, expires_at) values (?,?,?,?,?)",
           (store.sha(state), firm["id"], nonce, verifier, time.time() + STATE_TTL))
    q = {"response_type": "code", "client_id": cfg["client_id"], "redirect_uri": redirect_uri, "scope": "openid email profile",
         "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"}
    if login_hint:
        q["login_hint"] = login_hint
    return doc["authorization_endpoint"] + ("&" if "?" in doc["authorization_endpoint"] else "?") + urllib.parse.urlencode(q)


def finish(code, state, redirect_uri):
    """Returns (firm, email, name) for a completed sign-in, or raises ApiError."""
    row = db.one("select * from sso_states where state_hash=?", (store.sha(state or ""),))
    db.run("delete from sso_states where state_hash=?", (store.sha(state or ""),))
    if not row or row["expires_at"] < time.time() or not code:
        raise ApiError(400, "sso_expired", "That sign-in link expired. Start again from the sign-in page.")
    firm = store.firm(row["firm_id"])
    if not firm or not firm.get("sso"):
        raise ApiError(400, "sso_off", "Single sign-on is no longer set up for this firm.")
    cfg = firm["sso"]
    doc = _discover(cfg)
    tok = fetch_json(doc["token_endpoint"], {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                                             "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                                             "code_verifier": row["verifier"]})
    if not tok.get("access_token"):
        raise ApiError(400, "sso_error", "The identity provider didn't issue a token.")
    info = fetch_json(doc["userinfo_endpoint"], headers={"Authorization": "Bearer " + tok["access_token"]})
    mail = str(info.get("email") or "").strip().lower()
    if not mail or info.get("email_verified") is False:
        raise ApiError(403, "sso_email", "Your identity provider didn't share a verified email address.")
    if domain(mail) not in cfg["domains"]:
        raise ApiError(403, "sso_domain", "That account's email domain isn't one of this firm's domains.")
    name = str(info.get("name") or info.get("given_name") or mail.split("@")[0])[:100]
    return firm, mail, name
