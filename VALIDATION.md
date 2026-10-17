# Validation history

## Foundation

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


## Phase 2: read-only ingestion

Executed October 16, 2026 (America/Vancouver). This section supersedes the foundation-only scope limitations above.

### Mocked tests and real database tests

`docker compose exec -T -e RUN_DB_TESTS=1 app python -m unittest discover -s tests -v`: **22 passed** (3 foundation, 17 mocked/unit ingestion, 2 real PostgreSQL tests using mocked Shopify extraction). No live Shopify calls occur in these tests. They cover token caching/expiry/401 refresh, invalid authentication, timeouts, HTTP retry/Retry-After, GraphQL throttling/errors/version fallback, mutation rejection, root/nested cursor pagination, repeated-cursor detection, exact-order verification, duplicate ingestion, parameterized JSONB upserts, payload updates and atomic rollback with a retained failed audit. PostgreSQL test fixtures are isolated by temporary store names and removed afterward.

### Verified live development-store results

Authenticated through the client-credentials grant against `demo-analytics-poc.myshopify.com` using the existing installed app credentials and API version `2026-10`. No extra permissions were requested. Ran twice:

```powershell
docker compose exec -T app python -m ingestion.run --verify-order '#1001'
```

| Entity | First successful run (9) | Second successful run (13) |
| --- | ---: | ---: |
| Products | 17 | 17 |
| Variants | 26 | 26 |
| Orders | 1 | 1 |
| Order line items | 1 | 1 |
| Order payment transactions | 1 | 1 |
| Total unique source records | 46 | 46 |

Both runs succeeded, with identical processed and unique-record counts. Run IDs have gaps because tests exercise audit inserts and clean up their own fixtures. The retained audit intentionally grows once per ingestion; source IDs remain unique. A direct database check confirmed order `#1001`, one line item, one payment transaction, financial-status and discount-total fields in persisted JSON. **Shopify reports `test=false` for #1001**; it is a demonstration order, not flagged by Shopify as a test-payment order. Verification reports the actual flag and does not modify the store.

The initial local store hostname differed from the requested store and returned HTTP 301. Redirects were refused, with no credentials forwarded. Only the non-secret hostname in the ignored local `.env` was updated; secret values were preserved. An early strict assertion that the demonstration order had `test=true` was replaced by accurate flag reporting. These diagnostic failures remain as failed audit entries and persisted no source rows.

### Foundation/security regression checks

- `docker compose config --quiet` and `docker compose up --build -d`: passed; all services healthy.
- `dbt debug`: all checks passed; `dbt build`: one view plus three data tests, PASS=4, WARN=0, ERROR=0.
- App `pip check`: no broken requirements; Streamlit health endpoint on the Windows host: `ok`.
- Runtime inspection confirmed Streamlit receives no `SHOPIFY_*` variables. Only localhost:8501 is published; PostgreSQL remains internal.
- Recursively checked all 46 persisted JSON records for excluded customer/credential/payment-receipt field names and local secret values: passed, without printing payloads or secrets.
- The existing Streamlit title test remains unchanged in behavior; a Windows text-encoding issue during editing was corrected and the full suite rerun successfully.

### Remaining limits

Live store size exercises fewer than a page of roots; multipage root/nested behavior, retries, throttling, token expiry and failure sanitization are verified with mocks. No forced live expiry, throttling, or provider failure was induced. Read-orders visibility is normally limited to 60 days; no historical permission was requested. No incremental sync, deletion reconciliation, concurrent-run coordination, scheduler, inventory/customer extraction, dbt financial models, or dashboard metrics are implemented. Full JSON means the selected non-customer GraphQL fields, not a complete dump of every Shopify field. A forcibly terminated CLI can leave a running audit. No requested validation was skipped due to unavailable tooling.
