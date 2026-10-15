-- Melbourne House Hunt, step 2: shared settings for each hunt (who's paying, the split, budget, bedrooms).
-- Paste this whole file into Supabase > SQL Editor > New query, then press Run. Safe to run again.
-- Each hunt is identified by its code (the old "house code"), exactly like votes and notes.

create table if not exists public.hunts (
  house text primary key,
  settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
alter table public.hunts enable row level security;
revoke all on public.hunts from anon, authenticated;

-- Same as before, plus the hunt's settings
create or replace function public.house_state(p_house text) returns json
language plpgsql security definer set search_path = public as $$
begin
  perform check_house(p_house);
  return json_build_object(
    'votes', coalesce((select json_agg(v) from (select person, listing_id, vote from votes where house = p_house) v), '[]'),
    'notes', coalesce((select json_agg(n order by n.created_at) from (select id, listing_id, person, body, created_at from notes where house = p_house) n), '[]'),
    'added', coalesce((select json_agg(a order by a.created_at) from (select id, person, data, created_at from added where house = p_house) a), '[]'),
    'settings', (select settings from hunts where house = p_house)
  );
end $$;

create or replace function public.save_settings(p_house text, p_settings jsonb) returns void
language plpgsql security definer set search_path = public as $$
begin
  perform check_house(p_house);
  if pg_column_size(p_settings) > 20000 then raise exception 'Settings too large'; end if;
  insert into hunts (house, settings) values (p_house, p_settings)
  on conflict (house) do update set settings = excluded.settings, updated_at = now();
end $$;

revoke all on function public.save_settings(text, jsonb) from public;
grant execute on function public.house_state(text), public.save_settings(text, jsonb) to anon, authenticated;
