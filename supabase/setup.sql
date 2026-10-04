-- Melbourne House Hunt: shared votes, notes and added listings for the GitHub-hosted page.
-- Paste this whole file into Supabase > SQL Editor > New query, then press Run. Safe to run again.
--
-- How access works: the page only has Supabase's public "anon" key, which is visible to anyone
-- who opens the page. So the tables are closed to that key entirely, and every read or write goes
-- through the functions below, which require the house code. Each house code is its own separate
-- space: someone who finds the page but doesn't know your code sees nothing of yours.

create table if not exists public.votes (
  house text not null,
  person text not null check (char_length(person) between 1 and 30),
  listing_id text not null,
  vote text not null check (vote in ('love', 'maybe', 'nope')),
  updated_at timestamptz not null default now(),
  primary key (house, person, listing_id)
);

create table if not exists public.notes (
  id uuid primary key default gen_random_uuid(),
  house text not null,
  listing_id text not null,
  person text not null check (char_length(person) between 1 and 30),
  body text not null check (char_length(body) between 1 and 500),
  created_at timestamptz not null default now()
);

create table if not exists public.added (
  id uuid primary key default gen_random_uuid(),
  house text not null,
  person text not null check (char_length(person) between 1 and 30),
  data jsonb not null,
  created_at timestamptz not null default now()
);

-- Lock the tables: no direct access with the public key.
alter table public.votes enable row level security;
alter table public.notes enable row level security;
alter table public.added enable row level security;
revoke all on public.votes, public.notes, public.added from anon, authenticated;

create or replace function public.check_house(p_house text) returns void
language plpgsql immutable as $$
begin
  if p_house is null or char_length(p_house) < 6 or char_length(p_house) > 60 then
    raise exception 'House code must be 6 to 60 characters';
  end if;
end $$;

create or replace function public.house_state(p_house text) returns json
language plpgsql security definer set search_path = public as $$
begin
  perform check_house(p_house);
  return json_build_object(
    'votes', coalesce((select json_agg(v) from (select person, listing_id, vote from votes where house = p_house) v), '[]'),
    'notes', coalesce((select json_agg(n order by n.created_at) from (select id, listing_id, person, body, created_at from notes where house = p_house) n), '[]'),
    'added', coalesce((select json_agg(a order by a.created_at) from (select id, person, data, created_at from added where house = p_house) a), '[]')
  );
end $$;

create or replace function public.set_vote(p_house text, p_person text, p_listing text, p_vote text) returns void
language plpgsql security definer set search_path = public as $$
begin
  perform check_house(p_house);
  if p_vote is null then
    delete from votes where house = p_house and person = p_person and listing_id = p_listing;
  else
    insert into votes (house, person, listing_id, vote) values (p_house, p_person, p_listing, p_vote)
    on conflict (house, person, listing_id) do update set vote = excluded.vote, updated_at = now();
  end if;
end $$;

create or replace function public.add_note(p_house text, p_person text, p_listing text, p_body text) returns void
language plpgsql security definer set search_path = public as $$
begin
  perform check_house(p_house);
  if (select count(*) from notes where house = p_house) >= 2000 then raise exception 'Note limit reached'; end if;
  insert into notes (house, listing_id, person, body) values (p_house, p_listing, p_person, p_body);
end $$;

create or replace function public.delete_note(p_house text, p_person text, p_id uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  perform check_house(p_house);
  delete from notes where house = p_house and person = p_person and id = p_id;
end $$;

create or replace function public.add_listing(p_house text, p_person text, p_data jsonb) returns void
language plpgsql security definer set search_path = public as $$
begin
  perform check_house(p_house);
  if (select count(*) from added where house = p_house) >= 300 then raise exception 'Listing limit reached'; end if;
  if pg_column_size(p_data) > 20000 then raise exception 'Listing too large'; end if;
  insert into added (house, person, data) values (p_house, p_person, p_data);
end $$;

-- Used by Claude to fill in location scores for listings housemates add.
create or replace function public.update_listing(p_house text, p_id uuid, p_data jsonb) returns void
language plpgsql security definer set search_path = public as $$
begin
  perform check_house(p_house);
  update added set data = data || p_data where house = p_house and id = p_id;
end $$;

revoke all on function public.house_state(text), public.set_vote(text, text, text, text), public.add_note(text, text, text, text),
  public.delete_note(text, text, uuid), public.add_listing(text, text, jsonb), public.update_listing(text, uuid, jsonb) from public;
grant execute on function public.house_state(text), public.set_vote(text, text, text, text), public.add_note(text, text, text, text),
  public.delete_note(text, text, uuid), public.add_listing(text, text, jsonb), public.update_listing(text, uuid, jsonb) to anon, authenticated;
