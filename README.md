# Convioo

B2B lead-gen + lightweight CRM для маркетинговых агентств. Telegram-бот
и веб-аппа (Next.js) поверх одного бэкенда: поиск через Google Places,
enrichment по сайту и отзывам, AI-скоринг и outreach-драфты от Claude,
лид-менеджмент с задачами и активити-таймлайном.

> Python-пакет на диске называется `leadgen` (исторически), бренд и
> репозиторий — `Convioo`. Импорт-пути не трогать.

## Что умеет

- Диалог в Telegram: ниша + регион → запуск поиска.
- Сбор компаний из Google Places Text Search.
- Глубокий enrichment до 50 лидов: сайт, соцсети (включая Instagram/Facebook, если есть на сайте), отзывы.
- AI-скоринг и рекомендации как заходить к клиенту.
- Отправка отчёта в Telegram + экспорт в Excel.
- Startup-recovery: если процесс перезапустится во время поиска, зависший запрос автоматически помечается `failed` и пользователь получает уведомление.

## Требования

- Python 3.12+
- PostgreSQL 15+
- Telegram Bot Token
- Google Places API key
- (Опционально) Anthropic API key — без него работает fallback-оценка

## Быстрый старт (локально)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# заполни переменные в .env
alembic upgrade head
python -m leadgen
```

## Деплой на Railway

1. Создай в Railway проект и подключи к этому репозиторию.
2. Добавь в проект плагин **PostgreSQL** — Railway сам прокинет `DATABASE_URL`.
3. В **Variables** заполни как минимум `BOT_TOKEN` и `GOOGLE_PLACES_API_KEY` (см. раздел ниже).
4. Railway автоматически выполнит `alembic upgrade head && python -m leadgen` (прописано в `railway.json` и `Dockerfile`).

При каждом деплое миграции применяются автоматически — схема БД не рассинхронизируется.

## Переменные окружения

### Обязательные

| Переменная | Где взять |
|---|---|
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) → `/newbot` → выдаст токен вида `123456:AAE...` |
| `DATABASE_URL` | Railway плагин PostgreSQL подставит сам. Локально: `postgresql://user:pass@localhost:5432/leadgen` |
| `GOOGLE_PLACES_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) → создать проект → включить **Places API (New)** → APIs & Services → Credentials → **Create credentials → API key**. Включить биллинг (есть бесплатный лимит). |

### Рекомендуемые

| Переменная | Где взять |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) → Settings → API Keys → Create Key. Без него бот использует эвристический fallback. |
| `ANTHROPIC_MODEL` | Модель Claude. Дефолт: `claude-haiku-4-5-20251001` (самая дешёвая и быстрая для массового enrichment). |

### Опциональные (есть разумные дефолты)

| Переменная | Дефолт | Что делает |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Уровень логов: `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `DEFAULT_QUERIES_LIMIT` | `5` | Сколько поисков новый пользователь может сделать |
| `MAX_RESULTS_PER_QUERY` | `50` | Сколько компаний максимум тянем из Google Places |
| `MAX_ENRICH_LEADS` | `50` | Сколько топ-лидов отправлять на глубокий анализ |
| `ENRICH_CONCURRENCY` | `5` | Параллелизм при запросах к сайтам лидов |
| `HTTP_RETRIES` | `3` | Кол-во повторов при сетевых ошибках |
| `HTTP_RETRY_BASE_DELAY` | `0.7` | Базовая задержка exponential-backoff (секунды) |

Полный список — в `.env.example`.

## Разработка

```bash
ruff check src tests    # линт
pytest                  # тесты (13 штук)
alembic upgrade head    # миграции
```

CI (`.github/workflows/ci.yml`) поднимает postgres, прогоняет миграции, линт и тесты на каждый push.

## База данных

- Схема управляется только через Alembic (`alembic/versions/*`).
- `metadata.create_all` в рантайме больше не используется.
- На старте бот выполняет recovery: находит `pending`/`running` запросы, которые не пережили рестарт, помечает `failed` и уведомляет пользователей.

## Концепция продукта

См. `BOT_CONCEPT.md`.
