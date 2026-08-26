-- Paddle billing: processed-event ledger (idempotency) + org links to Paddle.
create table if not exists public.webhook_events (
  id         text primary key,              -- Paddle event_id (evt_...)
  type       text not null,
  created_at timestamptz not null default now()
);
alter table public.webhook_events enable row level security;   -- service connection only

alter table public.organizations add column if not exists paddle_customer_id     text;
alter table public.organizations add column if not exists paddle_subscription_id text;
