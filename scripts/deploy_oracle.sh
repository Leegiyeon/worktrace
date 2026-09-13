#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_DIR="${APP_DIR:-/home/ubuntu/worktrace}"
readonly REPOSITORY_URL="${REPOSITORY_URL:-https://github.com/Leegiyeon/worktrace.git}"
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

# The repository was renamed from work-support to worktrace. GitHub redirects the old URL,
# but keep the production checkout canonical so diagnostics and future automation do not depend on redirects.
git remote set-url origin "$REPOSITORY_URL"
echo "Git origin: $(git remote get-url origin)"
git fetch --prune origin main
git checkout main
git pull --ff-only origin main

"${COMPOSE[@]}" down --remove-orphans

if docker ps -a --filter label=com.docker.compose.project=work-support --format '{{.ID}}' | grep -q .; then
  "${LEGACY_COMPOSE[@]}" stop backend frontend db
  "${LEGACY_COMPOSE[@]}" rm -f backend frontend db
fi

"${COMPOSE[@]}" up -d --build --remove-orphans db backend frontend

# PostgreSQL's docker-entrypoint init scripts run only when the data volume is first created.
# Re-apply every idempotent schema/migration file on deploy so existing production volumes
# receive additive Worktrace schema changes as well. Resolve database credentials inside the
# running DB container so existing installations keep using the role/database that owns them.
for migration in infrastructure/postgres/init/*.sql; do
  echo "Applying database migration: $migration"
  "${COMPOSE[@]}" exec -T db sh -c \
    'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    < "$migration"
done

for attempt in {1..30}; do
  if curl --fail --silent --show-error http://127.0.0.1:8200/health/ready >/dev/null \
    && curl --fail --silent --show-error http://127.0.0.1:3200/login >/dev/null; then
    "${COMPOSE[@]}" exec -T -e GITHUB_SYNC_TOKEN backend python scripts/sync_github_data.py --cleanup-samples
    "${COMPOSE[@]}" exec -T backend python scripts/report_progress_snapshot.py
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
