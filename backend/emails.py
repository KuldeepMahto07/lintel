"""Outgoing email: Resend when RESEND_API_KEY is set, otherwise printed to the console (local runs).
The last messages are also kept in OUTBOX so tests and local users can follow links."""
import json
import os
import sys
import urllib.request
from collections import deque

OUTBOX = deque(maxlen=50)


def configured():
    return bool(os.environ.get("RESEND_API_KEY"))


def app_url():
    return os.environ.get("APP_URL", "http://127.0.0.1:8002").rstrip("/")


def send(to, subject, text):
    OUTBOX.append({"to": to, "subject": subject, "text": text})
    if not configured():
        print(f"\n--- email to {to}: {subject}\n{text}\n---", file=sys.stderr, flush=True)
        return
    body = json.dumps({"from": os.environ.get("MAIL_FROM", "Lintel <noreply@lintel.app>"), "to": [to],
                       "subject": subject, "text": text}).encode()
    req = urllib.request.Request("https://api.resend.com/emails", data=body, method="POST", headers={
        "Authorization": "Bearer " + os.environ["RESEND_API_KEY"], "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except OSError as e:  # mail failure must not break the request; the link can be resent
        print(f"email to {to} failed: {e}", file=sys.stderr, flush=True)


def invite(to, firm_name, inviter, role, token):
    link = f"{app_url()}/invite/{token}"
    send(to, f"{inviter} invited you to {firm_name} on Lintel",
         f"{inviter} invited you to join {firm_name} on Lintel as {role}.\n\n"
         f"Accept the invite: {link}\n\nThe link works once and expires in 7 days.")
    return link


def reset(to, token):
    link = f"{app_url()}/reset?token={token}"
    send(to, "Reset your Lintel password",
         f"Someone asked to reset the password for this email on Lintel.\n\nSet a new password: {link}\n\n"
         "The link works once and expires in 30 minutes. If this wasn't you, ignore this email.")
    return link
