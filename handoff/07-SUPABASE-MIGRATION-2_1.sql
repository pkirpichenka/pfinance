-- ============================================================
-- PFinance · Миграция Supabase для Фазы 2.1
-- Атомарная защита от затирания при одновременной записи с двух устройств.
--
-- КАК ПРИМЕНИТЬ:
--   Supabase → ваш проект → SQL Editor → New query → вставить весь файл → Run.
--   Выполняется один раз. Повторный запуск безопасен (idempotent).
--
-- ЧТО ДЕЛАЕТ:
--   1. Добавляет столбец app_state.rev (ревизия строки).
--   2. Создаёт функцию pf_save_state(p_data, p_base_rev), которая атомарно
--      (в одном UPDATE) записывает данные, только если ревизия в БД совпадает
--      с той, на которой основан клиент. Иначе возвращает {ok:false, rev:<текущая>}.
--
-- ДО применения миграции приложение продолжает работать в режиме Фазы 2
-- (проверка «прочитать-сравнить-записать»); после — переключается на атомарный
-- путь автоматически, без изменений в коде.
--
-- Таблица предполагается: public.app_state (user_id uuid PK/unique, data jsonb).
-- RLS и политики на app_state остаются вашими существующими; функция работает
-- от имени вызывающего пользователя (security invoker) и пишет только свою строку.
-- ============================================================

-- 1) Столбец ревизии
alter table public.app_state
  add column if not exists rev bigint not null default 0;

-- 2) Атомарное сохранение с оптимистичной блокировкой по ревизии
create or replace function public.pf_save_state(p_data jsonb, p_base_rev bigint)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_uid uuid := auth.uid();
  v_new bigint;
  v_current bigint;
begin
  if v_uid is null then
    raise exception 'not authenticated';
  end if;

  -- Условный UPDATE: пишем только если ревизия не изменилась с момента загрузки.
  update public.app_state
     set data = p_data,
         rev  = rev + 1
   where user_id = v_uid
     and rev = p_base_rev
  returning rev into v_new;

  if found then
    return jsonb_build_object('ok', true, 'rev', v_new);
  end if;

  -- Совпадения нет: либо строки ещё нет, либо ревизия ушла вперёд.
  select rev into v_current from public.app_state where user_id = v_uid;

  if not found then
    -- Первая запись пользователя.
    begin
      insert into public.app_state(user_id, data, rev) values (v_uid, p_data, 1);
      return jsonb_build_object('ok', true, 'rev', 1);
    exception when unique_violation then
      -- Гонка первой записи с другого устройства — сообщаем о конфликте.
      select rev into v_current from public.app_state where user_id = v_uid;
      return jsonb_build_object('ok', false, 'rev', coalesce(v_current, 0));
    end;
  end if;

  -- Ревизия в БД впереди клиентской — конфликт, ничего не затираем.
  return jsonb_build_object('ok', false, 'rev', v_current);
end;
$$;

-- 3) Доступ на выполнение функции авторизованным пользователям
grant execute on function public.pf_save_state(jsonb, bigint) to authenticated;
