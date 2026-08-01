# 02. Актуальная архитектура

## Технологический стек

- Статическое приложение для GitHub Pages.
- Один production HTML-файл: HTML + CSS + чистый JavaScript.
- Внешняя JS-зависимость: `@supabase/supabase-js@2` через ESM.
- Google Fonts подключены как CSS-ресурс.
- Нет сборщика, npm-проекта или фреймворка.
- Базовая валюта — BYN; отображение денежных сумм использует `BYN`.

## Файлы

- `index.html` — источник истины и production entrypoint.
- `finance-dashboard.html` — идентичная копия.
- `database/supabase-app-state.sql` — таблица JSONB и RLS.
- `CNAME` — `pfinance.flexico.by`.
- `docs/` — исторические ТЗ и старые handoff-документы.
- `handoff/` — актуальный контекст для следующего разработчика.
- `tools/verify_bundle.py` — автоматическая проверка комплекта.

## Supabase

Клиент создаётся с:

```js
auth: {
  persistSession: true,
  autoRefreshToken: true,
  detectSessionInUrl: false
}
```

Пользователь входит по username/password. Username преобразуется в технический email:

```text
username@pfinance.flexico.by
```

Состояние хранится одной JSONB-записью в `public.app_state`, ключ — `user_id`.

Сохранение — last-write-wins через `upsert` всего объекта состояния `S`.

При сетевой ошибке используется только временный `window.__mem`; это не полноценное офлайн-хранилище.

Публичный anon-key допустим в клиентском HTML. `service_role`, пароли и приватные ключи запрещены.

## Состояние приложения

Главный объект `S` содержит:

```js
{
  settings,
  currencies,
  legalEntities,
  accounts,
  businesses,
  categories,
  tx,
  debts,
  goals,
  presets,
  meta,
  ui
}
```

Текущая `meta.modelVersion` — `6`.

Миграции выполняются в клиенте после загрузки через функции семейства `ensure*`, прежде всего `ensureBusinessModel()` и `ensureUxState()`.

## Карта основных функций

### Инициализация и хранилище

- `Store.load()` / `Store.save()`.
- `seed()`.
- `updateRatesFromNBRB()`.
- `ensureUxState()`.
- `ensureBusinessModel()`.

### Финансовые расчёты

- `accountBalance(id)`.
- `personalBalance()`.
- `businessBankBalance()`.
- `businessCashBalance()`.
- `bizChannelBalance(id, paymentMethod)`.
- `bizStats(id)`.
- `owedToMe()` / `iOwe()`.
- `netWorth()`.
- `reconcile()`.
- `periodAgg(period)`.

### Представления

- `viewOverview()`.
- `viewAccounts()`.
- `viewAdd()`.
- `viewTx()`.
- `viewDebts()`.
- `viewBusiness()`.
- `viewForecast()`.
- `viewGoals()`.
- `viewSettings()`.

### Ввод операций

- `refreshAddForm()`.
- `updateCompactAddChrome()`.
- `saveTx()`.
- `completeSavedTx()`.
- `showUndo()`.

### Сверка остатков

- `adjustmentForm()`.
- `saveAccountAdjustment()`.
- Типы `account_adjustment` и `biz_adjustment`.

## Текущий UX

- Светлая/тёмная/автоматическая тема.
- Сохраняемая сессия Supabase.
- Компактная форма внесения операции.
- Экранная цифровая клавиатура.
- Пресеты и последние использованные значения.
- Haptic feedback при поддержке устройства.
- Toast с отменой операции.
- Периоды обзора: месяц, квартал, год, всё.
- Drill-down из графика в операции; KPI «Мне должны / Я должен» ведут в раздел «Долги».
- Нижняя навигация: Обзор · Операции · Внести · Счета · Ещё (детали редизайна — в 06-DECISIONS-LOG).
- Синхронизация с защитой от затирания: ревизия `meta.rev` в блобе, проверка перед записью и сверка при возврате во вкладку, окно разрешения конфликта, живой статус (детали — в 06-DECISIONS-LOG). Полностью атомарный режим включается миграцией handoff/07-SUPABASE-MIGRATION-2_1.sql (столбец rev + функция pf_save_state); до неё работает совместимый режим.
- Адаптивный desktop/mobile интерфейс.
- Встроенный favicon и apple-touch-icon.

## Технический долг, который уже виден в коде

Это не обязательные задачи, а точки для анализа:

- `index.html` стал большим монолитом; полезна более ясная внутренняя секционизация.
- Last-write-wins может потерять изменения при параллельной работе на нескольких устройствах.
- Нет устойчивого офлайн-режима.
- Автоматические тесты ограничены статическими проверками.
- В коде встречаются исторические имена и комментарии, не всегда отражающие текущую версию.
- Следует проверить дублирующиеся объявления/мертвый код перед крупным рефакторингом.

Claude может предложить безопасный план устранения этих проблем, но не должен незаметно менять финансовое поведение.
