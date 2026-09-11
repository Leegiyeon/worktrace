#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/restore_local.sh --confirm BACKUP_FILE

Restores a local PostgreSQL custom-format backup into the Docker Compose db service.
This replaces database objects from the backup. The --confirm flag is required.
USAGE
}

confirm=false
backup_file=""

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --confirm)
      confirm=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "${backup_file}" ]]; then
        usage >&2
        exit 2
      fi
      backup_file="$1"
      shift
      ;;
  esac
done

if [[ "${confirm}" != "true" || -z "${backup_file}" ]]; then
  usage >&2
  echo "Restore requires: --confirm BACKUP_FILE" >&2
  exit 2
fi

if [[ ! -f "${backup_file}" ]]; then
  echo "Backup file does not exist or is not a regular file: ${backup_file}" >&2
  exit 1
fi

if [[ ! -r "${backup_file}" ]]; then
  echo "Backup file is not readable: ${backup_file}" >&2
  exit 1
fi

if [[ ! -s "${backup_file}" ]]; then
  echo "Backup file is empty: ${backup_file}" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_SERVICE="${COMPOSE_DB_SERVICE:-db}"
restore_file="${backup_file}"
decrypted_file=""

cleanup() {
  [[ -z "${decrypted_file}" ]] || rm -f -- "${decrypted_file}"
}
trap cleanup EXIT

if [[ "${backup_file}" == *.enc ]]; then
  encryption_key_file="${BACKUP_ENCRYPTION_KEY_FILE:-}"
  if [[ -z "${encryption_key_file}" || ! -f "${encryption_key_file}" || ! -r "${encryption_key_file}" ]]; then
    echo "BACKUP_ENCRYPTION_KEY_FILE must reference a readable file for encrypted backups." >&2
    exit 1
  fi
  decrypted_file="$(mktemp "${TMPDIR:-/tmp}/worktrace_restore.XXXXXX.dump")"
  chmod 600 "${decrypted_file}"
  openssl enc -d -aes-256-cbc -pbkdf2 -pass "file:${encryption_key_file}" -in "${backup_file}" -out "${decrypted_file}"
  restore_file="${decrypted_file}"
fi

cd "${REPO_ROOT}"

container_id="$(docker compose ps -q "${COMPOSE_SERVICE}")"
if [[ -z "${container_id}" ]]; then
  echo "Docker Compose db service is not available. Start it with: docker compose up -d ${COMPOSE_SERVICE}" >&2
  exit 1
fi

docker compose exec -T "${COMPOSE_SERVICE}" pg_restore --list < "${restore_file}" >/dev/null

docker compose exec -T "${COMPOSE_SERVICE}" sh -eu -c '
  pg_restore \
    --clean \
    --exit-on-error \
    --if-exists \
    --no-owner \
    --no-privileges \
    --dbname="${POSTGRES_DB}" \
    --username="${POSTGRES_USER}"
' < "${restore_file}"

echo "Restore completed from: ${backup_file}"
