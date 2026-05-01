# Convioo

B2B lead-gen + lightweight CRM для маркетинговых агентств. Веб-аппа на
Next.js поверх Python-бэкенда: поиск через Google Places, multi-page
enrichment по сайту и отзывам, AI-скоринг и outreach-драфты от Claude,
полный лид-менеджмент с задачами / таймлайном / Excel-экспортом, плюс
Henry — встроенный ассистент, который учится на 👍/👎 фидбэке юзера.

> Python-пакет на диске называется `leadgen` (исторически), бренд и
> репозиторий — `Convioo`. Импорт-пути не трогать.

## Что умеет

- **Поиск** B2B-лидов: ниша + регион → Google Places (planned: OSM, Foursquare).
- **Глубокий enrichment** до 50 лидов: multi-page scraping (`/about`, `/team`,
  `/careers`, …), извлечение year-founded, team-size, hiring-сигнала,
  заголовков сайта, decision-maker'ов.
- **AI-скоринг + outreach-драфты** через Claude Haiku. Опционально
  A/B-вариант письма в одном запросе.
- **Henry учится на тебе**: 👍/👎 на каждый лид → твой ICP подмешивается
  в скоринг и cold-email промпты. Можно загружать PDF/TXT с прайсом
  / brochure — Henry будет цитировать в письмах.
- **CRM**: статусы, заметки, кастом-поля, задачи, активити-таймлайн,
  cross-session дедуп ("уже виделся в N сессиях").
- **Outreach SEND через Gmail OAuth** прямо из карточки лида.
- **Команды + приглашения**, GDPR-экспорт, audit log, аналитика.
- **CSV import** с AI-маппингом колонок (распознаёт «Назва компанії», и т.д.).
- **Аналитика** на `/app/analytics`: статусы, топ-ниши, A/B-сплит, 30-дневный график.
- **Browser extension** (Manifest v3) — one-click сохранение текущей
  страницы в CRM из любого сайта.

## Требования

- Python 3.12+
- PostgreSQL 15+
- Google Places API key
- (Рекомендуется) Anthropic API key — без него работает heuristic fallback
- (Опционально, для прода) Redis — фоновые поиски через arq
- (Опционально) Resend account + verified domain — для писем верификации
- (Опционально) Google Cloud OAuth client — для Gmail send

## Быстрый старт (локально)

```bash
# Бэкенд
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# заполни DATABASE_URL, GOOGLE_PLACES_API_KEY, ANTHROPIC_API_KEY
alembic upgrade head
python -m leadgen   # FastAPI на :8080

# Фронтенд
cd frontend
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL=http://localhost:8080
npm run dev   # localhost:3000

# Тесты + lint
pytest -q          # 169 тестов
ruff check src tests
```

## Структура репозитория

```
src/leadgen/
  core/services/             ← framework-agnostic: billing, email_sender,
                                gmail_service, icp_service, knowledge_files,
                                lead_fingerprint, assistant_memory, sinks,
                                progress_broker
  adapters/web_api/          ← FastAPI: app.py (factory), helpers.py,
                                schemas.py (pydantic), sinks.py, auth.py
  pipeline/                  ← search.py, enrichment.py, recovery.py
  collectors/                ← google_places.py, website.py (multi-page)
  analysis/                  ← ai_analyzer.py, csv_mapping.py, henry_core.py,
                                knowledge.py, aggregator.py
  db/                        ← models.py (24 tables), session.py
  queue/                     ← arq enqueue + worker (когда есть Redis)
  export/                    ← excel.py
  utils/                     ← rate_limit, secrets, retry, metrics

frontend/                    ← Next.js 14 App Router, 25 страниц
                                (`/app/analytics` свежий)
browser-extension/           ← Manifest v3 Chrome / Edge экстеншен
                                (загружается unpacked)
alembic/versions/            ← 24 миграции
tests/                       ← pytest + aiosqlite, 169 тестов
```

## Деплой

- **Backend** — Railway. Dockerfile + entrypoint.sh: `alembic upgrade head`
  → `python -m leadgen`.
- **Frontend** — Vercel, root directory `frontend`. Автодеплой на push в
  `main`. Production-домен: `convioo.com`.
- **Worker** — отдельный Railway service `arq leadgen.queue.worker.WorkerSettings`,
  активируется когда задан `REDIS_URL`.

## Переменные окружения

### Обязательные

| Переменная | Где взять |
|---|---|
| `DATABASE_URL` | Railway PostgreSQL plugin / `postgresql://user:pass@localhost:5432/convioo` |
| `GOOGLE_PLACES_API_KEY` | Google Cloud Console → Places API (New) → API key |

### Рекомендуемые

| Переменная | Что делает |
|---|---|
| `ANTHROPIC_API_KEY` | Включает Claude scoring + cold-email + Henry. Без ключа — heuristic fallback. |
| `ANTHROPIC_MODEL` | Дефолт `claude-haiku-4-5-20251001`. |
| `PUBLIC_APP_URL` | Базовый URL фронта. Email-верификация + инвайты ссылаются на него. |
| `WEB_CORS_ORIGINS` | Список Vercel-доменов через запятую. |
| `WEB_API_KEY` | Защищает `/api/v1/admin/email/test` и SSE. Любая длинная случайная строка. |

### Email (Resend)

| Переменная | Что делает |
|---|---|
| `RESEND_API_KEY` | Без ключа `send_email` логирует в stdout вместо отправки. |
| `EMAIL_FROM` | Должен использовать домен, верифицированный в Resend (SPF + DKIM). |

### Gmail OAuth (отправка писем лидам)

| Переменная | Что делает |
|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | Из Google Cloud Console → Credentials → OAuth client (Web). |
| `GOOGLE_OAUTH_TOKEN_KEY` | Fernet-ключ (base64url) для шифрования токенов. `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `PUBLIC_API_URL` | Публичный URL Railway. Должен совпадать с redirect URI в OAuth client. |

### Прочее

| Переменная | Что делает |
|---|---|
| `REDIS_URL` | Включает arq-воркер. Без неё поиски идут inline в API-процессе. |
| `BILLING_ENFORCED` | `true` включит реальный gating по квоте. По дефолту off. |
| `REGISTRATION_PASSWORD` | Если задан — `/auth/register` требует invite-код. |

Полный список — в `.env.example` и `src/leadgen/config.py`.

## Разработка

```bash
pytest -q                           # 169 тестов
ruff check src tests                # линт
alembic upgrade head                # миграции в локальный postgres / sqlite
cd frontend && npx tsc --noEmit     # type-check фронта
```

CI (`.github/workflows/ci.yml`) поднимает PostgreSQL, прогоняет миграции,
линт и pytest на каждый push.

## Browser extension

`browser-extension/` — Manifest v3 для Chrome / Edge.
Установка:

1. `chrome://extensions` → включи **Developer mode**.
2. **Load unpacked** → выбери папку `browser-extension/`.
3. Иконка в тулбаре → правый клик → **Options** → задай API URL +
   user ID (взять в `/app/profile`).

См. `browser-extension/README.md` для деталей.

## История

Раньше у проекта был Telegram-бот (aiogram, `src/leadgen/bot/`,
`src/leadgen/adapters/telegram/`). Он был удалён в PR #22; ребилд
будет идти через тонкий адаптер поверх существующих `core/services`
и `run_search_with_sinks`.

Подробный handoff для AI-агента, открывающего проект первый раз —
в `CLAUDE.md`.
