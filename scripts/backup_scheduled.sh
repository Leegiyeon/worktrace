#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups/postgres}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
LOCK_DIR="${BACKUP_DIR}/.backup.lock"

if ! [[ "${BACKUP_RETENTION_DAYS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "BACKUP_RETENTION_DAYS must be a positive integer." >&2
  exit 2
fi

mkdir -p -- "${BACKUP_DIR}"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "Another backup is already running." >&2
  exit 1
fi
trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT

BACKUP_DIR="${BACKUP_DIR}" "${SCRIPT_DIR}/backup_local.sh"
find "${BACKUP_DIR}" -type f \( -name 'worktrace_*.dump' -o -name 'worktrace_*.dump.enc' \) -mtime "+${BACKUP_RETENTION_DAYS}" -delete

echo "Backup retention applied: ${BACKUP_RETENTION_DAYS} days"
