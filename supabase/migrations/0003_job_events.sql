-- Live progress lines for background jobs (served to the UI by any API instance).
create table if not exists public.job_events (
  job_id      uuid not null references public.jobs(id) on delete cascade,
  seq         integer not null,
  kind        text not null default 'info',
  text        text not null,
  created_at  timestamptz not null default now(),
  primary key (job_id, seq)
);
alter table public.job_events enable row level security;
drop policy if exists job_events_select on public.job_events;
create policy job_events_select on public.job_events for select
  using (exists (select 1 from public.jobs j join public.projects p on p.id = j.project_id
                 where j.id = job_id and public.is_org_member(p.org_id)));
