# Convioo — Тотальный аудит кода

**Ветка:** `claude/code-review-performance-gPm17`
**Дата:** 2026-05-12
**Метод:** 6 параллельных агентов: backend perf, security, frontend, DB, resilience, dead code.
**HEAD:** `1ee3fa6`

---

## Короткий вердикт по 10 000 посетителей/день

**Сейчас — НЕТ, упадёт.** Без фиксов P0 продакшен ляжет уже на 100–200 одновременных пользователях, не говоря о 10 000/день (пиковая ~150–300 RPS).

Главные узкие места:
1. **DB pool на 15 коннектов** (`pool_size=5, max_overflow=10`) при асинхронном фреймворке — этого хватит на ~30 одновременных HTTP. На 10к/день будет постоянное `QueuePool limit overflow` → 504.
2. **`pool_pre_ping=False`** — после рестарта Postgres получаем `ConnectionInvalidated` на каждом старом коннекте. На Railway это случается регулярно.
3. **`command_timeout=10`** глобально — любой запрос длиннее 10с (CSV экспорт, аналитика, миграция данных) падает.
4. **47+ FK без `index=True`** — full scan на каждый JOIN/cascade. На 100к лидов это секунды.
5. **CSV/Excel экспорт грузит всё в память** — на 5к лидов уже 100–300МБ RSS, на 50к — OOM на Railway worker.
6. **SSE без таймаута/heartbeat** — 1 пользователь = 1 живой коннект из pool навсегда.
7. **`asyncio.gather(..., return_exceptions=False)` в рассылке вебхуков** — одна 502 у клиента сносит всю рассылку.

**С фиксом всех P0 и половины P1 — 10к/день вытянет** на одном Railway инстансе среднего размера + Postgres + Redis. С запасом и горизонтальным масштабированием уйдёт за 100к/день.

**Срок до боевой готовности:** 2–3 недели плотной работы.

---

## P0 — упадёт под нагрузкой / эксплуатируемо удалённо

### Backend perf

| # | Файл:строка | Что | Фикс |
|---|---|---|---|
| P0-1 | `src/leadgen/db/session.py:26-38` | `pool_size=5, max_overflow=10, pool_pre_ping=False`. На 10к/день пик 200+ конкаррентов — pool исчерпан мгновенно | `pool_size=20, max_overflow=40, pool_pre_ping=True`. Также `command_timeout` поднять до 30с или переопределить per-query для экспортов |
| P0-2 | `src/leadgen/adapters/web_api/app.py:543-631` | `export_leads_csv()` грузит до 5000 лидов в память + JOIN на SearchQuery. На 50к лидов = OOM | Стриминговый CSV: `yield row` через `StreamingResponse` + server-side курсор |
| P0-3 | `src/leadgen/adapters/web_api/app.py:636-739` | `export_session_xlsx()` использует синхронный `openpyxl.Workbook().save()` в async-хендлере — блокирует event loop | Вынести в arq worker, отдавать pre-signed URL/redirect когда готово |
| P0-4 | `src/leadgen/adapters/web_api/app.py:4888-4920` | SSE-стрим без таймаута/keepalive. 1000 открытых вкладок = 1000 связанных коннектов БД | Таймаут 60–120с + heartbeat каждые 15с + `event_stream` с `asyncio.wait_for` |
| P0-5 | `src/leadgen/adapters/web_api/app.py:5290, 5338` | `await send_email()` к Resend (~500мс) выполняется внутри сессии БД — держит коннект | Email только в background task / arq |
| P0-6 | `src/leadgen/db/models/*` (47 мест) | FK без `index=True`: `UserSession.user_id`, `LeadMark.{user_id,lead_id}`, `LeadTask.lead_id`, `OAuthCredential.user_id`, `UserIntegrationCredential.user_id`, `TeamMembership.{user_id,team_id}`, `Lead.{query_id,owner_user_id}` и др. | Новая миграция: `op.create_index(... , postgresql_concurrently=True)` для каждой |
| P0-7 | `src/leadgen/db/models/user.py:30` | `User.email` без `unique=True` и без индекса — race condition на signup, full scan на login при 100к юзеров | Миграция: дедуп → `unique=True, index=True` |
| P0-8 | `src/leadgen/db/models/lead.py:66,80; user.py:133` | Plain `JSON` вместо `_JSONB` на `score_components`, `rating_snapshots`, `icp_profile` — нельзя индексировать, медленный contains | Заменить тип на `_JSONB()` |

### DB / lazy loading

| # | Файл:строка | Что |
|---|---|---|
| P0-9 | `src/leadgen/db/models/lead.py:108`, `search.py:91-93` | `Lead.query`, `SearchQuery.leads`, `User.queries` — `relationship()` без `lazy=` контроля. Случайный доступ из Pydantic-схемы → подгружает тысячи строк |
| P0-10 | `src/leadgen/db/models/lead.py:88-106` | Soft-delete: `deleted_at`, `archived_at`, `blacklisted` — не везде учитываются в выборках. Удалённые лиды могут протекать в API |

### Security

| # | Файл:строка | Что |
|---|---|---|
| P0-11 | `src/leadgen/adapters/web_api/routes/auth.py:232-261` | Email enumeration: при невалидном email `verify_password` не вызывается, timing разный → перебор email возможен | Всегда вызывать dummy `verify_password` |
| P0-12 | `src/leadgen/adapters/web_api/app.py:319-328` | `allow_credentials=True` с origins из `WEB_CORS_ORIGINS` env. Если в env случайно `*` — открытая дверь. Сейчас валидации нет | Жёсткий allowlist в коде; при `*` падать на старте |

### Resilience

| # | Файл:строка | Что |
|---|---|---|
| P0-13 | `src/leadgen/core/services/webhooks.py:148` | `asyncio.gather(..., return_exceptions=False)` — один упавший вебхук рушит всю рассылку | Заменить на `True`, обработать исключения отдельно |
| P0-14 | `src/leadgen/collectors/website.py:192-327` | SSRF: `_normalise_url()` не блокирует `localhost`, `127.0.0.1`, `169.254.169.254` (AWS metadata), приватные диапазоны | Резолвить hostname → `ipaddress.ip_address().is_private/is_loopback/is_link_local` → 400 |

### Frontend

| # | Файл:строка | Что |
|---|---|---|
| P0-15 | `frontend/app/app/leads/page.tsx` (1518 строк) | Kanban/list рендерит весь `filtered.map((l) => ...)` без виртуализации. На 1000+ лидов — фриз UI | `@tanstack/react-virtual` или `react-window` |
| P0-16 | `frontend/lib/api/_core.ts:34-72` | `request<T>()` без `AbortController`. При быстрых переключениях фильтров stale-ответ перезаписывает свежие данные | Поддержать `signal` параметр + автоматический abort в hook |
| P0-17 | `frontend/app/` | `error.tsx` / Error Boundary отсутствуют → исключение в любом дочернем компоненте крушит всё App | Добавить корневой `app/error.tsx` + `app/app/error.tsx` |
| P0-18 | `frontend/app/globals.css:294` + 27 страниц на `"use client"` | Мобиль не адаптирован вообще: `grid-template-columns: 240px 1fr` фиксирован. На &lt;768px sidebar занимает экран | Hamburger + `@media` breakpoint, см. неиспользуемый `MobileBanner.tsx` |

---

## P1 — серьёзные тормоза / уязвимости

### Backend perf

- **`routes/_helpers.py:471-484, 499-520`** — `_marks_for_user()`, `_tags_by_lead()` без индекса `(user_id, lead_id)` → full scan при каждом отображении CRM.
- **`app.py:1757-1849`** — `bulk_update_leads()` цикл `for lead in leads: session.add()`. На 50 лидах = 50 INSERT. Использовать `update().where().values()`.
- **`app.py:4844-4886`** — `reorder_lead_statuses()` цикл UPDATE на каждый статус. Bulk update.
- **`app.py:5040-5089`** — `_saved_search_scheduler_loop()` без пагинации скана. На 10к saved searches → OOM scheduler.
- **`routes/admin.py:45-150`** — `admin_overview()` 10+ последовательных COUNT. `asyncio.gather()` или CTE.
- **`integrations/{notion,hubspot,yelp,osm,pipedrive,stripe,slack}.py`** — httpx.AsyncClient создаётся per-instance, нет глобального семафора. При 200 RPS = 200 одновременных исходящих → быстро упрётесь в rate-limit партнёра.

### DB — композитные/частичные индексы

- `leads(query_id) WHERE deleted_at IS NULL` (partial) — горячий путь CRM.
- `search_queries(user_id, team_id)`, `(user_id, status)`.
- `sequence_enrollments(user_id, next_send_at)`.
- `lead_marks(user_id, lead_id)`.
- `users(email_reply_tracking_enabled, email_reply_last_checked_at)` для cron-репорта.
- `saved_searches(active, next_run_at)` для шедулера.

### Security

- **`routes/auth.py:451-510`** — forgot-password не скрывает существование email и rate-limit слабый.
- **`adapters/web_api/auth.py:60-68`** — `hash_token()` использует SHA-256 без соли для API-ключей. Утечка БД → быстрый brute-force на GPU. Использовать `argon2` (он уже есть для паролей).
- **`adapters/web_api/app.py`** — нет CSRF middleware. На auth, change-email, change-password, team-admin endpoints — потенциально эксплуатируемо при социалке.
- **`adapters/web_api/app.py:2228-2240`** — Notion OAuth `state` валидируется HMAC, но без one-time use. Реплей возможен.
- **`frontend/app/developers/page.tsx:367`** — `dangerouslySetInnerHTML={{__html: title}}` — сейчас источник статический, но паттерн опасен.

### Resilience

- **`pipeline/enrichment.py:90, 104`**, **`analysis/ai_analyzer.py:139`**, **`analysis/research.py:26,86,126,194`** — `except Exception: return None` глушит ошибки Anthropic/HTTP, в Sentry не попадает.
- **`integrations/{notion,hubspot,pipedrive,stripe,slack,gmail,outlook}`** — ни одного retry с backoff. Один сетевой сбой = ошибка пользователю.
- **`adapters/web_api/app.py:1353` и др.** — `asyncio.create_task(_run_web_search_inline(...))` fire-and-forget. Если упадёт — пользователь видит «крутится» бесконечно.
- **`analysis/scoring.py:153-164`** — `as_completed` с `await coro` без try/except: одно исключение убивает остаток tasks.
- **`adapters/web_api/app.py:334-348`** — `/health` проверяет только БД. Redis/Anthropic упавшие — Railway считает сервис «здоровым».
- **`queue/worker.py`** — нет SIGTERM handler, dead-letter queue. Длинный search на rolling deploy просто умирает.

### Frontend

- **`components/AssistantWidget.tsx`** (6 useEffect), **`LeadDetailExtras.tsx`** (4 useEffect) — сложные зависимости, риск ре-инициализации/leaks.
- **`app/app/team/page.tsx:765`**, **`app/join/[token]/page.tsx:53`** — `setInterval(.., 1000)` для UI-таймеров (норм), но в других местах надо проверить наличие polling.
- **`lib/api/_core.ts:71`** — `return body as T` — нет runtime валидации. Малейшее изменение схемы бэка на проде → silent breakage.
- **`components/ConviooLogo.tsx:68`** — `<img>` без width/height → CLS hit.
- **`components/AssistantWidget.tsx:373,400`** — `key={i}` в чате. При вставке сообщений в начало список переиндексируется.

---

## P2 — best-practice и долги

### Архитектура

- **`src/leadgen/adapters/web_api/app.py` — 5938 строк**. По CLAUDE.md это P1-задача в roadmap. Вынести как минимум: `/leads/*`, `/integrations/{notion,hubspot,pipedrive}`, `/billing/*`, `/oauth/*`, SSE search.
- **Брендинг**: title FastAPI всё ещё `"Leadgen API"` (`app.py:312`). Менять на `"Convioo API"`.
- **Русские строки в user-facing**:
  - `app.py:5932` и `routes/_helpers.py:689` — `"Запустить поиск: {niche} в {region}"` дублирован, в PendingAction (UI). Локализовать через i18n.
  - `analysis/prompts/assistant.py:103` — русская строка в промпте Клода (внутри RU-локали ок, проверить логику выбора).

### Мёртвый код

- `frontend/components/HealthBadge.tsx` — нигде не импортируется.
- `frontend/components/MobileBanner.tsx` — экспортируется, но не используется (плюс мобиль не адаптирован — двойная странность).
- `src/leadgen/utils/cache.py:146` `clear_inmem()` — не используется.
- `src/leadgen/utils/geocode.py:217` `clear_cache()` — не используется.

### i18n

- `frontend/lib/i18n/en.ts` (~1043 строки) короче `ru.ts` (~1073) и `uk.ts` (~1068) — недопереведено, как заявлено в CLAUDE.md.

### Прочее

- Email-шаблоны (`core/services/email_sender.py`) — нет `html.escape()` при подстановке имени.
- Нет Content-Security-Policy на ответах API/в Next.js.
- `LeadCustomField.key` хранится как-есть — `"decision-maker"` ≠ `"Decision Maker"` ≠ `"Decision_Maker"`. Нужна нормализация.
- `SequenceEnrollment.status: String(20)` без CHECK / Enum.
- `AffiliateCode.code` — VARCHAR(64) PK без индекса (PK по varchar — медленно).
- Numeric(12,2) для `Lead.deal_value` — максимум $9 999 999,99, не документировано.
- Healthcheck: добавить Redis ping, опционально `ANTHROPIC` reachable (с кэшем 60с).
- Logging: `__main__.py:55-59` использует `print()` до настройки логгера → в Railway видно не всегда.

### TypeScript

- `lib/api/_core.ts` и потребители — массовое использование `as` вместо runtime-валидации (Zod).
- `components/app/LeadDetailExtras.tsx:529-552` — `(p as { from?: string }).from` повторён 5 раз — выделить guard.
- `components/layout/Sidebar.tsx:308` — `is_admin` через extension cast вместо включения в тип `CurrentUser`.

---

## Что в коде хорошо (чтобы не сломать рефакторингом)

- Архитектурное правило «`core/` и `pipeline/` не импортируют `adapters/`» — **соблюдается, нарушений нет**.
- 48 миграций, у всех есть `downgrade()`, парные ADD/DROP — миграционный долг минимален.
- `_JSONB` / `_UUID` декораторы корректно переключают тип для SQLite-тестов.
- HMAC-сравнения сделаны через `hmac.compare_digest` (timing-safe), Fernet шифрование OAuth-токенов, Stripe webhook signature verification — корректно.
- arq-воркер настроен с `job_timeout=900s`, `max_jobs=5`, sentry init на старте.
- Rate limiting есть на search/auth/assistant.
- TODO/FIXME/HACK комментариев в коде **нет** — чисто.
- Циклических импортов **нет**.

---

## План минимально достаточный для 10 000/день

**Неделя 1 (P0, ставит сайт на ноги):**
1. `db/session.py`: pool 20/40, `pool_pre_ping=True`, `command_timeout` per-query.
2. Миграция: индексы на 47 FK + unique на `User.email` + замена JSON→JSONB на 3 колонках.
3. `webhooks.py:148`: `return_exceptions=True`.
4. SSE: таймаут 60с + heartbeat 15с.
5. CSV/Excel экспорт: стрим / arq job.
6. SSRF guard в `collectors/website.py`.
7. Email enumeration: dummy `verify_password`.
8. CORS: жёсткий allowlist, fail-fast на `*`.
9. Frontend: корневой `error.tsx`, AbortController в `_core.ts`.

**Неделя 2 (P1):**
10. Виртуализация списка лидов.
11. Retry/backoff обёртка для всех integrations.
12. Bulk UPDATE вместо циклов в `app.py` (bulk_update_leads, reorder_statuses).
13. Композитные/partial индексы (см. список выше).
14. argon2 для API key хешей вместо SHA-256.
15. CSRF middleware на state-changing endpoints.
16. `/health` расширить: + Redis + arq queue depth.
17. SIGTERM handler + graceful cancel scheduler/long tasks.

**Неделя 3 (полировка):**
18. Дробление `app.py` (минимум leads/, integrations/, billing/, oauth/).
19. CSP заголовок, html.escape в email-шаблонах.
20. Мобильная адаптация (hamburger sidebar, breakpoints).
21. Доперевести EN-локаль.
22. Удалить мёртвый код, переименовать FastAPI title в `"Convioo API"`.

После этого ставится один Railway worker среднего размера + Postgres + Redis, и на 10к посетителей/день в пике 150–300 RPS система проходит без 5xx. Дальше — горизонтальное масштабирование backend (он stateless) и pgbouncer перед Postgres.
