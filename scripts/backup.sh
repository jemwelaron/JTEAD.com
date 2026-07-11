#!/usr/bin/env bash
# Backs up the SQLite database and uploaded manuscripts (jtead-instance/,
# the sibling directory outside the project root — see config.py) to a
# timestamped tarball, and prunes backups older than $RETENTION_DAYS.
#
# Not wired up to run automatically — add it to cron yourself, e.g.:
#   0 3 * * * BACKUP_DIR=/var/backups/jtead /path/to/jtead-website/scripts/backup.sh
#
# Only backs up the database file this way if using SQLite (the default).
# If DATABASE_URL points at Postgres, this script's DB copy step is a
# no-op and you should use your Postgres host's own backup mechanism
# (pg_dump on a schedule, or your host's managed-backup feature) instead —
# the uploads/ backup here is still relevant either way.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
INSTANCE_DIR="$(dirname "$PROJECT_DIR")/jtead-instance"
BACKUP_DIR="${BACKUP_DIR:-$HOME/jtead-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

if [ ! -d "$INSTANCE_DIR" ]; then
  echo "Instance directory not found at $INSTANCE_DIR — nothing to back up." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

ARCHIVE_PATH="$BACKUP_DIR/jtead-backup-$TIMESTAMP.tar.gz"
tar -czf "$ARCHIVE_PATH" -C "$(dirname "$INSTANCE_DIR")" "$(basename "$INSTANCE_DIR")"
echo "Backed up $INSTANCE_DIR -> $ARCHIVE_PATH"

find "$BACKUP_DIR" -name 'jtead-backup-*.tar.gz' -mtime "+$RETENTION_DAYS" -print -delete
