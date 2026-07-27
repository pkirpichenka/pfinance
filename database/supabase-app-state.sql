-- Идемпотентная настройка Supabase для личного финансового дашборда.
-- Скрипт можно запускать повторно: таблица и данные не удаляются.

create table if not exists public.app_state (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  data       jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.app_state enable row level security;

drop policy if exists "read own state" on public.app_state;
drop policy if exists "insert own state" on public.app_state;
drop policy if exists "update own state" on public.app_state;

create policy "read own state"
  on public.app_state for select
  using (auth.uid() = user_id);

create policy "insert own state"
  on public.app_state for insert
  with check (auth.uid() = user_id);

create policy "update own state"
  on public.app_state for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_touch_app_state on public.app_state;

create trigger trg_touch_app_state
  before update on public.app_state
  for each row
  execute function public.touch_updated_at();
