-- Lintel schema v1. Portable: db.migrate() rewrites the few SQLite-only bits for Postgres.
-- Timestamps are epoch seconds; JSON columns are text.

create table users (
  id text primary key,
  email text collate nocase unique not null,
  name text not null,
  password_hash text not null,
  email_verified_at real,
  created_at real not null,
  last_login_at real,
  deleted_at real
);

create table firms (
  id text primary key,
  name text not null,
  plan text not null default 'free',
  seats integer not null default 1,
  two_approvals integer not null default 0,
  chat_enabled integer not null default 1,
  trial_ends_at real,
  billing_customer_id text,
  created_at real not null,
  deleted_at real
);

create table memberships (
  user_id text not null references users(id) on delete cascade,
  firm_id text not null references firms(id) on delete cascade,
  role text not null check (role in ('owner','admin','approver','member','viewer')),
  created_at real not null,
  primary key (user_id, firm_id)
);

create table invites (
  id text primary key,
  firm_id text not null references firms(id) on delete cascade,
  email text collate nocase not null,
  role text not null,
  token_hash text not null unique,
  invited_by text references users(id),
  created_at real not null,
  expires_at real not null,
  accepted_at real,
  cancelled_at real
);

create table sessions (
  id_hash text primary key,
  user_id text not null references users(id) on delete cascade,
  firm_id text not null references firms(id) on delete cascade,
  csrf text not null,
  created_at real not null,
  expires_at real not null,
  user_agent text
);

create table password_resets (
  token_hash text primary key,
  user_id text not null references users(id) on delete cascade,
  expires_at real not null,
  used_at real
);

create table plugin_tokens (
  id text primary key,
  user_id text not null references users(id) on delete cascade,
  firm_id text not null references firms(id) on delete cascade,
  name text not null,
  token_hash text not null unique,
  prefix text not null,
  last_used_at real,
  revoked_at real,
  created_at real not null
);

create table projects (
  id text primary key,
  firm_id text not null references firms(id) on delete cascade,
  ext_key text,
  name text not null,
  host text,
  archived_at real,
  last_plugin_poll_at real,
  created_at real not null
);
create index projects_firm on projects (firm_id, archived_at);
create unique index projects_ext on projects (firm_id, ext_key);

create table snapshots (
  id integer primary key autoincrement,
  project_id text not null references projects(id) on delete cascade,
  host text,
  taken_at real not null,
  elements text not null
);
create index snapshots_project on snapshots (project_id, id);

create table rules (
  firm_id text not null references firms(id) on delete cascade,
  id text not null,
  data text not null,
  status text not null check (status in ('active','disabled','proposed')),
  created_by text,
  created_at real not null,
  primary key (firm_id, id)
);

create table project_rule_overrides (
  project_id text not null references projects(id) on delete cascade,
  rule_id text not null,
  value real,
  enabled integer not null default 1,
  primary key (project_id, rule_id)
);

create table changesets (
  id text primary key,
  project_id text not null references projects(id) on delete cascade,
  title text not null,
  reason text,
  ops text not null,
  status text not null check (status in ('proposed','approved','applied','failed','rejected','reverted')),
  source text not null check (source in ('rule','agent','revert','manual')),
  rule_id text,
  reverts text,
  created_by text,
  error text,
  created_at real not null,
  updated_at real not null
);
create index changesets_project on changesets (project_id, status);

create table approvals (
  changeset_id text not null references changesets(id) on delete cascade,
  user_id text not null,
  decision text not null check (decision in ('approve','reject')),
  at real not null,
  primary key (changeset_id, user_id)
);

create table comments (
  id text primary key,
  changeset_id text not null references changesets(id) on delete cascade,
  user_id text not null,
  body text not null,
  created_at real not null
);

create table chat_threads (
  project_id text not null references projects(id) on delete cascade,
  user_id text not null,
  messages text not null,
  updated_at real not null,
  primary key (project_id, user_id)
);

create table usage (
  firm_id text not null references firms(id) on delete cascade,
  month text not null,
  chat_messages integer not null default 0,
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  primary key (firm_id, month)
);

create table audit (
  id integer primary key autoincrement,
  firm_id text,
  project_id text,
  actor text not null,
  actor_name text,
  action text not null,
  target text,
  detail text not null,
  at real not null
);
create index audit_firm on audit (firm_id, id);

create table waitlist (
  id integer primary key autoincrement,
  email text collate nocase unique not null,
  data text not null,
  at real not null
);

create table billing_events (
  id text primary key,
  at real not null
);
