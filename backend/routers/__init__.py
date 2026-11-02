"""API routers. Small shared helpers for reading request bodies live here."""
import re

from ..errors import invalid

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def text(body, key, label=None, required=True, max_len=200):
    v = body.get(key)
    v = v.strip() if isinstance(v, str) else ("" if v is None else str(v))
    if required and not v:
        raise invalid(f"{label or key} is required.", **{key: "Required."})
    if len(v) > max_len:
        raise invalid(f"{label or key} is too long.", **{key: f"Use at most {max_len} characters."})
    return v


def email(body, key="email"):
    v = text(body, key, "Email").lower()
    if not EMAIL.fullmatch(v):
        raise invalid("Enter a valid email address.", **{key: "Enter a valid email address."})
    return v
