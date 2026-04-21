# Leadgen

Telegram-бот для поиска B2B-лидов через Google Places с enrichment по сайту и AI-анализом.

## Что уже умеет

- Диалог в Telegram: ниша + регион → запуск поиска.
- Сбор компаний из Google Places Text Search.
- Глубокий enrichment до 50 лидов: сайт, соцсети (включая Instagram/Facebook, если есть на сайте), отзывы.
- AI-скоринг и рекомендации по заходу к клиенту.
- Отправка отчёта в Telegram + экспорт в Excel.

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
```

### Применить миграции

```bash
alembic upgrade head
```

### Запуск бота

```bash
python -m leadgen
```

## Переменные окружения

См. `.env.example`.

Ключевые:

- `BOT_TOKEN`
- `GOOGLE_PLACES_API_KEY`
- `DATABASE_URL` (например `postgresql://user:pass@localhost:5432/leadgen`)
- `ANTHROPIC_API_KEY`

## Разработка

### Линт

```bash
ruff check src tests
```

### Тесты

```bash
pytest
```

## CI

В репозитории добавлен workflow `.github/workflows/ci.yml`, который запускает:

1. `ruff check src tests`
2. `pytest`

на Python 3.12.

## Важно по БД

- Создание схемы через runtime больше не используется.
- Схема управляется только через Alembic (`alembic/versions/*`).


## Railway: обязательные переменные

Минимум для запуска:

- `BOT_TOKEN`
- `DATABASE_URL`
- `GOOGLE_PLACES_API_KEY`

Рекомендуется для максимального качества AI-анализа:

- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`

Остальные (лимиты/логирование):

- `LOG_LEVEL`
- `DEFAULT_QUERIES_LIMIT`
- `MAX_RESULTS_PER_QUERY`
- `MAX_ENRICH_LEADS`
- `ENRICH_CONCURRENCY`
- `HTTP_RETRIES`
- `HTTP_RETRY_BASE_DELAY`


## Концепция продукта

Подробная продуктовая концепция описана в `BOT_CONCEPT.md`.
