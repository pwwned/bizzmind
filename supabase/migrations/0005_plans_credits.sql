-- Plans + unified credit pool per organization. One currency, different
-- action prices (analysis / chat / presentation); breakdown kept in events.
alter table public.organizations add column if not exists plan          text    not null default 'free';
alter table public.organizations add column if not exists credits_quota integer not null default 1000; -- Free plan allowance (must track plans.PLANS['free']['credits'])
alter table public.organizations add column if not exists credits_extra integer not null default 0;    -- purchased top-ups
alter table public.organizations add column if not exists credits_used  integer not null default 0;
alter table public.organizations add column if not exists auto_recharge boolean not null default false;

create table if not exists public.credit_events (
  id         bigserial primary key,
  org_id     uuid not null references public.organizations(id) on delete cascade,
  project_id text,
  kind       text not null,                 -- analysis | chat | presentation
  credits    integer not null,
  created_at timestamptz not null default now()
);
create index if not exists credit_events_org_idx on public.credit_events(org_id, created_at desc);
alter table public.credit_events enable row level security;   -- service connection only
alter table public.organizations add column if not exists credits_renewed_at timestamptz not null default now();
alter table public.organizations add column if not exists billing jsonb not null default '{}'::jsonb;
