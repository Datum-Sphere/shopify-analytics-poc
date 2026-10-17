# Foundation validation

Executed on October 16, 2026 (America/Vancouver), on Windows with Docker Desktop Linux containers, Docker Engine 29.8.1 and Compose v5.5.1. Containers use Python 3.12, PostgreSQL 16, dbt Core 1.10.11 and dbt-postgres 1.9.1.

| Check | Result |
| --- | --- |
| `docker compose config --quiet` | Passed |
| `docker compose up --build -d` | Passed; all three services started |
| `docker compose ps` | PostgreSQL, app and Streamlit healthy |
| `docker compose exec -T app dbt debug --project-dir dbt --profiles-dir dbt` | All checks passed, including authenticated PostgreSQL connection |
| `docker compose exec -T app dbt build --project-dir dbt --profiles-dir dbt` | One view and three data tests passed |
| `docker compose exec -T app python -m unittest discover -s tests -v` | Three tests passed: page rendering, database probe and Compose security boundaries |
| `python -m compileall -q ingestion pipeline dashboard tests` | Passed on host Python 3.12.10 |
| `docker compose exec -T app python -m pip check` | No broken requirements |
| `docker compose exec -T streamlit python -m pip check` | No broken requirements |
| Host HTTP GET `http://localhost:8501` | HTTP 200 |
| Host HTTP GET `http://localhost:8501/_stcore/health` | HTTP 200, `ok` |
| App image runtime and context checks | Non-root; `/app/.env` and `/app/.git` absent |
| Git ignore and credential checks | `.env` ignored; only `.env.example` is intended for version control |

Initial dbt diagnostics exposed read-only Windows build-context directories and missing Git in the slim image. Both were fixed in the Dockerfile and dbt validation rerun. A generic-test deprecation was corrected by nesting accepted-value options under `arguments`.

Docker commands initially required elevated access to the Docker Desktop named pipe; all required runtime checks were subsequently executed. No requested validation remains unexecuted. Streamlit AppTest emits a harmless missing ScriptRunContext warning when initialized outside a running server.

Scope limits: no Shopify API call, authentication flow, ingestion, sales model, scheduler, or dashboard business logic was tested or implemented. The UI was tested with Streamlit AppTest and host HTTP requests, not a graphical browser. Direct Python dependencies are pinned; transitive packages and base images are not fully locked. Containers and the local ignored `.env` are left available for demonstration.
