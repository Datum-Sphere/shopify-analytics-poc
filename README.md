# Shopify Analytics POC

Free, Dockerized consulting demonstration. This commit implements the environment foundation only: no Shopify requests, sales transformations, scheduling, or dashboard business logic.

## Architecture

Planned flow: Shopify Admin GraphQL API (2026-10) → Python ingestion → PostgreSQL 16 → dbt Core + dbt-postgres → Streamlit + Plotly.

- `ingestion/`: reserved Shopify API package.
- `pipeline/`: idle application service and authenticated database health check; future orchestration entry point.
- `dbt/`: environment-based connection profile, staging/marts directories, and a constant smoke model with three tests.
- `dashboard/`: environment-ready Streamlit page and dedicated Dockerfile.
- `tests/`: automated foundation smoke checks.
- `Dockerfile`, `compose.yaml`: Python 3.12 services and persistent PostgreSQL.

## Prerequisites

Docker Desktop running Linux containers with Docker Compose v2+ (tested with Compose v5). On Windows enable the WSL2 backend. Git is needed to clone. No host Python, PostgreSQL, dbt, paid services, or Shopify credentials are required for this foundation. Internet access is needed for initial image/package downloads. Docker Desktop licensing depends on your organization.

## Start (PowerShell)

```powershell
git clone https://github.com/Datum-Sphere/shopify-analytics-poc.git
cd shopify-analytics-poc
Copy-Item .env.example .env
# Edit .env and replace POSTGRES_PASSWORD with a long random password.
# Shopify placeholders can remain unchanged until ingestion is implemented.
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Open http://localhost:8501. The page displays **Shopify Analytics POC — Environment Ready.** Containers may take several minutes to build. Wait for all three services to become healthy:

```powershell
docker compose up -d --wait --wait-timeout 180
docker compose exec app dbt debug --project-dir dbt --profiles-dir dbt
docker compose exec app dbt build --project-dir dbt --profiles-dir dbt
docker compose exec app python -m unittest discover -s tests -v
(Invoke-WebRequest http://localhost:8501/_stcore/health).StatusCode
```

`dbt debug` must report a successful connection. `dbt build` creates `analytics.environment_ready` and runs not-null, unique, and accepted-value tests. This is a connectivity fixture, not a sales model. dbt uses the official [Postgres profile format](https://docs.getdbt.com/docs/local/connect-data-platform/postgres-setup) and [secret environment variables](https://docs.getdbt.com/reference/dbt-jinja-functions/env_var).

## Security and operations

Only `127.0.0.1:8501` is published to the Windows host; PostgreSQL stays on the Compose network. Both Python containers run as non-root. The dashboard receives no credentials and provides no shell or subprocess controls. Shopify placeholders are not passed to any service yet. `.env`, secrets, caches, and dbt output are excluded from Git and Docker build contexts. Never commit credentials. Database credentials are injected at runtime; local Docker administrators can inspect container environment variables. This is a local POC, not production hardening.

PostgreSQL uses the named `postgres_data` volume. `docker compose down` stops the stack and preserves data. `docker compose down -v` **deletes all database data**. Changing database credentials in `.env` does not change an existing database volume's credentials; retain the existing credentials or intentionally reinitialize disposable data. Application code is baked into images: rebuild after edits. dbt artifacts live in the app container and can be inspected with `docker compose exec app dbt ...` or copied with `docker compose cp`.

Troubleshoot with `docker compose ps` and `docker compose logs --tail 100`. Do not publish logs or resolved `docker compose config` output containing credentials. Use `config --quiet` for validation.

## Validation

See [VALIDATION.md](VALIDATION.md) for checks actually executed in the implementation environment. Direct dependencies are pinned in requirements files; transitive dependencies and base image tags can change, so this is not a byte-for-byte locked supply chain.

## Next step

Implement a read-only Shopify GraphQL client with environment-based credentials, pagination, rate-limit handling, and idempotent raw-order persistence. Keep API credentials out of Streamlit.
