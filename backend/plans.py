"""Plan entitlements (docs/billing.md). The server is the gate; the UI only shows upgrade prompts."""
import time

from .errors import ApiError

PLANS = {
    "free": {"projects": 1, "apply": False, "custom_rules": False, "chat_per_seat": 20, "two_approvals": False,
             "audit_csv": False, "overrides": False, "members": 1},
    "pro": {"projects": None, "apply": True, "custom_rules": True, "chat_per_seat": 300, "two_approvals": False,
            "audit_csv": False, "overrides": True, "members": None},
    "firm": {"projects": None, "apply": True, "custom_rules": True, "chat_per_seat": 1000, "two_approvals": True,
             "audit_csv": True, "overrides": True, "members": None},
    "enterprise": {"projects": None, "apply": True, "custom_rules": True, "chat_per_seat": 5000, "two_approvals": True,
                   "audit_csv": True, "overrides": True, "members": None},
}
PRICES = {"pro": {"month": 39, "year": 390}, "firm": {"month": 99, "year": 990, "min_seats": 3}}
TRIAL_DAYS = 14
TRIAL_SEATS = 3


def effective(firm):
    """The plan in force: a lapsed trial with no subscription drops to Free (data is kept)."""
    plan = firm.get("plan") or "free"
    if firm.get("trial_ends_at") and not firm.get("billing_customer_id") and time.time() > firm["trial_ends_at"]:
        return "free"
    return plan if plan in PLANS else "free"


def limits(firm):
    return PLANS[effective(firm)]


def trial_days_left(firm):
    if not firm.get("trial_ends_at") or firm.get("billing_customer_id"):
        return None
    return max(0, int((firm["trial_ends_at"] - time.time()) // 86400) + 1)


def require(firm, feature):
    if not limits(firm)[feature]:
        raise ApiError(402, "plan_limit", _MESSAGES.get(feature, "Your plan doesn't include this."),
                       limit=feature, plan=effective(firm))


def check_count(firm, feature, current):
    cap = limits(firm)[feature]
    if cap is not None and current >= cap:
        raise ApiError(402, "plan_limit", _MESSAGES.get(feature, "Plan limit reached."), limit=feature, plan=effective(firm))


def seat_cap(firm):
    """Members who can propose, approve or chat. Viewers are free."""
    cap = limits(firm)["members"]
    return cap if cap is not None else max(1, int(firm.get("seats") or 1))


def chat_cap(firm, seats_used):
    return limits(firm)["chat_per_seat"] * max(1, seats_used)


_MESSAGES = {
    "projects": "The Free plan includes one project. Upgrade to add more.",
    "apply": "Applying approved changes in your CAD app needs the Pro plan.",
    "custom_rules": "Custom firm rules need the Pro plan. Starter rules stay available.",
    "two_approvals": "Two-approval mode is part of the Firm plan.",
    "audit_csv": "Audit CSV export is part of the Firm plan.",
    "overrides": "Per-project rule overrides need the Pro plan.",
    "members": "Your plan has no free seats. Add seats in Billing or invite this person as a Viewer.",
    "chat": "Your firm has used this month's assistant messages. Chat resumes next month, or add a top-up in Billing.",
}
