#!/bin/sh
# Proves the last backup can be restored: it restores it into a separate,
# throw-away database (eka_restore_check), compares a few counts with the
# live database and removes only that throw-away database. The live database
# "eka" is only read.
#
# Run from infrastructure/prod:
#   sh restore-check.sh
set -eu
cd "$(dirname "$0")"

DIR="${EKA_BACKUP_DIR:-$HOME/eka-backups}"
CHECK_DB=eka_restore_check

DUMP=$(ls -1t "$DIR"/eka-*.dump 2>/dev/null | head -n 1 || true)
FILES=$(ls -1t "$DIR"/eka-files-*.tar.gz 2>/dev/null | head -n 1 || true)
if [ -z "$DUMP" ] || [ -z "$FILES" ]; then
  echo "PAROU: nao ha backups em $DIR; corre primeiro sh backup.sh."
  exit 1
fi
echo "A verificar $(basename "$DUMP") e $(basename "$FILES")"

sql() {
  docker compose exec -T postgres psql -U eka_admin -v ON_ERROR_STOP=1 -At "$@"
}

sql -d postgres -c "SET client_min_messages = warning" -c "DROP DATABASE IF EXISTS $CHECK_DB;" > /dev/null
sql -d postgres -c "CREATE DATABASE $CHECK_DB;" > /dev/null
if ! docker compose exec -T postgres pg_restore -U eka_admin -d "$CHECK_DB" --exit-on-error < "$DUMP"; then
  sql -d postgres -c "SET client_min_messages = warning" -c "DROP DATABASE IF EXISTS $CHECK_DB;" > /dev/null
  echo "FALHOU: o backup nao restaurou."
  exit 1
fi

COUNTS="SELECT (SELECT count(*) FROM organizations) || ' organizacoes, ' || (SELECT count(*) FROM documents) || ' documentos, ' || (SELECT count(*) FROM document_chunks) || ' passagens, ' || (SELECT count(*) FROM chunk_embeddings) || ' vetores'"
RESTORED=$(sql -d "$CHECK_DB" -c "$COUNTS")
LIVE=$(sql -d eka -c "$COUNTS")
sql -d postgres -c "DROP DATABASE $CHECK_DB;" > /dev/null

ENTRIES=$(tar -tzf "$FILES" | wc -l)
echo "Restaurado: $RESTORED"
echo "Agora:      $LIVE"
echo "Ficheiros no arquivo: $ENTRIES entradas"
echo "OK: o backup restaura (a base de teste ja foi apagada)."
