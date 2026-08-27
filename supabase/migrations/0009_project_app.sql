-- AI-generated mini-app spec per project (forms, KPIs, live lists over the data)
alter table public.projects add column if not exists app jsonb not null default '{}'::jsonb;
