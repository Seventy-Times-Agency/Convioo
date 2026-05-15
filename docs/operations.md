# Convioo — runbook

Краткий ops-справочник: куда смотреть и что нажимать, когда что-то не так. Дополнение к `CLAUDE.md` (там общая инструкция по проекту) и `REVIEW.md` (полный технический аудит).

## Окружения

| Среда | Backend | Frontend | БД |
|---|---|---|---|
| Production | Railway сервис `convioo` | Vercel `convioo-web` | Railway Postgres (managed) |
| Preview (PR) | Railway PR-environment | Vercel preview deploy | Pre-PR Postgres branch |
| Local | `python -m leadgen` :8080 | `npm run dev` :3000 | DATABASE_URL по выбору |

## Деплой

Push в `main` → автодеплой:
- Railway пересобирает `Dockerfile` → `entrypoint.sh` → `alembic upgrade head` → `python -m leadgen`.
- Vercel пересобирает frontend.

После пуша:
```bash
curl -s https://<railway-url>/health | jq
```
Должно вернуть `{"status":"healthy","db":true}` и `commit` = SHA свежего merge-коммита. Если не вернуло за 60с — смотри Railway logs.

## Откат

### Frontend (Vercel)
1. Открой проект `convioo-web` в Vercel → Deployments.
2. Найди предыдущий зелёный production-deploy.
3. «Promote to Production». Откат — мгновенный.

### Backend (Railway)
Railway не имеет one-click rollback с миграциями. План:
1. Revert PR в GitHub → пуш в main → Railway пересоберёт.
2. Если у revert-коммита нет downgrade-миграций, добавь их вручную. Проверь `alembic history` и нужные `op.create_index` / `op.alter_column`.
3. Перед запуском revert сделай дамп БД: Railway Postgres → `Settings → Backup`.

### Миграции
Каждый файл в `alembic/versions/` имеет `downgrade()`. Откатить одну миграцию:
```bash
alembic downgrade -1
```
До конкретной ревизии:
```bash
alembic downgrade 20260507_0048
```
**Внимание:** дедупликация в миграции `20260512_0049` (по `lower(email)`) — необратимая. Если откатываешь её, дубликаты не восстановятся.

## Где смотреть, когда плохо

| Симптом | Куда |
|---|---|
| 5xx на API | Sentry (issues / alerts) → Railway service logs → `/health` |
| Растёт p95 запросов | Sentry Performance → Railway metrics → `pg_stat_statements` в Postgres |
| Pool starvation (`QueuePool limit overflow`) | Postgres `pg_stat_activity` — посчитать активных коннектов; поднять `pool_size` в `db/session.py` (текущий 20+40) |
| Не приходят email | Resend dashboard → search by `to:` → проверить bounce/spam |
| OAuth callback падает | Railway logs → искать `oauth_state` или `notion_oauth` → проверить `AUTH_JWT_SECRET` и `FERNET_KEY` (не менялись?) |
| arq worker не стартует | Railway WORKER service logs → Redis URL валиден? |
| Stripe webhook невалиден | Stripe dashboard → Webhook → `Recent deliveries` → текст ошибки. Не меняй `STRIPE_WEBHOOK_SECRET` без обновления в Railway |

## Часто меняемые переменные

| Имя | Где | Меняется при |
|---|---|---|
| `DATABASE_URL` | Railway → `convioo` | Изменение БД instance / параметров |
| `ANTHROPIC_API_KEY` | Railway → `convioo` | Ротация ключа |
| `GOOGLE_PLACES_API_KEY` | Railway → `convioo` | Ротация ключа |
| `AUTH_JWT_SECRET` | Railway → `convioo` | **НЕ МЕНЯТЬ без необходимости** — инвалидирует все активные сессии и API ключи (через legacy_hash_token fallback всё переживёт первое использование, но новые токены не сматчатся со старыми хешами после ротации) |
| `FERNET_KEY` | Railway → `convioo` | **НЕ МЕНЯТЬ без необходимости** — все OAuth токены становятся нечитаемыми, пользователи теряют интеграции |
| `WEB_CORS_ORIGINS` | Railway → `convioo` | Добавление нового домена; запрещено `*` (приложение упадёт на старте) |
| `PUBLIC_APP_URL` | Railway → `convioo` | Смена домена; используется в email-ссылках и OAuth redirect_uri |
| `BILLING_ENFORCED` | Railway → `convioo` | Включение биллинга (по умолчанию false) |

## Здоровье БД

```sql
-- Активные коннекты (если близко к 100 — поднимаем pgbouncer)
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';

-- Самые медленные запросы за неделю
SELECT mean_exec_time, calls, query
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 20;

-- Дублирующиеся индексы / неиспользуемые
SELECT indexrelname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 10;
```

## Инциденты

Шаблон записи (заводи новую секцию ниже датой):

```
### YYYY-MM-DD — короткое описание

Симптом:
Корневая причина:
Что починили:
Как предотвратить:
```
