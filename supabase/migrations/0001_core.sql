-- Bizzmind core metadata schema. Applied with the postgres role; RLS protects
-- direct client access (Supabase JS / PostgREST). The backend uses the
-- service connection and enforces org membership itself.
create extension if not exists pgcrypto;

create table if not exists public.organizations (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  created_at  timestamptz not null default now()
);

create table if not exists public.memberships (
  org_id      uuid not null references public.organizations(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,
  role        text not null check (role in ('owner','admin','member')),
  created_at  timestamptz not null default now(),
  primary key (org_id, user_id)
);

create table if not exists public.projects (
  id          text primary key,                          -- url slug, also -> schema p_<id>
  org_id      uuid references public.organizations(id) on delete cascade,
  name        text not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  meta        jsonb not null default '{}'::jsonb,        -- files, views
  dashboard   jsonb not null default '[]'::jsonb,
  filters     jsonb not null default '[]'::jsonb,
  notes       jsonb not null default '[]'::jsonb,
  chat        jsonb not null default '[]'::jsonb,
  i18n        jsonb not null default '{}'::jsonb,        -- {lang: {hash: text}}
  progress    text
);
create index if not exists projects_org_idx on public.projects(org_id);

create table if not exists public.jobs (
  id          uuid primary key default gen_random_uuid(),
  project_id  text references public.projects(id) on delete cascade,
  kind        text not null,                             -- chat | review | deck | translate | gamma
  status      text not null default 'queued' check (status in ('queued','running','done','failed')),
  payload     jsonb not null default '{}'::jsonb,
  result      jsonb,
  error       text,
  lang        text not null default 'bg',
  created_by  uuid references auth.users(id),
  created_at  timestamptz not null default now(),
  started_at  timestamptz,
  finished_at timestamptz,
  tokens_in   integer,
  tokens_out  integer
);
create index if not exists jobs_queue_idx on public.jobs(status, created_at) where status = 'queued';
create index if not exists jobs_project_idx on public.jobs(project_id, created_at desc);

create table if not exists public.audit_log (
  id          bigserial primary key,
  org_id      uuid,
  project_id  text,
  user_id     uuid,
  action      text not null,
  detail      jsonb,
  created_at  timestamptz not null default now()
);
create index if not exists audit_org_idx on public.audit_log(org_id, created_at desc);

-- helper: is the current auth user a member of the org?
create or replace function public.is_org_member(org uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.memberships m where m.org_id = org and m.user_id = auth.uid());
$$;
create or replace function public.is_org_admin(org uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.memberships m where m.org_id = org and m.user_id = auth.uid()
                 and m.role in ('owner','admin'));
$$;

-- RLS on everything
alter table public.organizations enable row level security;
alter table public.memberships   enable row level security;
alter table public.projects      enable row level security;
alter table public.jobs          enable row level security;
alter table public.audit_log     enable row level security;

drop policy if exists org_select on public.organizations;
create policy org_select on public.organizations for select using (public.is_org_member(id));

drop policy if exists mem_select on public.memberships;
create policy mem_select on public.memberships for select using (public.is_org_member(org_id));
drop policy if exists mem_admin on public.memberships;
create policy mem_admin on public.memberships for all using (public.is_org_admin(org_id)) with check (public.is_org_admin(org_id));

drop policy if exists proj_select on public.projects;
create policy proj_select on public.projects for select using (public.is_org_member(org_id));
drop policy if exists proj_write on public.projects;
create policy proj_write on public.projects for all using (public.is_org_admin(org_id)) with check (public.is_org_admin(org_id));

drop policy if exists jobs_select on public.jobs;
create policy jobs_select on public.jobs for select
  using (exists (select 1 from public.projects p where p.id = project_id and public.is_org_member(p.org_id)));
drop policy if exists jobs_insert on public.jobs;
create policy jobs_insert on public.jobs for insert
  with check (exists (select 1 from public.projects p where p.id = project_id and public.is_org_member(p.org_id)));

drop policy if exists audit_select on public.audit_log;
create policy audit_select on public.audit_log for select using (public.is_org_admin(org_id));

-- updated_at trigger
create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;
drop trigger if exists projects_touch on public.projects;
create trigger projects_touch before update on public.projects for each row execute function public.touch_updated_at();
