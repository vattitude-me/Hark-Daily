-- Morning Brief Voice: Supabase schema.
-- Paste into Supabase → SQL Editor → New query → Run. Safe to re-run.
--
-- Who writes what:
--   * The PWA (signed-in users, publishable key) reads its own briefings and manages its own links,
--     settings and push subscriptions. Row-level security keeps every user to their own rows.
--   * The Linux worker (secret key, bypasses RLS) reads everyone's links, writes briefings,
--     uploads MP3s and publishes the shared app_status row.

-- ---------------------------------------------------------------- profiles
create table if not exists public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  email       text,
  is_admin    boolean not null default false,
  -- Unguessable folder name for this user's MP3s in the public bucket.
  feed_token  text not null unique default replace(gen_random_uuid()::text, '-', ''),
  settings    jsonb not null default '{}'::jsonb,
  -- Written by the worker: last build time, last error, notes for the user.
  status      jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email) on conflict (id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Users created before this script ran.
insert into public.profiles (id, email) select id, email from auth.users on conflict (id) do nothing;

-- ----------------------------------------------------------------- sources
-- user_id null = built-in source shared by everyone (seeded by the worker).
create table if not exists public.sources (
  id              bigint generated always as identity primary key,
  user_id         uuid default auth.uid() references auth.users (id) on delete cascade,
  name            text not null check (char_length(name) <= 200),
  url             text not null check (char_length(url) <= 2000 and url ~* '^https?://'),
  feed_url        text,
  kind            text not null default 'auto' check (kind in ('auto', 'feed', 'page', 'article')),
  section         text not null default 'custom' check (section in ('canada', 'tech', 'custom')),
  enabled         boolean not null default true,
  weight          real not null default 1.0,
  created_at      timestamptz not null default now(),
  last_fetched_at timestamptz,
  last_status     text,
  last_count      integer,
  consumed_at     timestamptz,
  unique nulls not distinct (user_id, url)
);
create index if not exists sources_user_idx on public.sources (user_id);

-- --------------------------------------------------------------- briefings
create table if not exists public.briefings (
  user_id     uuid not null references auth.users (id) on delete cascade,
  date        date not null,
  data        jsonb not null,
  audio_path  text,
  created_at  timestamptz not null default now(),
  primary key (user_id, date)
);

-- ------------------------------------------------------ push subscriptions
create table if not exists public.push_subscriptions (
  endpoint    text primary key check (char_length(endpoint) <= 2048),
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  p256dh      text not null,
  auth        text not null,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------- build requests
-- 'push_test' is open to everyone; 'build' (ad-hoc rebuild) is admin-only for now.
create table if not exists public.build_requests (
  id           bigint generated always as identity primary key,
  user_id      uuid not null default auth.uid() references auth.users (id) on delete cascade,
  kind         text not null default 'build' check (kind in ('build', 'push_test')),
  status       text not null default 'queued' check (status in ('queued', 'running', 'done', 'error')),
  message      text,
  created_at   timestamptz not null default now(),
  finished_at  timestamptz
);

-- -------------------------------------------------------------- app status
-- One shared row the worker keeps up to date: schedule, last run, voices, push key.
create table if not exists public.app_status (
  id          integer primary key default 1 check (id = 1),
  data        jsonb not null default '{}'::jsonb,
  updated_at  timestamptz not null default now()
);

-- ------------------------------------------------------ row-level security
alter table public.profiles           enable row level security;
alter table public.sources            enable row level security;
alter table public.briefings          enable row level security;
alter table public.push_subscriptions enable row level security;
alter table public.build_requests     enable row level security;
alter table public.app_status         enable row level security;

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((select is_admin from public.profiles where id = auth.uid()), false)
$$;

drop policy if exists "own profile" on public.profiles;
create policy "own profile" on public.profiles for select to authenticated using (id = auth.uid());
drop policy if exists "edit own profile" on public.profiles;
create policy "edit own profile" on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists "read built-in and own sources" on public.sources;
create policy "read built-in and own sources" on public.sources for select to authenticated
  using (user_id is null or user_id = auth.uid());
drop policy if exists "add own sources" on public.sources;
create policy "add own sources" on public.sources for insert to authenticated
  with check (user_id = auth.uid() and (select count(*) from public.sources where user_id = auth.uid()) < 25);
drop policy if exists "edit own sources" on public.sources;
create policy "edit own sources" on public.sources for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists "remove own sources" on public.sources;
create policy "remove own sources" on public.sources for delete to authenticated using (user_id = auth.uid());

drop policy if exists "read own briefings" on public.briefings;
create policy "read own briefings" on public.briefings for select to authenticated using (user_id = auth.uid());

drop policy if exists "own push subscriptions" on public.push_subscriptions;
create policy "own push subscriptions" on public.push_subscriptions for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "read own requests" on public.build_requests;
create policy "read own requests" on public.build_requests for select to authenticated using (user_id = auth.uid());
drop policy if exists "create requests" on public.build_requests;
create policy "create requests" on public.build_requests for insert to authenticated
  with check (user_id = auth.uid() and status = 'queued' and (kind = 'push_test' or public.is_admin()));

drop policy if exists "read app status" on public.app_status;
create policy "read app status" on public.app_status for select to authenticated using (true);

-- Column-level limits: users may only touch the columns the app needs.
-- (is_admin, feed_token, status and the worker's source bookkeeping stay worker-only.)
revoke all on public.profiles, public.sources, public.briefings, public.push_subscriptions,
              public.build_requests, public.app_status from anon, authenticated;
grant select on public.profiles, public.sources, public.briefings, public.push_subscriptions,
                public.build_requests, public.app_status to authenticated;
grant update (settings) on public.profiles to authenticated;
grant insert (user_id, name, url, section, enabled) on public.sources to authenticated;
grant update (name, section, enabled) on public.sources to authenticated;
grant delete on public.sources to authenticated;
grant insert (endpoint, user_id, p256dh, auth) on public.push_subscriptions to authenticated;
grant delete on public.push_subscriptions to authenticated;
grant insert (user_id, kind) on public.build_requests to authenticated;

-- ---------------------------------------------------------------- storage
-- Public bucket: MP3s live under /<feed_token>/<date>.mp3 and voice samples under /previews/.
-- Only the worker (secret key) can write; anyone with the exact link can stream.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('briefings', 'briefings', true, 26214400, array['audio/mpeg'])
on conflict (id) do update set public = true, file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;
