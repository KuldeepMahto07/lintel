# Lintel security and privacy

What protects accounts, firm data and models, and the rules every endpoint must follow.

---

## 1. Threats we design for

| Threat | Control |
|---|---|
| Someone signs in as another user | argon2id password hashes, login rate limits, session rotation, optional email verification |
| One firm sees another firm's data | `firm_id` on every query, 404 for other firms' ids, isolation tests in CI |
| A member approves changes they shouldn't | Role checks on the server for every write; the UI hiding buttons is not the control |
| A stolen plugin token | Tokens stored only as SHA-256 hashes, per-user, revocable, prefix shown for identification, last-used tracking |
| Cross-site request forgery | `SameSite=Lax` cookie + `X-CSRF-Token` on every non-GET request |
| XSS through model data or names | All text rendered with `textContent` / escaping; no `innerHTML` with user or model data; strict CSP |
| The AI changes a model on its own | The agent has no approve/apply tool; approval is a server-side state transition by an authorised user only |
| Prompt injection via model element names | The agent treats element data as data; its tools are limited to read, check and propose; proposals still need a human |
| Lost or corrupted data | Daily backups, point-in-time restore (Neon), migrations reviewed in PRs |

---

## 2. Authentication

- **Passwords:** minimum 10 characters, checked against a top-10k common-password list; hashed with argon2id (`time_cost=3, memory_cost=64MB`).
- **Sessions:**
  - The cookie holds 32 random bytes.
  - The server stores only their SHA-256 hash.
  - Cookie flags: `HttpOnly; Secure; SameSite=Lax`, 30-day expiry.
  - Rotated on login and on role change; deleted on logout and password change (all sessions).
- **Password reset:** single-use token, 30-minute expiry, the hash stored. The response is identical whether or not the email exists.
- **Invites:** single-use token, 7-day expiry, bound to the invited email.
- **Rate limits:**
  - Login: 5 tries per 15 min per email+IP.
  - Reset requests: 3 per hour per email.
  - Plugin endpoints: 120 per minute per token.
  - Chat: per firm, by plan.
- **Later:** TOTP two-factor, SAML/OIDC SSO for Enterprise.

---

## 3. Authorisation (role matrix)

| Action | Viewer | Member | Approver | Admin | Owner |
|---|:-:|:-:|:-:|:-:|:-:|
| View projects, issues, history, audit | ✓ | ✓ | ✓ | ✓ | ✓ |
| Propose fixes, chat, comment, create project | | ✓ | ✓ | ✓ | ✓ |
| Approve / reject / revert change sets | | | ✓ | ✓ | ✓ |
| Manage rules, overrides, import | | | | ✓ | ✓ |
| Invite / remove members, change roles | | | | ✓ | ✓ |
| Export audit CSV | | | | ✓ | ✓ |
| Billing, delete firm, transfer ownership | | | | | ✓ |
| Create own plugin tokens | | ✓ | ✓ | ✓ | ✓ |

Implemented as FastAPI dependencies (`require_role("approver")`) on each route; covered by a table-driven test that calls every write endpoint with every role.

---

## 4. Tenancy isolation

- The current firm comes only from the session (or the plugin token), never from the request body.
- Repository functions require `firm_id`; queries on child tables join through `projects.firm_id`.
- A resource id from another firm returns **404**, not 403, so ids can't be probed.
- CI test: create firms A and B, then call every endpoint as B with A's ids; every response must be 404.

---

## 5. Data handling and privacy

- **What we store:** account data, firm rules, model snapshots (element ids, properties, simple geometry), change sets, chat history, audit log. No full CAD files.
- **AI processing:** a chat request sends the user's message plus relevant model data and rules to Anthropic's API. Per Anthropic's commercial terms, API data isn't used for training; state this in the privacy policy. Firms can disable chat in Settings.
- **Retention:**
  - Snapshots: the last 50 per project.
  - Audit: kept for the life of the firm. Exportable.
  - Deleted firms are purged after 30 days.
- **Export and deletion:** the owner can export all firm data (JSON) and delete the firm. User deletion removes personal data and keeps audit entries as "deleted user".
- **Building codes:** Lintel stores numbers and section references only, never code text.

---

## 6. Web security headers

```
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
```
The Rhino WebView loads `/app` from the same origin, so `frame-ancestors 'self'` doesn't block it.

---

## 7. Secrets and operations

- Secrets live only in the hosting provider's environment variables; `.env` files are git-ignored; CI runs a secret scan on every push.
- Separate keys for preview and production (Neon branch DB, Stripe test keys).
- Dependencies: `pip-audit` in CI; Dependabot for weekly updates.
- Logs never contain passwords, tokens, session ids or chat contents. Request logs keep user id, firm id, route, status and duration.

---

## 8. Incident basics

1. Revoke affected sessions and tokens (admin endpoint + script).
2. Rotate secrets (`SESSION_SECRET` rotation logs everyone out).
3. Restore from a point-in-time backup if data was altered.
4. Tell affected firms within 72 hours with what happened and what they should do.
