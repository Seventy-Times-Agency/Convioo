# Карта проекта Convioo

Что где лежит и куда смотреть, когда что-то ломается. Два приложения:
бэкенд `src/leadgen/` (Python, FastAPI, Railway) и фронт `frontend/`
(Next.js, Vercel). Они говорят через `/api/v1/...`.

Деплой: push в `main` на GitHub `Seventy-Times-Agency/Convioo` → Railway
собирает бэкенд, Vercel — фронт. Проверить, что уехало:
`curl https://convioo.com/health` отдаёт `commit`.

---

## Семь доменов

Бэкенд (`routes/` и `core/services/`) и фронт (`components/`, `lib/api/`)
разложены по одним и тем же семи доменам. Если ломается «звонок из
карточки» — это `sales`, если «не приходит письмо» — `outreach`.

| Домен | Что внутри | Бэкенд routes | Бэкенд services |
|---|---|---|---|
| **account** | регистрация, вход, восстановление, профиль, команды, роли, уведомления | `account/auth.py` `users.py` `teams.py` `notifications.py` | `account/profile_service.py` `email_verification.py` `tokens.py` `team_permissions.py` `team_events.py` `team_journal.py` `notification_prefs.py` `squads.py` |
| **crm** | база лидов: карточка, теги, задачи, сегменты, шаблоны, отчёты, Henry | `crm/leads.py` `tags.py` `tasks.py` `segments.py` `templates.py` `base_distribute.py` `reports.py` `assistant.py` | `crm/lead_archive.py` `crm_snapshot.py` `report_builder.py` `icp_analyzer.py` `business_language.py` `decision_maker.py` `email_finder.py` `assistant_memory.py` `demo_data.py` |
| **sales** | отдел продаж: режим работы (очередь звонков), воронки, телефония, сквады, журнал, главная роли | `sales/work.py` `funnels.py` `telephony.py` `squads.py` `home.py` `journal.py` | `sales/funnel_engine.py` `telephony/` (`ringostat.py` — звонок на телефон, `telnyx.py` — звонок из браузера, `processing.py` — запись → расшифровка → разбор) `digest.py` |
| **search** | поиск и парсинг лидов, сохранённые поиски, лимиты и стоимость | `search/search.py` `saved_searches.py` | `search/search_cache.py` `search_channels.py` `saved_searches.py` `source_health.py` `sinks.py` `progress_broker.py` `cost_control.py` `usage_tracker.py` `tariff_limits.py` |
| **outreach** | почта: Gmail, входящие, последовательности, доставляемость, отписки | `outreach/gmail.py` `inbox.py` `sequences.py` `deliverability.py` `suppressions.py` `unsubscribe.py` | `outreach/email_sender.py` `email_reply_tracker.py` `inbox_sync.py` `reply_classifier.py` `spam_check.py` `dns_auth.py` `send_quota.py` `suppression.py` `unsubscribe.py` |
| **integrations** | Notion, HubSpot, Pipedrive, вебхуки, Telegram-бот, хранилище OAuth-токенов | `integrations/notion.py` `hubspot.py` `pipedrive.py` `webhooks.py` `telegram.py` | `integrations/oauth_state.py` `oauth_store.py` `secrets_vault.py` `webhooks.py` `tracking.py` |
| **platform** | админка, аудит, биллинг Stripe, партнёрка, логи, Sentry, health | `platform/admin.py` `audit.py` `billing.py` `affiliate.py` `misc.py` | `platform/billing_service.py` `log_setup.py` `sentry_setup.py` `health_probes.py` |

Общее для всех routes: `routes/_helpers.py` — `membership()` (проверка,
что пользователь в команде и с какой ролью), `resolve_team_view`,
`record_audit`, дефолтные статусы лидов.

---

## Бэкенд: `src/leadgen/`

```
src/leadgen/
  __main__.py            запуск: python -m leadgen
  config.py              все переменные окружения (Settings), одно место
  adapters/
    web_api/
      app.py             сборка FastAPI: CORS, CSRF, lifespan, include_router
      auth.py            кто сделал запрос (cookie-сессия → user)
      csrf.py                CSRF-защита; schemas/ — pydantic-схемы запросов/ответов
      sinks.py               прогресс поиска в SSE для браузера
      routes/<домен>/    HTTP-эндпоинты, см. таблицу выше
    telegram_v2/         Telegram-бот (bot.py команды, sinks.py доставка)
  core/services/<домен>/ бизнес-логика без FastAPI, см. таблицу выше
  pipeline/search.py     run_search_with_sinks — один вход для любого поиска
  pipeline/enrichment.py обогащение лида (сайт, email, ЛПР); recovery.py — добор упавших поисков
  collectors/            источники: google_places, osm, yelp, foursquare, website
  analysis/              Claude: скоринг, советы, Henry (henry_core, prompts/)
  integrations/          клиенты внешних API: stripe, gmail, notion, hubspot, pipedrive, slack, sheets
  db/models/             таблицы (SQLAlchemy); миграции — ../../alembic/versions
  db/session.py          подключение к Postgres
  queue/                 arq + Redis: worker.py — все кроны (дайджесты, касания воронки, ответы на письма)
  export/excel.py        выгрузка в Excel
  utils/                 http с ретраями, rate_limit, geocode, dedup, cache, metrics, secrets
```

Правило: `core/` и `pipeline/` не импортируют из `adapters/`.

---

## Фронт: `frontend/`

```
frontend/
  app/                    страницы (Next.js App Router)
    page.tsx              лендинг
    login/ register/ forgot-*/ reset-password/ verify-email/ join/   вход и приглашения
    app/                  всё за логином
      layout.tsx          оболочка: RequireAuth → Sidebar + main
      page.tsx            главная (личный режим — старый дашборд; команда — RoleHome)
      base/ leads/        База и CRM
      search/ sessions/   поиск и его результаты
      work/ funnels/      режим работы и воронки
      inbox/ sequences/ templates/   почта
      team/               команда: участники, роли, аналитика
      settings/           настройки (вкладки: компания, интеграции, телефония, почта, журнал, языки, биллинг)
      profile/ billing/ connectors/ import/ affiliate/ admin/ help/
    pricing/ privacy/ terms/ cookies/ changelog/ developers/ help/ vs/ r/   публичные страницы
  components/
    shell/        каркас: RequireAuth, AuthShell, баннеры, тема, тур, горячие клавиши, EmptyState
    brand/        логотип, иконки (Icon), аватар Henry
    layout/       Sidebar (навигация по роли), Topbar
    ui/           кнопки, поля, модалки, таблицы, чипы, MiniChart
    leads/        карточка лида и её модалка, теги, статусы писем, редактор воронки статусов, SessionRow
    crm/          доска (CrmBoard) и таблица (BaseTable)
    search/       форма поиска (FormColumn), комбобоксы ниши и региона
    work/ home/ team/ inbox/ assistant/ settings/ billing/ profile/ connectors/
  lib/
    api/          клиент API, по файлу на домен (auth, leads, teams, work, telephony …); _core.ts — request()
    auth.ts       localStorage-зеркало пользователя (convioo.user)
    workspace.ts  выбранное пространство: личное или команда (convioo.workspace)
    roles.ts      navForRole — какие пункты меню у какой роли
    i18n/         переводы ru / uk / en (строки в коде — только через t("ключ"))
    toast.ts confirm.ts prompt.tsx   уведомления и диалоги
    hooks/        useAbortable, useMediaQuery
```

---

## Если ломается — куда смотреть

| Симптом | Где искать |
|---|---|
| Не могу зарегистрироваться / «invite code» | `routes/account/auth.py` (`register`), переменная `REGISTRATION_PASSWORD` на Railway; форма `app/register/page.tsx` |
| После входа пустое меню, «not a team member», «не удалось загрузить» | `components/shell/RequireAuth.tsx` (401 → выход), `components/layout/Sidebar.tsx` (самолечение протухшей команды), `lib/workspace.ts` |
| Видно не те пункты меню | `lib/roles.ts` → `navForRole`, роль приходит из `GET /teams/{id}` |
| sales видит чужие лиды / deal_value | `core/services/account/team_permissions.py`, фильтры в `routes/crm/leads.py` |
| Поиск не стартует / нет результатов | `routes/search/search.py` → `pipeline/search.py` → `collectors/`; лимиты — `core/services/search/cost_control.py` |
| Звонок не идёт | `routes/sales/telephony.py` (`start_call`, `webrtc-token`, webhook) → `core/services/sales/telephony/{ringostat,telnyx}.py`; переменные `RINGOSTAT_*`, `TELNYX_*`, `TELEPHONY_ROUTES`; фронт — `lib/telephony/browserCall.ts` |
| Запись/расшифровка звонка не появилась | `core/services/sales/telephony/processing.py`, вебхук `POST /telephony/webhook/ringostat` |
| Касание воронки не ушло / очередь работы пустая | `core/services/sales/funnel_engine.py`, `routes/sales/work.py`, кроны в `queue/worker.py` |
| Письмо не отправилось / не видим ответ | `core/services/outreach/email_sender.py`, `email_reply_tracker.py`, `inbox_sync.py`; OAuth-токены — `integrations/oauth_store.py` |
| Notion/HubSpot/Pipedrive рассинхрон | `routes/integrations/<сервис>.py` + `src/leadgen/integrations/<сервис>.py` |
| Дайджест/уведомление не пришло | `core/services/account/team_events.py`, `sales/digest.py`, `queue/worker.py` |
| Stripe / тариф | `routes/platform/billing.py`, `core/services/platform/billing_service.py` (`BILLING_ENFORCED=false`) |
| Текст не переведён | `frontend/lib/i18n/{ru,uk,en}.ts` — ключ должен быть во всех трёх |

---

## Проверка перед пушем

```bash
# бэкенд
source .venv/bin/activate && ruff check src tests && pytest -q
# фронт
cd frontend && npx tsc --noEmit && npx next lint && npx next build
```

Тесты лежат в `tests/` плоско, по одному файлу на тему
(`test_auth_recovery.py`, `test_telephony.py`, `test_funnels.py` …).
