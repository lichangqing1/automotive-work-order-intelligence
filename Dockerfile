FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[ai]'

COPY alembic.ini ./
COPY migrations ./migrations
COPY configs ./configs
COPY prompts ./prompts
COPY sql ./sql

EXPOSE 8000
CMD ["uvicorn", "automotive_quality.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
