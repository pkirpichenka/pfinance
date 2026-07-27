# ТЗ (модуль 2): развёртывание и интеграция с Supabase

Это **дополнение** к основному документу `Техническое-задание.md` и эталону `finance-dashboard.html`.
Задача модуля: сделать приложение реально работающим в обычном браузере на личном субдомене —
с сохранением данных в облаке и входом по email, **не меняя логику расчётов, формулы и интерфейс**.

> Истина по поведению приложения — эталонный файл `finance-dashboard.html`.
> Этот документ описывает **только** то, что добавляется: облачное хранилище, авторизацию и деплой.

---

## 0. Что и зачем

Сейчас приложение хранит состояние `S` через `window.storage` — этого API нет в обычном браузере.
Нужно заменить хранилище на **Supabase** (Postgres + Auth + RLS), добавить экран входа и развернуть
статический файл на **GitHub Pages** с личным субдоменом. Регион Supabase — **EU (Frankfurt)**.

Данные финансовые и лежат на публичном адресе, поэтому **вход обязателен**, а доступ к строкам
ограничивается политиками RLS (каждый видит только свои данные).

---

## 1. ЖЁСТКИЕ ПРАВИЛА (без фантазий)

1. **Не менять** модель данных `S`, формулы, типы операций, экраны, тексты, дизайн, мобильную версию — всё из основного ТЗ остаётся как есть.
2. **Хранилище — единый JSON-объект.** В базе состояние `S` хранится целиком как одна JSONB-строка на пользователя. **Не нормализовать** данные в отдельные таблицы (это сломало бы расчёты). Схема — строго как в разделе 3.
3. **Единственная новая внешняя зависимость** — официальный клиент `@supabase/supabase-js`, подключаемый по ESM с CDN. Больше никаких библиотек и фреймворков. Приложение остаётся **одним файлом** `finance-dashboard.html`.
4. **Не трогать** делегирование событий, имена функций, разметку экранов. Изменения строго в трёх местах: обёртка `Store`, функция `init()`, добавление экрана входа и кнопки «Выйти».
5. **Секретов в коде нет.** В файл кладётся только `SUPABASE_URL` и публичный `anon`-ключ (он для клиента и защищён RLS — это нормально и безопасно). Никаких `service_role`-ключей в клиенте.
6. **Никакого `localStorage`/`sessionStorage`.** Резервная копия — существующие кнопки экспорт/импорт JSON.
7. Язык интерфейса — русский. Если чего-то не хватает для точной реализации — **спросить**, не выдумывать.

---

## 2. Настройка Supabase (сделать в панели Supabase)

1. Создать проект, регион **Central EU (Frankfurt)**.
2. В **Authentication → Providers** включить **Email** (вход по ссылке/коду — magic link / OTP). Отключить обязательное подтверждение, если нужен вход по одноразовому коду (на усмотрение — по умолчанию magic link).
3. В **Authentication → URL Configuration** добавить в *Site URL* и *Redirect URLs* адрес вашего субдомена (например, `https://finance.example.com`) и `http://localhost` для локальной отладки.
4. В **SQL Editor** выполнить SQL из раздела 4.
5. В **Project Settings → API** скопировать `Project URL` и `anon public key` — они пойдут в конфиг (раздел 5).

---

## 3. Схема данных в базе

Одна таблица, одна строка на пользователя, всё состояние в JSONB:

```
Таблица: app_state
  user_id     uuid        PRIMARY KEY, ссылается на auth.users(id)
  data        jsonb       NOT NULL DEFAULT '{}'::jsonb   -- сюда сериализуется весь объект S
  updated_at  timestamptz NOT NULL DEFAULT now()
```

Правило записи — **last-write-wins** (полностью перезаписываем `data` объектом `S`), как и в текущей модели.

---

## 4. SQL для Supabase (выполнить целиком)

```sql
-- Таблица состояния
create table if not exists public.app_state (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  data       jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

-- Включаем защиту на уровне строк
alter table public.app_state enable row level security;

-- Пользователь читает только свою строку
create policy "read own state"
  on public.app_state for select
  using (auth.uid() = user_id);

-- Пользователь создаёт только свою строку
create policy "insert own state"
  on public.app_state for insert
  with check (auth.uid() = user_id);

-- Пользователь обновляет только свою строку
create policy "update own state"
  on public.app_state for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- Авто-обновление updated_at
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

drop trigger if exists trg_touch_app_state on public.app_state;
create trigger trg_touch_app_state
  before update on public.app_state
  for each row execute function public.touch_updated_at();
```

---

## 5. Изменения в коде (точечно)

### 5.1. Подключение клиента и конфиг
В `<head>` (или перед основным скриптом) добавить модуль, создающий клиент и «мост» на `window`.
Основной скрипт приложения остаётся обычным `<script>` — он общается с бэкендом через `window.PFBackend`.

```html
<script type="module">
  import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

  const SUPABASE_URL = 'https://ВАШ-ПРОЕКТ.supabase.co';
  const SUPABASE_ANON_KEY = 'ВАШ-ПУБЛИЧНЫЙ-ANON-KEY';   // публичный ключ, класть в код можно
  const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

  // Контракт, который использует основной скрипт приложения:
  window.PFBackend = {
    user: null,
    _cbs: [],
    onChange(cb){ this._cbs.push(cb); },
    async signInWithEmail(email){
      const { error } = await sb.auth.signInWithOtp({
        email, options:{ emailRedirectTo: window.location.origin + window.location.pathname }
      });
      return { error };
    },
    async signOut(){ await sb.auth.signOut(); },
    async load(){
      const { data:{ user } } = await sb.auth.getUser();
      if(!user) return null;
      const { data, error } = await sb.from('app_state').select('data').eq('user_id', user.id).maybeSingle();
      if(error) throw error;
      return data ? data.data : null;
    },
    async save(state){
      const { data:{ user } } = await sb.auth.getUser();
      if(!user) throw new Error('not authenticated');
      const { error } = await sb.from('app_state')
        .upsert({ user_id:user.id, data:state }, { onConflict:'user_id' });
      if(error) throw error;
    }
  };

  // Следим за сессией и уведомляем приложение
  sb.auth.onAuthStateChange(async (_e, session)=>{
    window.PFBackend.user = session?.user || null;
    window.PFBackend._cbs.forEach(cb=>{ try{ cb(window.PFBackend.user); }catch(_){} });
  });
  // начальное состояние сессии
  (async ()=>{ const { data:{ user } } = await sb.auth.getUser();
    window.PFBackend.user = user || null;
    window.PFBackend._cbs.forEach(cb=>{ try{ cb(user||null); }catch(_){} });
  })();
</script>
```

### 5.2. Обёртка `Store` — перенаправить на Supabase
Заменить **только тело** методов `Store.load`/`Store.save`, сохранив прежний интерфейс.
Оставить деградацию в память (`window.__mem`) на случай оффлайна/паузы проекта.

```js
const Store={
  async load(){
    try{ if(window.PFBackend){ const r=await window.PFBackend.load(); if(r) return r; } }
    catch(e){ /* оффлайн/пауза — уходим в память */ }
    try{ if(window.__mem) return JSON.parse(window.__mem); }catch(e){}
    return null;
  },
  async save(state){
    const s=JSON.stringify(state);
    window.__mem=s;                                  // локальная страховка
    try{ if(window.PFBackend) await window.PFBackend.save(state); }
    catch(e){ toast('Нет связи с облаком — изменения сохранены локально'); }
  }
};
```

### 5.3. Экран входа и запуск
Изменить `init()`: сначала дождаться сессии, показать экран входа, если пользователь не авторизован; при входе — загрузить состояние и запустить приложение как обычно.

Логика:
- Если `window.PFBackend` **нет** (открыли файл локально без модуля) — работать по-старому в памяти (текущее поведение), чтобы файл оставался запускаемым.
- Если пользователь **не авторизован** — отрисовать простой экран входа: поле email + кнопка «Получить ссылку для входа», вызывающая `PFBackend.signInWithEmail`. После отправки — сообщение «Проверьте почту».
- Если пользователь **авторизован** — `S = await Store.load() || seed()`, выполнить существующие миграции, `render()`.
- Подписаться на `PFBackend.onChange`: при входе — перезапустить `init()`; при выходе — показать экран входа.

Экран входа выдержать в стиле приложения (те же CSS-переменные/шрифты). Никакой новой навигации. Добавить кнопку **«Выйти»** в «Настройки» (вызывает `PFBackend.signOut()`), рядом с блоком «Данные».

### 5.4. Что НЕ меняется
Все `view*`-функции, формулы (`personalBalance`, `bizBalance`, `sumTx`, прогноз и т.д.), типы операций, категории, миграции, мобильная навигация, экспорт/импорт JSON, ключ дебаунса сохранения — **без изменений**.

---

## 6. Деплой на GitHub Pages + личный субдомен

1. Создать репозиторий, положить в него `finance-dashboard.html` (при желании переименовать в `index.html`, чтобы открывался по корню домена).
2. В репозитории добавить файл `CNAME` с одной строкой — вашим субдоменом, например: `finance.example.com`.
3. В **Settings → Pages** выбрать ветку (`main`) и корень (`/`), включить сборку. Включить **Enforce HTTPS**.
4. В DNS вашего домена добавить запись:
   - `CNAME` `finance` → `ВАШ-ЛОГИН.github.io.`
   - (для доменов на Cloudflare — режим прокси можно оставить, HTTPS выдаст либо GitHub, либо Cloudflare).
5. Дождаться выпуска сертификата (обычно минуты, иногда до часа).
6. В Supabase (раздел 2, п.3) убедиться, что этот субдомен указан в Site URL и Redirect URLs — иначе ссылка входа не сработает.

Альтернатива хостингу (по желанию, не обязательно): Cloudflare Pages или Netlify — тоже бесплатно, свой домен, HTTPS и больший лимит трафика. Бэкенд при этом тот же — Supabase.

---

## 7. Пауза проекта при простое (необязательный «keep-alive»)

Бесплатный проект Supabase ставится на паузу после 7 дней без запросов к базе (данные сохраняются, «будится» кнопкой ~30 сек). При ежедневном заполнении это не наступит. Как страховка на время отпуска — любой из вариантов:
- бесплатный внешний пинг раз в сутки (например, UptimeRobot) на публичный endpoint, делающий лёгкий запрос к базе;
- или запланированное простое обращение к таблице раз в день.
Внедрять только если попросят отдельно; в код приложения это не входит.

---

## 8. Приёмка (чек-лист)

- [ ] Приложение открывается на субдомене по HTTPS.
- [ ] Без входа виден экран авторизации; после входа по email грузятся данные пользователя.
- [ ] Операции/долги/цели/счета сохраняются в Supabase и подтягиваются на другом устройстве после входа тем же email.
- [ ] Другой пользователь (другой email) своих данных не видит у первого — RLS работает.
- [ ] Оффлайн/пауза: приложение не падает, показывает тост и продолжает работать в памяти; экспорт/импорт JSON доступны.
- [ ] Логика, формулы, экраны, дизайн и мобильная версия — идентичны эталону; изменения только в `Store`, `init()`, экране входа и кнопке «Выйти».
- [ ] В коде нет `service_role`-ключа и других секретов; только `URL` + публичный `anon`-ключ.
- [ ] Один файл `finance-dashboard.html`; единственная внешняя JS-зависимость — `@supabase/supabase-js` по ESM.

---

## 9. Промпт для GPT (вставить вместе с этим файлом, эталоном и основным ТЗ)

> Ты — старший фронтенд-разработчик. Тебе передают готовый эталон `finance-dashboard.html`, основное
> `Техническое-задание.md` и этот модуль про Supabase и деплой. Реализуй **только** то, что описано в этом
> модуле: замени хранилище `window.storage` на Supabase, добавь вход по email и кнопку «Выйти», подготовь
> файл к деплою на GitHub Pages с субдоменом. **Не меняй** логику расчётов, формулы, типы операций, экраны,
> тексты, дизайн и мобильную версию — всё это остаётся строго как в эталоне. Соблюдай «жёсткие правила» из
> раздела 1: один HTML-файл, единственная новая зависимость — `@supabase/supabase-js` по ESM, никаких других
> библиотек, никаких секретов в коде кроме публичного anon-ключа, никакого localStorage. Изменения вноси
> только в обёртку `Store`, функцию `init()`, экран входа и кнопку «Выйти», как показано в разделе 5.
> Верни: (1) полный файл `finance-dashboard.html`, (2) SQL из раздела 4 отдельным блоком, (3) короткий список
> шагов деплоя. Если чего-то не хватает для точной реализации — спроси, ничего не выдумывай.
