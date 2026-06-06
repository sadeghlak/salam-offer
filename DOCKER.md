# Salam Offer Docker

## Local/host setup

Copy env example and set your real host/domain:

```bash
cp .env.example .env
```

Edit `.env`:

```env
DJANGO_DEBUG=1
DJANGO_SECRET_KEY=replace-this-with-a-long-random-secret
DJANGO_ALLOWED_HOSTS=your-domain.com,your-server-ip,127.0.0.1,localhost
SQLITE_PATH=/app/data/db.sqlite3
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

- SQLite is persisted in the `salam_offer_data` Docker volume.
- Static files are collected on container startup.
- For production, set `DJANGO_DEBUG=0`, a strong `DJANGO_SECRET_KEY`, and exact `DJANGO_ALLOWED_HOSTS` values.
