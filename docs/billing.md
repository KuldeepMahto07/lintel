# Lintel billing: plans, limits and payments

Pricing strategy and research: `saas/11-conversion/pricing-strategy`. This file is what the app enforces.

---

## 1. Plans

| | Free | Pro | Firm | Enterprise |
|---|---|---|---|---|
| Price (monthly) | $0 | $39 per seat | $99 per seat (min 3) | Custom |
| Price (yearly) | $0 | $390 per seat ($32.50/mo) | $990 per seat ($82.50/mo) | Custom |
| Projects | 1 | Unlimited | Unlimited | Unlimited |
| Rule checks + plan view | ✓ | ✓ | ✓ | ✓ |
| Propose fixes | ✓ | ✓ | ✓ | ✓ |
| **Apply** approved changes in the CAD app | — (approve shows an upgrade prompt) | ✓ | ✓ | ✓ |
| Firm rules (custom) | Starter rules only | ✓ | ✓ | ✓ |
| Chat messages / seat / month | 20 | 300 | 1 000 | Custom |
| Members | 1 | Seats bought | Seats bought | Seats bought |
| Two-approval mode, audit CSV export | — | — | ✓ | ✓ |
| Rule overrides per project | — | ✓ | ✓ | ✓ |
| SSO, data residency, self-hosting | — | — | — | ✓ |
| Support | Community | Email | Priority | Named contact |

- **Trial:** 14 days of Pro on sign-up, no card. On expiry the firm drops to Free; rules, projects and history are kept.
- **Seats:** a seat is a member who can propose, approve or chat. Viewers are free and unlimited.
- **Founding firms (pilot):** Pro for up to 3 seats at $390/year total, locked. Applied as a coupon.

---

## 2. Entitlements (how limits are enforced)

```python
PLANS = {
  "free":  {"projects": 1,   "apply": False, "custom_rules": False, "chat_per_seat": 20,   "two_approvals": False, "audit_csv": False},
  "pro":   {"projects": None,"apply": True,  "custom_rules": True,  "chat_per_seat": 300,  "two_approvals": False, "audit_csv": False},
  "firm":  {"projects": None,"apply": True,  "custom_rules": True,  "chat_per_seat": 1000, "two_approvals": True,  "audit_csv": True},
}
```
- Checked on the server at the action (create project, approve, save rule, chat, export). The UI shows an upgrade prompt, but the server is the gate.
- **Over a limit:** HTTP `402` with `{error: {code: "plan_limit", limit: "projects", plan: "free"}}`.
- Chat usage is counted per firm per month in `usage`; at 80% the admins see a banner, and at 100% chat pauses until the next month or a top-up.
- **Top-ups:** +500 chat messages for $10, one-off purchase.
- **Downgrades never delete data.** Extra projects become read-only and custom rules are disabled (kept).

---

## 3. Payments

**Provider:** Stripe Billing (or Lemon Squeezy as merchant of record if you don't want to handle sales tax/VAT). 👤 You create the account and products; the app needs only API keys and price ids.

| Setting | Value |
|---|---|
| Products | Lintel Pro, Lintel Firm (per-seat, monthly + yearly prices), Chat top-up (one-off) |
| Env vars | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO_MONTH`, `…_PRO_YEAR`, `…_FIRM_MONTH`, `…_FIRM_YEAR`, `…_TOPUP` (one-off $10), `…_PILOT_YEAR` ($390/year flat, quantity 1; never edit it, so pilots keep their price) |
| Founding pilot | Staff accept a firm with `PATCH /api/staff/firms/<id>` `{"pilot": true}`; its Billing page then offers the pilot price. Pro for up to 3 seats. |

### Flow
1. Owner → Settings › Billing → choose plan, seats and interval → `POST /api/billing/checkout` → redirect to Stripe Checkout.
2. Stripe → `POST /api/billing/webhook` (signature verified):
   - `checkout.session.completed` → set `firms.plan`, `seats`, `billing_customer_id`.
   - `customer.subscription.updated` → sync plan and seats.
   - `customer.subscription.deleted` → drop to Free.
   - `invoice.payment_failed` → banner to owners; 7-day grace, then Free.
3. Owner → "Manage billing" → `POST /api/billing/portal` → Stripe customer portal (card, invoices, cancel).

### Rules
- Webhooks are idempotent: store processed event ids.
- Plan changes write an audit entry (`billing.plan_changed`).
- Seat count can't go below the current number of members; remove members first.
- Prices shown in USD; tax handled by Stripe Tax or the merchant of record.

---

## 4. What the owner must do (👤)

1. Create the Stripe (or Lemon Squeezy) account, the products and the prices.
2. Add the keys to Vercel (preview = test keys, production = live keys).
3. Set the webhook URL `https://<domain>/api/billing/webhook` and copy its secret.
4. Write the terms of service, privacy policy and refund policy pages (templates in `saas/12-revenue`).
