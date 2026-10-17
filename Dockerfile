FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DBT_PROFILES_DIR=/app/dbt
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home app && chown app:app /app
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --chown=app:app . .
# Windows build contexts may mark directories read-only; dbt writes logs/target.
RUN chmod -R u+rwX /app
USER app
CMD ["python", "-m", "pipeline.service"]
