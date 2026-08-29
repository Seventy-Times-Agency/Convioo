#!/usr/bin/env bash
# Первый пуш Convloo в GitLab.
#
# Запуск из корня репозитория:
#   bash scripts/push-to-gitlab.sh git@gitlab.com:<username>/convloo.git
# или по HTTPS (спросит логин и Personal Access Token со scope write_repository):
#   bash scripts/push-to-gitlab.sh https://gitlab.com/<username>/convloo.git
#
# Проект в GitLab создать заранее ПУСТЫМ: New project -> Create blank project,
# снять галку "Initialize repository with a README", Visibility = Private.

set -euo pipefail

REMOTE_URL="${1:-}"
BRANCH="${2:-main}"

if [ -z "$REMOTE_URL" ]; then
  echo "Использование: bash scripts/push-to-gitlab.sh <git-url> [ветка]" >&2
  exit 1
fi

if [ ! -d .git ]; then
  echo "Нет .git — запускай из корня репозитория (там, где pyproject.toml)." >&2
  exit 1
fi

# Ветка main (репозиторий собран с ней; на всякий случай приводим имя).
git branch -M "$BRANCH"

# Один remote с именем origin, идемпотентно.
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

echo "origin -> $(git remote get-url origin)"
echo "ветка  -> $BRANCH"
echo "коммитов: $(git rev-list --count HEAD)"

# Проверка, что в индексе нет случайного мусора: .env, база, node_modules.
if git ls-files | grep -Eq '(^|/)(\.env$|convloo\.db$|node_modules/|\.venv/|\.next/)'; then
  echo "СТОП: в индекс попали игнорируемые файлы — проверь .gitignore." >&2
  git ls-files | grep -E '(^|/)(\.env$|convloo\.db$|node_modules/|\.venv/|\.next/)' >&2
  exit 1
fi

git push -u origin "$BRANCH"

echo
echo "Готово. Дальше в GitLab:"
echo "  Settings -> CI/CD -> Variables: добавить прод-переменные из .env.example"
echo "  Settings -> Repository -> Protected branches: защитить $BRANCH"
echo "  Пайплайн .gitlab-ci.yml запустится сам на первом же пуше."
