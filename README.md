# Convioo

B2B lead-gen + lightweight CRM для маркетинговых агентств. Веб-аппа на
Next.js поверх Python-бэкенда: поиск через Google Places, enrichment
по сайту и отзывам, AI-скоринг и outreach-драфты от Claude, полноценный
лид-менеджмент с задачами, активити-таймлайном и Excel/CSV экспортом.

> Python-пакет на диске называется `leadgen` (исторически), бренд и
> репозиторий — `Convioo`. Импорт-пути не трогать.

## Что умеет

- Поиск B2B-лидов: ниша + регион → выдача из Google Places.
- Глубокий enrichment до 50 лидов: сайт, соцсети, отзывы, decision-maker.
- AI-скоринг и outreach-драфты через Claude Haiku.
- Полный CRM: статусы, заметки, кастом-поля, задачи, активити-таймлайн.
- Henry — встроенный AI-ассистент: чат, weekly check-in, per-lead research.
- Команды + приглашения, GDPR-экспорт, audit log.
- Excel + CSV экспорт сессии и общего CRM.
- Startup-recovery: зависший при рестарте запрос автоматически
  помечается `failed`.

## Требования

- Python 3.12+
- PostgreSQL 15+
- Google Places API key
- (Опционально) Anthropic API key — без него работает fallback-оценка
- (Опционально для прода) Redis — фоновые поиски через arq

## Быстрый старт (локально)

```bash
# Бэкенд
python -m venv .venv
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
```

## Деплой

- **Backend** — Railway (Dockerfile + entrypoint.sh): `alembic upgrade head` → `python -m leadgen`.
- **Frontend** — Vercel, root directory `frontend`. Автодеплой на push в main.

## Переменные окружения

### Обязательные

| Переменная | Где взять |
|---|---|
| `DATABASE_URL` | Railway плагин PostgreSQL подставит сам. Локально: `postgresql://user:pass@localhost:5432/convioo` |
| `GOOGLE_PLACES_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) → Places API (New) → API key. |

### Рекомендуемые

| Переменная | Где взять |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) → Settings → API Keys. Без ключа используется эвристический fallback. |
| `ANTHROPIC_MODEL` | Дефолт: `claude-haiku-4-5-20251001`. |
| `PUBLIC_APP_URL` | Vercel-домен. Используется для email-верификации и инвайтов. |
| `WEB_CORS_ORIGINS` | Список Vercel-доменов через запятую. |
| `RESEND_API_KEY` | Для отправки email (верификация / инвайты). |
| `REDIS_URL` | Включает arq-воркер для фоновых поисков. |

Полный список — в `.env.example` и `src/leadgen/config.py`.

## Разработка

```bash
ruff check src tests
pytest -q
alembic upgrade head
```

CI (`.github/workflows/ci.yml`) поднимает postgres, прогоняет миграции, линт и тесты на каждый push.

## История

Раньше у проекта был Telegram-бот (aiogram, `src/leadgen/bot/`,
`src/leadgen/adapters/telegram/`). Он был выключен и удалён,
пока ведётся переход на новый бот, который пристыкуется к тем же
`core/services` и пайплайну поиска через `run_search_with_sinks`.
