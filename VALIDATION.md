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


## Phase 3: financial ingestion and models

Executed October 16, 2026 (America/Vancouver), against Admin GraphQL 2026-10. This supersedes earlier financial-model scope limits.

### Automated validation

- `docker compose exec -T -e RUN_DB_TESTS=1 app python -m unittest discover -s tests -v`: **28 passed**, including the unchanged original 22 tests and six new financial extraction/fixture tests. The tests use mocked API data and real PostgreSQL where enabled; they are not Shopify report reconciliation.
- `docker compose exec -T app dbt build --project-dir dbt --profiles-dir dbt`: **PASS=100, WARN=0, ERROR=0, SKIP=0**: 14 views, one expected-results seed and 85 data tests. Tests cover unique/non-null keys and money fields, relationships and parent-order consistency, dataset isolation, no join fanout, financial identities, event-to-daily reconciliation, unsupported-event coverage and independent fixture expectations.
- `docker compose config --quiet`, image build/startup, app dependency check and Python compilation: passed. All three containers healthy; host Streamlit health: `ok`. PostgreSQL remains internal in the shared/default configuration. Dashboard receives no Shopify environment variables. App is non-root, and `.env` is absent from its image.
- A separate local edit publishing localhost:5432 temporarily caused the existing security test to fail. The port setting was preserved in ignored `compose.host-db.local.yaml`; shared Compose was restored to its original internal-only default. The final test suite passed. The override is opt-in with `docker compose -f compose.yaml -f compose.host-db.local.yaml up -d postgres`; it is not committed or copied into the app image.

### Verified live API and persistence

Live schema introspection confirmed `SalesAgreement`, `Sale` and `ProductSale`. `SalesAgreementLineItem` is absent. Agreement implementations are not Node-queryable, so ingestion fixes the outer agreement cursor while paginating each agreement's sales. Read-only queries for refund lines and adjustments were accepted using a nonexistent refund ID, confirming query shape but not real refund behavior.

Live ingestion succeeded twice (runs 19 and 21) with identical unique counts: **17 products, 26 variants, one order, one order line, one payment transaction, one agreement, two sale events, zero refunds and zero refund lines**. The sale events are one product and one zero-value shipping event. No extra scopes or store mutations were used.

Order **#1001** was checked separately from fixtures. Its original API line price × quantity is **CAD 200**, allocated discounts **0**, and there are no refunds/reversal events. The financial fact and daily mart yield gross **200**, discounts **0**, returns **0**, net **200**. The UTC agreement timestamp is 2026-10-17 01:18:30, which reports on **2026-10-16** in **America/New_York**. Shopify's `test` flag is false. The result was independently compared to live order-line data, not a report/export.

A snapshot of all source unique counts and every daily mart value was captured before replaying live ingestion and fixture loading. The post-replay snapshot was identical. Audit runs intentionally increase; monetary facts do not append. The PostgreSQL container was recreated during configuration validation without deleting its volume, and the data/models remained available.

An unsupported product `UPDATE` was simulated inside a PostgreSQL transaction: its fact became `is_supported=false`, net_sales became null, and the daily row showed one unsupported event and null net_sales. The transaction was rolled back, leaving live source data unchanged.

### Fixture-validated financial results

Synthetic records use **is_synthetic=true** and reserved store **financial-fixtures.invalid**. They are GraphQL-shaped examples, not captured Shopify responses. Fixtures cover two discounted lines, a separate unpaid/canceled order, test-order exclusion, two later partial reversals of the same original line, a shipping refund, a payments-only refund, midnight timezone conversion and isolated USD amounts.

| Fixture reporting date | Currency | Gross | Discounts | Returns | Net |
| --- | --- | ---: | ---: | ---: | ---: |
| 2026-10-01 | CAD | 250 | 25 | 0 | 225 |
| 2026-10-02 | CAD | 90 | 0 | 0 | 90 |
| 2026-10-04 | CAD | 0 | 0 | 90 | -90 |
| 2026-10-06 | CAD | 0 | 0 | 90 | -90 |
| CAD totals | CAD | **340** | **25** | **180** | **135** |
| 2026-10-02 | USD | 7 | 0 | 0 | 7 |

Each partial reversal is one 100-price unit with a 10 discount: gross return 100, discount reversed 10, net merchandise return 90, and tax 9 kept outside net sales. Payment headers sum to 213, including 18 item tax, 10 shipping and 5 cash-only difference; they are not substituted for returns of 180. Current quantity for the fully reversed original line is zero, yet original sales remain recorded on their original event date. USD is not added to CAD.

### Evidence boundary and limits

**No Shopify Analytics export, ShopifyQL report or admin-report reconciliation was performed.** The development store has no actual discounted, refunded, returned, exchanged or edited orders to verify those paths end to end. Return signs/allocation, tax-bearing examples, later dates and one-to-many joins are fixture-validated; query schema and original-order financials are API-validated. The mixed-currency fixture tests partitioning only, not real-store FX behavior.

Supported merchandise events are ProductSale ORDER/RETURN with zero after-tax discount and consistent shop-money currencies. Nonzero unclassified/adjustment sales, product UPDATE/unknown actions and incomplete monetary data fail coverage. Physical returns, general price-update accounting, total sales, cash-flow reconciliation, complex/tax-inclusive report parity, historical sync, currency/timezone history, deleted-source reconciliation and advanced accounting remain outside scope. See [financial contract](docs/FINANCIALS.md) and README for grains, dates, allocation rules and exact reproduction commands. No required check was omitted because tooling was unavailable.


## DataGrip localhost access — October 18, 2026

At the user's request, the shared `compose.yaml` now publishes PostgreSQL as `127.0.0.1:5432:5432`. This supersedes the earlier internal-only/override-only PostgreSQL configuration; no override is required. The foundation test now checks the exact localhost binding for PostgreSQL and Streamlit, and still rejects an application host port.

Validation executed:

- `docker compose config --quiet`: passed.
- `docker compose up --build -d`: passed; all services healthy and the database volume retained.
- `docker compose exec -T app python -m unittest discover -s tests -p test_foundation.py -v`: three tests passed.
- `docker compose port postgres 5432`: `127.0.0.1:5432`.
- Windows `Test-NetConnection -ComputerName 127.0.0.1 -Port 5432 -InformationLevel Quiet`: `True`.

DataGrip should use host `127.0.0.1`, port `5432`, and database/user/password from the local `.env`. DataGrip's own login was not automated. No credentials were printed or changed.
