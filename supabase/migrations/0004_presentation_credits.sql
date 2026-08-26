-- Presentation credits, metered per organization. Users see and spend
-- Bizzmind credits; the engine behind them is not exposed.
alter table public.organizations add column if not exists pres_quota integer not null default 100;
alter table public.organizations add column if not exists pres_used  integer not null default 0;

create table if not exists public.pres_generations (
  gid        text primary key,              -- engine generation id (unguessable)
  org_id     uuid not null references public.organizations(id) on delete cascade,
  project_id text not null,
  credits    integer,                       -- deducted on completion (once)
  status     text not null default 'pending',
  created_at timestamptz not null default now()
);
create index if not exists pres_gen_org_idx on public.pres_generations(org_id, created_at desc);
alter table public.pres_generations enable row level security;  -- service connection only
