# Salam Offer Docker

This project runs as two Django processes over one PostgreSQL database:

```text
browser -> web/gunicorn -> PostgreSQL <- process_analysis_queue worker
```

The web process only queues analysis jobs and shows status. The worker claims pending jobs from PostgreSQL and performs the expensive Basalam search/detail analysis.

## Environment

Create a real `.env` from the example:

```bash
cp .env.example .env
```

Then set at least:

```env
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=replace-this-with-a-long-random-secret
DJANGO_ALLOWED_HOSTS=salam-offer.titanapp.dev,your-domain.com,127.0.0.1,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://salam-offer.titanapp.dev,https://your-domain.com
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB_NAME
DATABASE_SSL_REQUIRE=0
```

`DATABASE_URL` is required for Docker Compose. SQLite is only for direct local Django development with `DJANGO_DEBUG=1`; Compose does not use SQLite.

## Services

`docker-compose.yml` defines:

- `migrate`: runs Django migrations once, then exits.
- `web`: starts Gunicorn and serves the dashboard/API.
- `worker`: runs `python manage.py process_analysis_queue --loop`.

Web and worker use the same image and the same `DATABASE_URL`.

## Start

```bash
docker compose up -d --build
```

The app listens on:

```text
http://YOUR_HOST:8000/
```

## Logs

```bash
docker compose logs -f migrate
docker compose logs -f web
docker compose logs -f worker
```

## Stop

```bash
docker compose down
```

## Smoke test

1. Start `web` without `worker`, or stop the worker temporarily:

   ```bash
   docker compose stop worker
   ```

2. Queue one product analysis from the dashboard. It should remain `analysis_pending`.
3. Start the worker:

   ```bash
   docker compose up -d worker
   ```

4. Watch worker logs and confirm the snapshot moves through `analysis_running` to a terminal status.

## Operational notes

- Do not run web and worker against different databases.
- Do not use the removed web-processing endpoints (`/api/analysis/process-next/`, `/api/analysis/process-batch/`). Analysis belongs in the worker.
- The dashboard's stop button only stops browser polling. It does not cancel worker jobs.
- `migrate` owns schema migrations in Compose. Permanent `web` and `worker` services run with startup migrations skipped.
- `worker` also skips `collectstatic` because it does not serve HTTP/static files.
- The real `.env` is ignored by git and must not be committed.
