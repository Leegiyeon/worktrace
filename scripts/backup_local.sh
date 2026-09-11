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
backup_file="${BACKUP_DIR}/worktrace_${timestamp}.dump"
tmp_file="${backup_file}.tmp.$$"
encryption_key_file="${BACKUP_ENCRYPTION_KEY_FILE:-}"

if [[ "${APP_ENV:-local}" == "production" && -z "${encryption_key_file}" ]]; then
  echo "BACKUP_ENCRYPTION_KEY_FILE is required in production." >&2
  exit 1
fi
if [[ -n "${encryption_key_file}" && ( ! -f "${encryption_key_file}" || ! -r "${encryption_key_file}" ) ]]; then
  echo "Backup encryption key file is not readable: ${encryption_key_file}" >&2
  exit 1
fi

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
if [[ -n "${encryption_key_file}" ]]; then
  encrypted_file="${backup_file}.enc"
  openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:${encryption_key_file}" -in "${tmp_file}" -out "${encrypted_file}"
  chmod 600 "${encrypted_file}"
  rm -f -- "${tmp_file}"
  backup_file="${encrypted_file}"
else
  mv -- "${tmp_file}" "${backup_file}"
fi
trap - EXIT

echo "Backup written: ${backup_file}"
