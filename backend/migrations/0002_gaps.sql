-- Schema v2: message top-ups, Enterprise settings (custom assistant limit, SSO, data region)
-- and learned-rule suggestions the firm dismissed.

alter table usage add column topup_messages integer not null default 0;

alter table firms add column chat_cap_override integer;
alter table firms add column region text;
alter table firms add column sso text;

create table sso_states (
  state_hash text primary key,
  firm_id text not null references firms(id) on delete cascade,
  nonce text not null,
  verifier text not null,
  expires_at double precision not null
);

create table rule_suggestions_dismissed (
  firm_id text not null references firms(id) on delete cascade,
  key text not null,
  at double precision not null,
  primary key (firm_id, key)
);
