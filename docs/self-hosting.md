# Self-hosting Lintel (Enterprise)

Run Lintel on your own server or cloud account so drawings, rules and the audit log never leave
your network or your chosen region. It's the same app as the hosted one, in one container plus Postgres.

## Run it

1. Install Docker with the compose plugin.
2. In the Lintel folder: copy `.env.example` to `.env` and fill it in. `POSTGRES_PASSWORD` and
   `APP_URL` (the address people will type) are required.
3. `docker compose up -d`
4. Open `<APP_URL>/signup` and create the first firm. That person is its owner.

The database tables are created on first start, and upgrades apply new migrations automatically.

Put a TLS proxy (Caddy, nginx, your load balancer) in front of port 8002 and serve it over https.
Session cookies are marked Secure whenever `APP_URL` starts with `https`.

## Data region

`LINTEL_REGION` names where this server keeps data (for example `eu-west` or `on-premises`). Every
firm created on the server records it, and Settings › Firm shows it to the firm. For hosted
Enterprise customers who need a specific region, Lintel runs a separate deployment and database in
that region. Data isn't copied between deployments.

## Plans on your own server

A firm starts on the 14-day Pro trial like on the hosted app. To put it on Enterprise terms, call
the staff endpoint with your `LINTEL_STAFF_TOKEN`:

```bash
curl -X PATCH "$APP_URL/api/staff/firms/<firm id>" \
  -H "x-staff-token: $LINTEL_STAFF_TOKEN" -H "content-type: application/json" \
  -d '{"plan": "enterprise", "seats": 40, "chat_cap_override": 20000}'
```

`chat_cap_override` is the firm's assistant messages per month (the custom assistant limit).
The firm id is in Settings › Firm and in the audit log.

## Single sign-on

Enterprise owners turn it on in Settings › Firm › Single sign-on, with any OpenID Connect provider
(Okta, Microsoft Entra ID, Google Workspace, Keycloak and others):

1. In the provider, create a web app (confidential client) with the redirect URL
   `<APP_URL>/api/auth/sso/callback` and the scopes `openid email profile`.
2. In Lintel, enter the issuer URL, client ID, client secret and your email domains.
3. Optionally tick **Require SSO**. Members then can't sign in with a password. Owners still can,
   so a provider outage can't lock the firm out.

People who sign in with SSO for the first time join as the role you choose. If there's no free
seat they join as Viewers until an admin gives them one.

## Backups

Back up the `lintel-db` volume, or run `pg_dump` against it, on your usual schedule. That one
database holds everything: accounts, projects, model snapshots, rules and the audit log.
