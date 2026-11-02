# Lintel data model and API reference

Architecture: [architecture.md](architecture.md) · Security rules: [security.md](security.md).

---

## 1. Database schema (Postgres)

```sql
-- 0001_init.sql
create extension if not exists citext;

create table users (
  id            text primary key,                 -- "usr_" + random
  email         citext unique not null,
  name          text not null,
  password_hash text not null,                    -- argon2id
  email_verified_at timestamptz,
  created_at    timestamptz not null default now(),
  last_login_at timestamptz
);

create table firms (
  id          text primary key,                   -- "frm_"
  name        text not null,
  plan        text not null default 'free',       -- free | pro | firm | enterprise
  seats       int  not null default 1,
  two_approvals boolean not null default false,
  billing_customer_id text,
  created_at  timestamptz not null default now()
);

create table memberships (
  user_id  text references users(id) on delete cascade,
  firm_id  text references firms(id) on delete cascade,
  role     text not null check (role in ('owner','admin','approver','member','viewer')),
  created_at timestamptz not null default now(),
  primary key (user_id, firm_id)
);

create table invites (
  id text primary key, firm_id text not null references firms(id) on delete cascade,
  email citext not null, role text not null, token_hash text not null unique,
  invited_by text references users(id), expires_at timestamptz not null, accepted_at timestamptz
);

create table sessions (
  id_hash text primary key, user_id text not null references users(id) on delete cascade,
  firm_id text not null references firms(id) on delete cascade, csrf text not null,
  created_at timestamptz not null default now(), expires_at timestamptz not null,
  ip inet, user_agent text
);

create table password_resets (
  token_hash text primary key, user_id text not null references users(id) on delete cascade,
  expires_at timestamptz not null, used_at timestamptz
);

create table plugin_tokens (
  id text primary key, user_id text not null references users(id) on delete cascade,
  firm_id text not null references firms(id) on delete cascade, name text not null,
  token_hash text not null unique, prefix text not null,          -- first 8 chars, shown in UI
  last_used_at timestamptz, revoked_at timestamptz, created_at timestamptz not null default now()
);

create table projects (
  id text primary key, firm_id text not null references firms(id) on delete cascade,
  name text not null, host text, archived_at timestamptz,
  last_plugin_poll_at timestamptz, created_at timestamptz not null default now()
);
create index on projects (firm_id, archived_at);

create table snapshots (
  id bigserial primary key, project_id text not null references projects(id) on delete cascade,
  host text, taken_at timestamptz not null default now(), elements jsonb not null
);
create index on snapshots (project_id, id desc);

create table rules (
  id text primary key, firm_id text not null references firms(id) on delete cascade,
  data jsonb not null,     -- {name, kind, applies_to, where, prop, value, unit, ref, severity, fixable, source}
  status text not null check (status in ('active','disabled','proposed')),
  created_by text references users(id), created_at timestamptz not null default now()
);
create index on rules (firm_id, status);

create table project_rule_overrides (
  project_id text references projects(id) on delete cascade,
  rule_id text references rules(id) on delete cascade,
  value numeric, enabled boolean not null default true,
  primary key (project_id, rule_id)
);

create table changesets (
  id text primary key, project_id text not null references projects(id) on delete cascade,
  title text not null, reason text, ops jsonb not null,   -- [{op, element, element_name, prop, from, to}]
  status text not null check (status in ('proposed','approved','applied','failed','rejected','reverted')),
  source text not null check (source in ('rule','agent','revert','manual')),
  rule_id text, reverts text references changesets(id),
  created_by text references users(id), error text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index on changesets (project_id, status);

create table approvals (
  changeset_id text references changesets(id) on delete cascade,
  user_id text references users(id), decision text check (decision in ('approve','reject')),
  at timestamptz not null default now(), primary key (changeset_id, user_id)
);

create table comments (
  id text primary key, changeset_id text not null references changesets(id) on delete cascade,
  user_id text not null references users(id), body text not null check (length(body) <= 4000),
  created_at timestamptz not null default now()
);

create table chat_threads (
  project_id text references projects(id) on delete cascade,
  user_id text references users(id) on delete cascade,
  messages jsonb not null default '[]', updated_at timestamptz not null default now(),
  primary key (project_id, user_id)
);

create table usage (
  firm_id text references firms(id) on delete cascade, month date not null,
  chat_messages int not null default 0, input_tokens bigint not null default 0, output_tokens bigint not null default 0,
  primary key (firm_id, month)
);

create table audit (
  id bigserial primary key, firm_id text references firms(id) on delete cascade,
  project_id text, actor text not null,            -- "usr_…", "host:rhino8", "agent", "system"
  action text not null, target text, detail jsonb not null default '{}',
  at timestamptz not null default now()
);
create index on audit (firm_id, at desc);

create table waitlist (
  id bigserial primary key, email citext unique not null, data jsonb not null default '{}',
  at timestamptz not null default now()
);
```

**Tenancy rule:** every table under a firm is reached through `firm_id` (directly or via `project_id`). Repository functions take `firm_id` as their first argument and add it to every `WHERE`. Tests check that firm B can never read firm A's rows (see [testing.md](testing.md)).

---

## 2. Element snapshot format (plugin → server)

```json
{
  "project": "prj_8f2…", "host": "rhino8", "name": "Clinic GF",
  "elements": [
    {"id": "R-corr", "type": "room", "props": {"name": "Main corridor", "use": "corridor", "area_m2": 70.0, "clear_width_mm": 1000},
     "geom": {"outline": [[0,0],[70000,0],[70000,1000],[0,1000]]}},
    {"id": "D-03", "type": "door", "props": {"name": "Exam 1 door", "clear_width_mm": 760, "rooms": ["R-corr","R-exam1"], "exit": false},
     "geom": {"location": [3500,1000]}},
    {"id": "S-01", "type": "stair", "props": {"riser_mm": 190, "tread_mm": 254, "risers": 18, "total_rise_mm": 3420}, "geom": {"location": [40000,-2500]}},
    {"id": "W-01", "type": "wall", "props": {"length_mm": 70000, "thickness_mm": 200}, "geom": {"start": [0,0], "end": [70000,0]}}
  ]
}
```
Units: millimetres; areas in m². Element ids are stable host ids.

---

## 3. API

Base: `/api`. JSON in and out. Browser calls send the session cookie plus the `X-CSRF-Token` header on writes. Plugin calls send `Authorization: Bearer <plugin token>`.

### Errors
```json
{ "error": { "code": "forbidden", "message": "Approvers only." } }
```
| Status | code | When |
|---|---|---|
| 400 | `bad_request` | malformed JSON |
| 401 | `unauthenticated` | no or expired session or token |
| 403 | `forbidden` | role too low or CSRF missing |
| 404 | `not_found` | missing, **or belongs to another firm** |
| 409 | `conflict` | wrong state (e.g. approving a rejected change set), drift |
| 422 | `invalid` | validation; includes `fields: {name: "message"}` |
| 429 | `rate_limited` | too many requests; `Retry-After` header |

### Auth
| Method | Path | Body → Result |
|---|---|---|
| POST | `/auth/signup` | `{name, email, password, firm_name}` → 201 `{user, firm}` + cookie |
| POST | `/auth/login` | `{email, password}` → 200 `{user, firms}` + cookie |
| POST | `/auth/logout` | → 204 |
| POST | `/auth/reset/request` | `{email}` → 202 (always, never reveals whether the email exists) |
| POST | `/auth/reset/confirm` | `{token, password}` → 204 |
| GET | `/me` | → `{user, firm, role, firms:[…], csrf}` |
| POST | `/me/firm` | `{firm_id}` → switch the current firm |

### Firm and members (Admin+ unless noted)
| Method | Path | Notes |
|---|---|---|
| GET / PATCH | `/firm` | name, two_approvals (Owner/Admin) |
| GET | `/members` | any role |
| PATCH | `/members/:user_id` | `{role}`; cannot demote the last owner |
| DELETE | `/members/:user_id` | |
| POST | `/invites` | `{email, role}` → sends email |
| GET | `/invites/:token` | public: invite info |
| POST | `/invites/:token/accept` | `{name, password}` or signed-in user |
| DELETE | `/invites/:id` | cancel |

### Plugin tokens (each user, own tokens)
| Method | Path | Notes |
|---|---|---|
| GET | `/tokens` | list (prefix, name, last used) |
| POST | `/tokens` | `{name}` → `{id, token}`; the token is shown **once** |
| DELETE | `/tokens/:id` | revoke |

### Projects
| Method | Path | Notes |
|---|---|---|
| GET | `/projects?archived=0` | list with counts |
| POST | `/projects` | `{name}` (Member+) |
| GET | `/projects/:id` | `{project, snapshot_at, host, elements, issues, egress, changesets, plugin_seen_at}` |
| PATCH | `/projects/:id` | `{name, archived}` (Admin+) |
| POST | `/projects/sample` | creates the sample clinic project (onboarding) |
| POST | `/projects/:id/issues/:issue_id/fix` | → `{changeset}` (Member+) |

### Change sets
| Method | Path | Notes |
|---|---|---|
| GET | `/approvals` | all proposed change sets in the firm |
| POST | `/changesets/:id/approve` | Approver+ → `{status}` |
| POST | `/changesets/:id/reject` | Approver+ |
| POST | `/changesets/:id/revert` | Approver+ → `{changeset}` |
| GET / POST | `/changesets/:id/comments` | Member+ to post |

### Rules
| Method | Path | Notes |
|---|---|---|
| GET | `/rules` | any role |
| POST | `/rules` | create or update (Admin+) |
| POST | `/rules/:id/status` | `{status: active|disabled}` (Admin+) |
| DELETE | `/rules/:id` | Admin+ |
| POST | `/rules/import` | JSON array or CSV text; `?dry_run=1` returns a preview with row errors |
| GET | `/rules/export` | JSON download |
| PUT | `/projects/:id/rules/:rule_id` | override `{value, enabled}` (Admin+) |

### Chat
| Method | Path | Notes |
|---|---|---|
| GET | `/projects/:id/chat` | the signed-in user's thread |
| POST | `/projects/:id/chat` | `{message}` → `text/event-stream` of `{type: text|changeset|rule|done|error}` |

### Audit
| Method | Path | Notes |
|---|---|---|
| GET | `/audit?project=&actor=&action=&from=&to=&cursor=` | paginated (50) |
| GET | `/audit.csv?…` | CSV export (Admin+) |

### Plugin (Bearer token)
| Method | Path | Body → Result |
|---|---|---|
| POST | `/plugin/snapshot` | snapshot (§2) → `{project, issues}`; creates the project in the token's firm if new |
| GET | `/plugin/pending?project=` | → approved change sets for the project |
| POST | `/plugin/result` | `{changeset, ok, error?, host}` → 204 |

### Billing
| Method | Path | Notes |
|---|---|---|
| POST | `/billing/checkout` | `{plan, seats, interval}` → `{url}` (Owner) |
| POST | `/billing/portal` | → `{url}` (Owner) |
| POST | `/billing/webhook` | provider webhook (signature checked) |

### Public
| Method | Path | Notes |
|---|---|---|
| POST | `/waitlist` | marketing pilot form (exists) |
| GET | `/health` | `{ok, db, version}` for uptime checks |
