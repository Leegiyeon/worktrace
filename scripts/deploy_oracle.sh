#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_DIR="${APP_DIR:-/home/ubuntu/worktrace}"
readonly COMPOSE=(
  docker compose
  --env-file .env.production
  -f docker-compose.prod.yml
  -f docker-compose.oracle.yml
)
readonly LEGACY_COMPOSE=(
  docker compose
  -p work-support
  --env-file .env.production
  -f docker-compose.prod.yml
  -f docker-compose.oracle.yml
)

cd "$APP_DIR"

test -f .env.production || {
  echo "Missing $APP_DIR/.env.production" >&2
  exit 1
}

deployment_diagnostics() {
  local exit_code="$?"
  trap - ERR
  set +e
  echo "Deployment command failed with exit code $exit_code. Collecting diagnostics..." >&2
  "${COMPOSE[@]}" ps -a
  "${COMPOSE[@]}" logs --tail=150 db backend frontend
  exit "$exit_code"
}

trap deployment_diagnostics ERR

sed -i 's/^WORK_SUPPORT_PASSWORD_HASH=/WORKTRACE_PASSWORD_HASH=/' .env.production
sed -i 's/^WORK_SUPPORT_SESSION_SECRET=/WORKTRACE_SESSION_SECRET=/' .env.production

git fetch --prune origin main
git checkout main
git pull --ff-only origin main

if docker ps -a --filter label=com.docker.compose.project=work-support --format '{{.ID}}' | grep -q .; then
  "${LEGACY_COMPOSE[@]}" stop backend frontend db
  "${LEGACY_COMPOSE[@]}" rm -f backend frontend db
fi

"${COMPOSE[@]}" up -d --build --remove-orphans db backend frontend

for attempt in {1..30}; do
  if curl --fail --silent --show-error http://127.0.0.1:8200/health/ready >/dev/null \
    && curl --fail --silent --show-error http://127.0.0.1:3200/login >/dev/null; then
    "${COMPOSE[@]}" ps
    echo "Deployment health checks passed."
    trap - ERR
    exit 0
  fi
  sleep 2
done

"${COMPOSE[@]}" ps
"${COMPOSE[@]}" logs --tail=100 backend frontend
echo "Deployment health checks failed." >&2
exit 1
