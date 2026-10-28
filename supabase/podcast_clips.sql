-- Podcast mode table. Safe to re-run. Paste into the Supabase SQL editor.
-- (Also part of schema.sql.)

-- ------------------------------------------------------------ podcast clips
-- Podcast mode: two hosts chat around the news. Each piece is a short two-voice exchange voiced
-- once a day and shared by everyone; the browser strings the right ones together for a listener's
-- lineup. Same rules as voice_notes: worker-written, world-readable.
--   pod_open_<n> | pod_tease_<section> | pod_bridge_<section> | pod_close_<n>
-- plus one marker row, clip_key 'podcast_ready', written when the day's set is published.
-- Object layout: /podcast/<date>/<clip_key>-<hosts>.mp3  (hosts = e.g. matthew_reference+kelly_reference)
create table if not exists public.podcast_clips (
  date       date not null,
  hosts      text not null,   -- the pair that voiced it, "voiceA+voiceB"
  clip_key   text not null,
  text       text not null,   -- the transcript, for captions and debugging
  duration   real not null default 0 check (duration >= 0),  -- seconds
  audio_path text not null,
  writer     text not null default 'built-in',  -- which AI (or the template) wrote the lines
  created_at timestamptz not null default now(),
  primary key (date, hosts, clip_key)
);
create index if not exists podcast_clips_date_idx on public.podcast_clips (date);

alter table public.podcast_clips enable row level security;
drop policy if exists "read podcast clips" on public.podcast_clips;
create policy "read podcast clips" on public.podcast_clips for select to anon, authenticated using (true);

revoke all on public.podcast_clips from anon, authenticated;
grant select on public.podcast_clips to anon, authenticated;

