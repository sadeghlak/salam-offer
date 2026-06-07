# Salam Offer Docker

## Local/host setup

Copy env example and set your real host/domain:

```bash
cp .env.example .env
```

Edit `.env`:

```env
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=replace-this-with-a-long-random-secret
DJANGO_ALLOWED_HOSTS=salam-offer.titanapp.dev,your-domain.com,your-server-ip,127.0.0.1,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://salam-offer.titanapp.dev,https://your-domain.com
DJANGO_CSRF_COOKIE_SECURE=1
DJANGO_SESSION_COOKIE_SECURE=1

# Production PostgreSQL. Leave empty locally to use SQLite.
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB_NAME
DATABASE_SSL_REQUIRE=0

# SQLite fallback for local/dev when DATABASE_URL is empty.
SQLITE_PATH=/app/data/db.sqlite3

PORT=8000
WEB_CONCURRENCY=2
WEB_TIMEOUT=120
```

## Run with Docker Compose

```bash
docker compose up -d --build
```

The app listens on:

```text
http://YOUR_HOST:8000/
```

n8n URLs should use the public host:

```text
http://YOUR_HOST:8000/api/runs/
http://YOUR_HOST:8000/api/products/ingest/
http://YOUR_HOST:8000/api/analysis/pending/
```

## Logs

```bash
docker compose logs -f web
```

## Stop

```bash
docker compose down
```

## Notes

- If `DATABASE_URL` is set, Django uses PostgreSQL.
- If `DATABASE_URL` is empty, Django falls back to SQLite at `SQLITE_PATH`.
- SQLite is persisted in the `salam_offer_data` Docker volume for compose-based deployments.
- Static files are collected on container startup.
- The container serves Django with Gunicorn and binds to `${PORT:-8000}`.
- For production, set `DJANGO_DEBUG=0`, a strong `DJANGO_SECRET_KEY`, exact `DJANGO_ALLOWED_HOSTS`, and a persistent PostgreSQL `DATABASE_URL`.
