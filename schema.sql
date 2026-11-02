-- Varuna ASV monitoring: jalankan di Supabase SQL Editor

create table if not exists public.mission_logs (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  sog         numeric,          -- speed over ground (knot)
  cog         numeric,          -- course over ground (derajat, 0-360)
  position    text,             -- label posisi, mis. "A3" atau "-7.9521, 112.6145"
  geotag      text,             -- teks geotag terakhir
  score       integer not null default 0,
  x           numeric,          -- koordinat lintasan (0-25)
  y           numeric,          -- koordinat lintasan (0-25)
  lat         double precision,
  lon         double precision
);

create index if not exists mission_logs_created_at_idx
  on public.mission_logs (created_at desc);

-- Row Level Security:
--  * website (anon key)  -> hanya boleh MEMBACA
--  * kapal (service key) -> menulis, melewati RLS
alter table public.mission_logs enable row level security;

drop policy if exists "anon can read mission_logs" on public.mission_logs;
create policy "anon can read mission_logs"
  on public.mission_logs for select
  to anon
  using (true);

-- Aktifkan realtime untuk event INSERT
alter publication supabase_realtime add table public.mission_logs;

-- Bucket gambar (publik untuk dibaca, upload hanya lewat service key)
insert into storage.buckets (id, name, public)
values ('mission_images', 'mission_images', true)
on conflict (id) do nothing;

drop policy if exists "anon can list mission_images" on storage.objects;
create policy "anon can list mission_images"
  on storage.objects for select
  to anon
  using (bucket_id = 'mission_images');
