#!/bin/sh
set -eu

mkdir -p /app/data /app/staticfiles

if [ "${SKIP_STARTUP_MIGRATE:-0}" = "1" ]; then
  echo "Skipping startup migrations because SKIP_STARTUP_MIGRATE=1"
else
  python manage.py migrate --noinput
fi

python manage.py collectstatic --noinput

exec "$@"
