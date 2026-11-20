#!/usr/bin/env bash
# Nightly Postgres dump. Cron on the VM:  0 3 * * * /opt/unpack/backup.sh >> /opt/unpack/backups/backup.log 2>&1
# Set BACKUP_BUCKET (e.g. gs://my-unpack-backups) to also copy the dump off the VM.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p backups
file="backups/unpack-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U unpack -d unpack | gzip > "$file"
find backups -name 'unpack-*.sql.gz' -mtime +7 -delete
if [ -n "${BACKUP_BUCKET:-}" ]; then gcloud storage cp "$file" "$BACKUP_BUCKET/"; fi
echo "wrote $file"
