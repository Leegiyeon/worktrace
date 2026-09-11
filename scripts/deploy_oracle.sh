#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_DIR="${APP_DIR:-/home/ubuntu/worktrace}"
readonly COMPOSE=(
  docker compose
  --env-file .env.production
  -f docker-compose.prod.yml
  -f docker-compose.oracle.yml
)

cd "$APP_DIR"

test -f .env.production || {
  echo "Missing $APP_DIR/.env.production" >&2
  exit 1
}

sed -i 's/^WORK_SUPPORT_PASSWORD_HASH=/WORKTRACE_PASSWORD_HASH=/' .env.production
sed -i 's/^WORK_SUPPORT_SESSION_SECRET=/WORKTRACE_SESSION_SECRET=/' .env.production

git fetch --prune origin main
git checkout main
git pull --ff-only origin main

"${COMPOSE[@]}" up -d --build --remove-orphans db backend frontend

for attempt in {1..30}; do
  if curl --fail --silent --show-error http://127.0.0.1:8200/health/ready >/dev/null \
    && curl --fail --silent --show-error http://127.0.0.1:3200/login >/dev/null; then
    "${COMPOSE[@]}" ps
    echo "Deployment health checks passed."
    exit 0
  fi
  sleep 2
done

"${COMPOSE[@]}" ps
"${COMPOSE[@]}" logs --tail=100 backend frontend
echo "Deployment health checks failed." >&2
exit 1
