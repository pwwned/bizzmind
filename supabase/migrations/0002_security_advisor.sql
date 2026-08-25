-- Fixes for Supabase Security Advisor findings.
-- 1) SECURITY DEFINER helpers: only signed-in users may call them.
revoke execute on function public.is_org_member(uuid) from public, anon;
revoke execute on function public.is_org_admin(uuid)  from public, anon;
grant  execute on function public.is_org_member(uuid) to authenticated, service_role;
grant  execute on function public.is_org_admin(uuid)  to authenticated, service_role;
-- 2) compat round() in every project schema: pin search_path.
do $$
declare r record;
begin
  for r in select n.nspname as s from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where p.proname = 'round' and n.nspname like 'p\_%' group by n.nspname loop
    execute format('alter function %I.round(double precision, integer) set search_path = ''''', r.s);
    execute format('alter function %I.round(bigint, integer) set search_path = ''''', r.s);
  end loop;
end $$;
