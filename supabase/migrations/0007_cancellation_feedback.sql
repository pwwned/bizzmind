-- Why subscriptions get cancelled — collected in-app before the cancel call.
create table if not exists public.cancellation_feedback (
  id              bigserial primary key,
  org_id          uuid references public.organizations(id) on delete set null,
  subscription_id text,
  reason          text not null,
  comment         text not null default '',
  created_at      timestamptz not null default now()
);
alter table public.cancellation_feedback enable row level security;  -- service connection only
