-- Schema v3: founding pilot firms (Pro for up to 3 seats at a fixed yearly price, set by Lintel staff).

alter table firms add column pilot integer not null default 0;
