#!/usr/bin/env sh
set -eu

umask 077
cd "$(dirname "$0")"

compose() {
  docker compose --project-name motioncare-prod --env-file .env -f docker-compose.prod.yml "$@"
}

mkdir -p backups data/media data/postgres data/redis data/static

if compose ps --status running --services 2>/dev/null | grep -qx postgres; then
  backup_path="backups/motioncare-$(date +%Y%m%d-%H%M%S).sql.gz"
  compose exec -T postgres sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    | gzip > "$backup_path"
  printf 'Database backup: %s\n' "$backup_path"
fi

compose --profile tools pull
compose --profile tools run --rm migrate
compose up -d --wait --wait-timeout 240
compose ps
