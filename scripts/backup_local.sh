#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/backup_local.sh

Creates a local PostgreSQL custom-format backup from the Docker Compose db service.
The backup is written under backups/postgres/ with owner-only permissions.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$#" -ne 0 ]]; then
  usage >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups/postgres}"
COMPOSE_SERVICE="${COMPOSE_DB_SERVICE:-db}"

umask 077
mkdir -p -- "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_file="${BACKUP_DIR}/work_support_${timestamp}.dump"
tmp_file="${backup_file}.tmp.$$"

cleanup() {
  rm -f -- "${tmp_file}"
}
trap cleanup EXIT

cd "${REPO_ROOT}"

container_id="$(docker compose ps -q "${COMPOSE_SERVICE}")"
if [[ -z "${container_id}" ]]; then
  echo "Docker Compose db service is not available. Start it with: docker compose up -d ${COMPOSE_SERVICE}" >&2
  exit 1
fi

docker compose exec -T "${COMPOSE_SERVICE}" sh -eu -c '
  pg_dump \
    --format=custom \
    --no-owner \
    --no-privileges \
    --dbname="${POSTGRES_DB}" \
    --username="${POSTGRES_USER}"
' > "${tmp_file}"

docker compose exec -T "${COMPOSE_SERVICE}" pg_restore --list < "${tmp_file}" >/dev/null
chmod 600 "${tmp_file}"
mv -- "${tmp_file}" "${backup_file}"
trap - EXIT

echo "Backup written: ${backup_file}"
