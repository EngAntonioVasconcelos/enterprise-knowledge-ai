#!/bin/sh
# Daily backup of the demo: the database and the uploaded files.
#
# Two copies: one here (~/eka-backups, the last 7 days, for a quick restore
# after a mistake) and one in Oracle Object Storage (kept 30 days by the
# bucket's lifecycle rule), so losing the server does not lose the data.
# The upload uses a pre-authenticated request that may only write: from this
# server nobody can read or delete the copies in the bucket. Its URL lives
# in backup.par (chmod 600, never in Git) and is never printed. After a full
# backup it calls the monitor's heartbeat (backup.heartbeat, same rules).
#
# Not copied, because they come back on their own: the models (downloaded
# again) and the certificate (Caddy asks for a new one). .env stays only on
# this server.
#
# Run from infrastructure/prod, by hand or from cron:
#   sh backup.sh
set -eu
cd "$(dirname "$0")"

DIR="${EKA_BACKUP_DIR:-$HOME/eka-backups}"
KEEP_DAYS=7
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DB="$DIR/eka-$STAMP.dump"
FILES="$DIR/eka-files-$STAMP.tar.gz"

umask 077
mkdir -p "$DIR"
trap 'rm -f "$DB.part" "$FILES.part"' EXIT

# Written to .part first: a copy cut short never looks like a good one.
docker compose exec -T postgres pg_dump -U eka_admin -d eka --format=custom > "$DB.part"
docker compose exec -T api tar -czf - -C /app/backend/var/storage . > "$FILES.part"
if [ ! -s "$DB.part" ] || [ ! -s "$FILES.part" ]; then
  echo "FALHOU: a copia saiu vazia; nada foi enviado."
  exit 1
fi
mv "$DB.part" "$DB"
mv "$FILES.part" "$FILES"
echo "Copia local: $(basename "$DB") ($(du -h "$DB" | cut -f1)), $(basename "$FILES") ($(du -h "$FILES" | cut -f1))"

if [ -s backup.par ]; then
  PAR=$(cat backup.par)
  for file in "$DB" "$FILES"; do
    curl -fsS --retry 3 --upload-file "$file" "$PAR$(basename "$file")"
  done
  echo "Enviado para o Object Storage."
  # Tell the uptime monitor the backup worked. It warns by e-mail when
  # this does not arrive in time; the URL lives in backup.heartbeat.
  if [ -s backup.heartbeat ]; then
    curl -fsS --retry 3 -o /dev/null "$(cat backup.heartbeat)" && echo "Monitor avisado."
  fi
else
  echo "AVISO: falta backup.par; a copia ficou so neste servidor."
fi

# Only this script's own files, only in its folder, only past the 7 days.
find "$DIR" -maxdepth 1 -type f -name 'eka-*' -mtime +"$((KEEP_DAYS - 1))" -delete
echo "OK: backup $STAMP"
