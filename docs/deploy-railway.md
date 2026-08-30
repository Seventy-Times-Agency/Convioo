# Railway — развёртывание API и воркера

Пошагово. Дополняет `docs/operations.md` (что делать, когда сломалось)
и `ПЕРВЫЙ-ЗАПУСК.md` (запуск на своей машине).

Всего в проекте четыре сервиса: **Postgres**, **Redis**, **API**,
**воркер**. API и воркер собираются из одного и того же образа —
отдельный Dockerfile для воркера не нужен, отличается только команда
запуска.

---

## Порядок

Порядок важен: воркеру нужна база со свежей схемой, а накатывает её
API. Не поднимайте воркер раньше, чем API отчитается о миграциях.

### 1. Postgres

New Project → Add Service → Database → **PostgreSQL**.

Railway сам выдаст `DATABASE_URL`. Приложение принимает и
`postgres://`, и `postgresql://` — приведение к async-драйверу
делается в коде (`config.py`, свойство `sqlalchemy_url`).

### 2. Redis

Add Service → Database → **Redis**. Даст `REDIS_URL`.

Redis нужен не для скорости, а для работы: без него воркер не
стартует вообще, и вместе с ним молчат все десять кронов —
авто-касания воронок, просроченные перезвоны, обе сводки,
сканирование ответов, синк инбокса.

### 3. API

Add Service → GitHub/GitLab Repo → этот репозиторий.

Сборка по Dockerfile подхватывается из `railway.json`, настраивать
builder вручную не нужно. Команду запуска не задавайте — сработает
`CMD` из Dockerfile (`python -m leadgen`).

Переменные:

| Переменная | Значение |
|---|---|
| `DATABASE_URL` | ссылка на Postgres-сервис |
| `REDIS_URL` | ссылка на Redis-сервис |
| `AUTH_JWT_SECRET` | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `FERNET_KEY` | `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `GOOGLE_PLACES_API_KEY` | реальный поиск лидов |
| `ANTHROPIC_API_KEY` | скоринг, выжимки, заходы |
| `PUBLIC_APP_URL` | домен фронта на Vercel |
| `WEB_CORS_ORIGINS` | тот же домен, через запятую если их несколько |

Полный список — в `.env.example`.

**Дождитесь в логах строки `STAGE 1: migrations OK`.** Пока её нет,
воркер не поднимайте.

Проверка:

```
curl -s https://<railway-api-url>/health
```

Ожидается `{"status":"healthy","db":true,...}`. Поле `redis` на этом
шаге ещё `null` — пул поднимается лениво.

### 4. Воркер

Add Service → тот же репозиторий → ещё один сервис.

| Настройка | Значение |
|---|---|
| Custom Start Command | `arq leadgen.queue.worker.WorkerSettings` |
| `RUN_MIGRATIONS` | `0` |
| `DATABASE_URL` | тот же Postgres |
| `REDIS_URL` | тот же Redis |
| остальные переменные | те же, что у API |

`RUN_MIGRATIONS=0` обязателен. Без него оба сервиса при
одновременном старте полезут накатывать миграции в одну базу.
Проигравший упадёт на конфликте объектов и уйдёт в ветку
восстановления `alembic stamp head` — она пометит схему актуальной,
не применив её. Отказ тихий, база остаётся недомигрированной.

Публичный домен воркеру не нужен — он ничего не слушает.

---

## Проверка, что воркер живой

```
curl -s https://<railway-api-url>/health
```

Теперь должно быть `"redis": true` и числовой `queue_depth`
(`health_probes.py:probe_redis_and_queue`). Если `redis` остался
`null` — переменная не долетела до API; если `false` — Redis
недоступен.

В логах самого воркера при старте видно список зарегистрированных
кронов. Если `REDIS_URL` не задан, воркер падает сразу с явным
сообщением — это сделано намеренно (`queue/worker.py:_on_startup`),
чтобы он не ушёл молча на `redis://localhost` и не делал вид, что
работает.

Первое реальное подтверждение: воронка с шагом-письмом и флагом
`auto` должна отправить касание в течение 10 минут — это интервал
`cron_funnel_touches`.

---

## Что делает воркер

| Крон | Расписание |
|---|---|
| `cron_funnel_touches` | каждые 10 минут |
| `cron_email_reply_scan` | каждые 5 минут |
| `cron_inbox_sync` | каждые 10 минут |
| `cron_overdue_callbacks` | ежечасно в :30 |
| `cron_daily_digest` | 09:00 UTC |
| `cron_morning_owner_digest` | 12:00 UTC |
| `cron_evening_digest` | 22:00 UTC |
| `decay_stale_leads` | 03:00 UTC |
| `cron_check_sequence_enrollments` | ежечасно |
| `check_crm_lead_ratings` | воскресенье 08:00 UTC |

Плюс фоновые задачи по требованию: `run_search_job`,
`send_sequence_step`.

Расписания заданы в UTC. Для отдела продаж в Киеве вечерняя сводка
в 22:00 UTC придёт в час ночи — при переходе на боевой режим
расписания стоит пересмотреть под часовой пояс команды.

---

## Демо-инстанс без ключей

Чтобы просто прокликать продукт снаружи, ключи не нужны. Один
сервис из репозитория, **без единой переменной**: без
`DATABASE_URL` берётся SQLite и демо-режим включается сам. На
Vercel задать `NEXT_PUBLIC_API_URL` на адрес этого сервиса.

Ограничения такого инстанса: SQLite на Railway обнуляется при
редеплое, воркера нет, парсер отдаёт муляж.

Принудительно демо включается и выключается через `DEMO_MODE=1` /
`DEMO_MODE=0` (`config.py`, свойство `demo_active`).
