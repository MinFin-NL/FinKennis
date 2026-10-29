# Zet de nieuwste dump van de backup-share terug in een lege database.
#
# De postgres-image source't dit script uit /docker-entrypoint-initdb.d, en dat
# gebeurt alleen direct na initdb: op een lege datadirectory. De server luistert
# dan nog alleen op de lokale socket, dus geen client kan tussendoor verbinden.
#
# Geen 'exit' hier: het script draait in de shell van docker-entrypoint.sh. Die
# draait met 'set -e', dus een mislukte restore stopt de container. Dat is de
# bedoeling: een database die luid niet start is beter dan een die stil leeg
# begint, waarna de volgende backup de goede dumps wegroteert.

pg_restore_latest() {
  local dir="${PG_BACKUP_DIR:-/backup}" newest
  newest=$(find "$dir" -maxdepth 1 -name '*.dump' 2>/dev/null | sort | tail -n 1 || true)
  if [[ -z "$newest" ]]; then
    echo "[pg-restore] geen dump in $dir; de database begint leeg"
    return 0
  fi
  echo "[pg-restore] $newest terugzetten in $POSTGRES_DB"
  pg_restore --exit-on-error --no-owner --no-privileges \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" "$newest"
  echo "[pg-restore] klaar"
}

pg_restore_latest
