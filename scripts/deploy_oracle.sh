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

if [[ "$#" -ne 1 ]]; then
  echo "Usage: $0 <verified-commit-sha>" >&2
  exit 64
fi

readonly DEPLOY_SHA="$1"
if [[ ! "$DEPLOY_SHA" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "Deploy SHA must be an exact 40-character commit SHA." >&2
  exit 64
fi

if [[ "$APP_DIR" == "/home/ubuntu/worktrace" && -d /home/ubuntu/work-support && ! -e "$APP_DIR" ]]; then
  mv /home/ubuntu/work-support "$APP_DIR"
fi

cd "$APP_DIR"

test -f .env.production || {
  echo "Missing $APP_DIR/.env.production" >&2
  exit 1
}

worktree_status="$(git status --porcelain --untracked-files=normal)"
if [[ -n "$worktree_status" ]]; then
  echo "Refusing to deploy from a dirty worktree. Commit, move, or explicitly remove local source changes first." >&2
  printf '%s\n' "$worktree_status" >&2
  exit 1
fi

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
git checkout --detach "$DEPLOY_SHA"
checked_out_sha="$(git rev-parse HEAD)"
if [[ "$checked_out_sha" != "$DEPLOY_SHA" ]]; then
  echo "Checked out $checked_out_sha, expected $DEPLOY_SHA" >&2
  exit 1
fi
echo "Deploying verified revision: $checked_out_sha"

"${COMPOSE[@]}" up -d --wait db
"${COMPOSE[@]}" build backend
"${COMPOSE[@]}" run --rm --no-deps backend python scripts/migrate_db.py --preflight

"${COMPOSE[@]}" down --remove-orphans

if docker ps -a --filter label=com.docker.compose.project=work-support --format '{{.ID}}' | grep -q .; then
  "${LEGACY_COMPOSE[@]}" stop backend frontend db
  "${LEGACY_COMPOSE[@]}" rm -f backend frontend db
fi

"${COMPOSE[@]}" up -d --build --remove-orphans db backend frontend

"${COMPOSE[@]}" exec -T backend python scripts/migrate_db.py

for attempt in {1..30}; do
  if curl --fail --silent --show-error http://127.0.0.1:8200/health/ready >/dev/null \
    && curl --fail --silent --show-error http://127.0.0.1:3200/login >/dev/null; then
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
