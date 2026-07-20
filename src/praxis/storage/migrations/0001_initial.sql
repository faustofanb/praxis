create table if not exists runtime_state (
    scope text not null,
    key text not null,
    value text not null,
    updated_at text not null,
    primary key (scope, key)
);

create table if not exists requirements (
    requirement_id text primary key,
    short_name text not null,
    status text not null,
    original_request text not null,
    systems_json text not null,
    domains_json text not null,
    created_at text not null,
    updated_at text not null
);

create table if not exists outbox (
    id integer primary key,
    topic text not null,
    payload text not null,
    created_at text not null,
    processed_at text
);

create table if not exists audit_events (
    sequence_number integer primary key,
    audit_id text not null unique,
    event text not null,
    code text not null,
    details text not null,
    previous_hash text,
    event_hash text not null,
    created_at text not null
);

create index if not exists idx_outbox_pending on outbox(processed_at, id);
create index if not exists idx_requirements_short_name on requirements(short_name, status);
