#!/usr/bin/env bash
#
# Dumpt de database naar de backup-share. Draait als Container Apps-job: elke
# nacht, en vanuit de pipeline vlak voor elke deploy. pg-restore.sh zet de
# nieuwste dump terug zodra Postgres met een lege schijf start.
#
# Op de share staan alleen de laatste KEEP dumps (<stempel>.dump); oudere zijn
# niet meer interessant.
#
# Verbinding via de standaard libpq-variabelen: PGHOST, PGPORT, PGUSER,
# PGPASSWORD, PGDATABASE.
set -euo pipefail

dir="${PG_BACKUP_DIR:-/backup}"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
partial="$dir/.$stamp.partial"
trap 'rm -f "$partial"' EXIT

# Eerst naar een tijdelijke naam: een afgebroken dump mag nooit de nieuwste
# lijken, want die wordt bij een herstart teruggezet.
pg_dump --format=custom --file="$partial"
mv "$partial" "$dir/$stamp.dump"

# Opruimen pas na een geslaagde dump: zo blijven er dumps over, ook als de job
# een tijd faalt.
find "$dir" -maxdepth 1 -name '*.dump' | sort -r | tail -n +"$((${KEEP:-3} + 1))" | xargs -r rm -f --

echo "[pg-backup] $PGDATABASE gedumpt naar $stamp.dump ($(du -h "$dir/$stamp.dump" | cut -f1))"
