# Local development runbook

## Container path

```bash
cp .env.example .env
docker compose up --build
```

The API is available at `http://localhost:8000/docs`. Liveness is `/health/live`; readiness verifies PostgreSQL at `/health/ready`.

## Native Python path

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
docker compose up -d postgres redis
alembic upgrade head
pytest -q
uvicorn automotive_quality.api.main:app --reload
```

## Database reset

For a disposable local environment only:

```bash
docker compose down -v
docker compose up -d postgres redis
alembic upgrade head
```

