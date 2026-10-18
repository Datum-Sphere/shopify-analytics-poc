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


## Phase 4A: read-only Streamlit financial dashboard — October 18, 2026

The placeholder page is replaced by a financial dashboard. Financial formula/grain/date/currency contracts remain unchanged. No pipeline execution backend or remote exposure was added; Run Pipeline & Refresh is visible and disabled for Phase 4B.

### Executed automated checks

| Check | Observed result |
| --- | --- |
| `docker compose config --quiet` | Passed with explicit localhost bindings and separate dashboard credential |
| `docker compose up --build -d` | Both images built; PostgreSQL, app and Streamlit healthy |
| `docker compose exec -T app dbt build --project-dir dbt --profiles-dir dbt` | PASS=108, WARN=0, ERROR=0, SKIP=0: 16 views, 91 data tests, one seed |
| `docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_DASHBOARD_DB_TESTS=1 app python -m unittest discover -s tests -v` | 43 passed; no skips |
| `python -m compileall -q dashboard pipeline tests` | Passed |
| `docker compose exec -T streamlit python -m pip check` | No broken requirements |
| Host HTTP GET `http://localhost:8501` | HTTP 200 |
| Host GET `http://localhost:8501/_stcore/health` | `ok` |

The original 28 Python tests remain included; the placeholder-title/security expectations were updated for the intentionally changed UI and dedicated database environment. Fifteen dashboard tests cover query parameters, dataset/currency/date isolation, live order data, synthetic totals, later negative sales, empty data, null/unsupported values, current product aggregation, custom/unlinked products, duplicate titles, decimal display precision, UI rendering, disabled controls, safe errors and database permissions.

Initial checks caught a missing import in the bootstrap helper and a context-manager mock in the new tests. Both were corrected before the final passing run. Streamlit AppTest emits its usual missing ScriptRunContext warning outside a normal browser session; the tests report no rendering exceptions.

### Database and production-image evidence

The local ignored `.env` was extended with a generated, separate dashboard password; existing Shopify/database secrets were preserved and not printed. App startup provisions `shopify_dashboard` on the existing database volume. Explicit model grants survive dbt rebuilds. The role has SELECT on exactly five analytics views: mart_daily_sales, fct_sales_events, dim_product, dashboard_ingestion_status and dashboard_financial_issues.

Real PostgreSQL tests confirmed the role is not superuser/createdb/createrole/replication/bypassrls, uses a default read-only transaction, has no extra analytic-view grants, and cannot select raw payloads, select ingestion errors, update raw data, create public or temporary tables, or SET ROLE to the privileged application user. These write/role attempts were denied even after disabling the convenience read-only session setting, proving SQL privilege enforcement. PUBLIC temporary-table access and public-schema CREATE are revoked by the local bootstrap.

Runtime checks inside the Streamlit container confirmed no SHOPIFY_*, POSTGRES_* or DBT_* variables and no `/app/.env`. Only the dedicated DASHBOARD_DB_* connection values are injected. No Docker socket is mounted. The committed host mappings remain 127.0.0.1:5432 for DataGrip and 127.0.0.1:8501 for Streamlit; the app has no host port. No broader laptop/network exposure was introduced.

The actual production Streamlit image was also exercised with AppTest and its real SELECT-only connection, without query mocks. It rendered three Plotly charts and the following metrics, then changed dataset/date controls successfully without exceptions:

| Selection | Gross | Discounts | Returns | Net |
| --- | ---: | ---: | ---: | ---: |
| Live CAD, current development-store data | 200 | 0 | 0 | 200 |
| Synthetic CAD, full fixture range October 1–6 | 340 | 25 | 180 | 135 |
| Synthetic CAD, October 4 only | 0 | 0 | 90 | -90 |
| Synthetic CAD, October 3 only | unavailable | unavailable | unavailable | unavailable |

The empty date renders dashes and no charts, rather than invented zero amounts. A separate source/fact query explicitly scoped to real order #1001 confirmed CAD 200 gross/net and zero discounts/returns. These checks use existing ingested Shopify data, not a newly executed Shopify request or a Shopify Analytics report reconciliation. Synthetic USD 7 was separately checked; it never entered CAD or live totals.

### Unsupported-data and product checks

Isolated synthetic test stores were loaded, modified only in PostgreSQL, and cleaned up afterward. Tests verified that:

- Removing a line's catalog product reference retains a Custom / unlinked product bucket; all product totals still sum to the selected mart net 135.
- A later product UPDATE produces an unsupported selection and withholds every KPI/chart; another valid date or currency remains independent.
- A non-product AdjustmentSale, which is absent from merchandise mart totals, still blocks the matching date through safe quality metadata.
- Missing financial-extraction metadata with unknown event date blocks the selected source conservatively, even on an otherwise valid earlier day.
- Query failures produce fixed, credential-free messages instead of driver exception text; partial NULL sums are never displayed as complete totals.

The dashboard quality view additionally flags missing test/timezone/currency metadata and missing event/line parents. It is a coverage safeguard, not proof that every possible financial test was just run. Safe freshness metadata is only the latest successful ingestion timestamp per dataset/store, not build success or a timestamp restricted to the selected report period.

### Limitations and checks not performed

No Shopify Analytics export/ShopifyQL reconciliation, fresh ingestion, pipeline-trigger backend, authentication/hosting layer, Cloudflare or other remote setup was implemented or tested in this slice. Existing live-return/discount limitations from the financial contract still apply. Product labels are current catalog/fallback labels, not historical dimensions. The page performs uncached SELECTs in a read-only repeatable-read snapshot and is intended for small demonstration datasets.

Rendering was validated with mocked and real-database Streamlit AppTest sessions plus host HTTP checks. A graphical headless-browser screenshot attempt was blocked by execution policy; no browser screenshot or pixel-level visual review is claimed. All required Python/dbt/Docker/security checks ran successfully.


## Phase 4B: authenticated pipeline and validated publication — October 18, 2026

This supersedes Phase 4A's disabled-control and direct-analytics-access descriptions. Existing financial formulas, source selection and Shopify permissions remain unchanged. No remote exposure was configured.

### Final executed checks

| Command/check | Observed result |
| --- | --- |
| `docker compose config --quiet` | Passed; only localhost PostgreSQL/Streamlit host bindings; no backend port |
| `docker compose up --build -d --wait --wait-timeout 120` | Both images built; all three services healthy on the existing persistent volume |
| `docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_DASHBOARD_DB_TESTS=1 -e RUN_PIPELINE_DB_TESTS=1 app python -m unittest discover -s tests -v` | **59 passed, no skips**, final run 36.259 seconds |
| `docker compose exec -T app dbt build --project-dir dbt --profiles-dir dbt` | **PASS=108, WARN=0, ERROR=0, SKIP=0**: 16 views, 91 tests, one seed |
| `docker compose exec -T app python -m compileall -q dashboard ingestion pipeline tests` | Passed |
| `docker compose exec -T app python -m pip check` and equivalent in Streamlit | Both reported no broken requirements |
| Host GET `http://localhost:8501` / `/_stcore/health` | HTTP **200** / **ok** |
| Final `docker compose exec -T app python -m pipeline.run` | **Succeeded**, exit 0, run `6bfff21c-1781-481a-b3e7-8a08357636fe`, 14.300973 seconds, six timestamped stage transitions |

The 43 Phase 4A tests remain included, with expectations updated for the enabled control and publication permissions. Eleven new mocked workflow/HTTP/UI tests and five real PostgreSQL/dbt tests cover stage order, each stage's failure, no-shell fixed dbt invocation, secret separation, 401 authentication, empty-body/path restrictions, safe errors, status/button states, success-only cache invalidation, session locks across connections/processes, CLI busy exit 2, concurrent admission, crash/orphan recovery, rollback and repeat publication. No Shopify requests occur in the Python unit/database suite. DB tests intentionally fail isolated candidate builds and clean their own source records; controlled run rows are retained with test origin.

### Verified live button workflow

Executed inside the actual Streamlit image using its SELECT-only login and **real internal HTTP**, without mocks:

```powershell
Get-Content tests/e2e_pipeline.py -Raw | docker compose exec -T streamlit python -
```

The actual AppTest button initiated live Shopify ingestion, full dbt build/tests and publication twice. Representative successful button runs: `7db5999d-e6c4-4c53-a64f-041bc4c031fe` and `52279690-7a63-44f6-ba4e-47b252243a67`. UI showed Running with a disabled active-run button, then Succeeded; the session publication generation changed and financial cards reloaded. A competing real HTTP trigger returned already_running/409. Unauthenticated real POST /runs and GET /status returned **401**. The initial and repeated selected metrics were identical:

| Selection | Gross | Discounts | Merchandise returns | Net |
| --- | ---: | ---: | ---: | ---: |
| Live CAD, order #1001 | 200 | 0 | 0 | 200 |
| Synthetic CAD, October 1–6 | 340 | 25 | 180 | 135 |
| Synthetic CAD, October 4 | 0 | 0 | 90 | -90 |

A separate source/fact query explicitly scoped to live #1001 confirmed CAD 200 gross/net. Unique source counts captured before and after the first two live button runs were identical for both stores. The final live counts remain **17 products, 26 variants, one order, one line, one payment transaction, one agreement, two sales, zero refunds/refund lines**: 49 unique raw records. Canonical synthetic counts remain 32 records. Audit counts increase by design; financial amounts and unique source counts do not inflate. All temporary validation stores were confirmed removed.

### Real failure and publication consistency evidence

Prepared an isolated synthetic `phase4b-failure-check.invalid` store using the existing fixtures and changed product actions to unsupported UPDATE. Then executed the same real button check with `python - --expect-failure`. Run `29991308-c3b3-4269-81c7-084fbb924f24` completed ingestion, **failed the real dbt stage**, and appeared as **Failed** with a sanitized error in the actual Streamlit page. The prior publication UUID and all displayed live/synthetic amounts stayed unchanged; no successful-refresh indicator was emitted. The test source records/audit were removed using the shared lock, and successful real button/CLI runs followed.

The database suite separately compares **every row in all five published outputs plus publication metadata** before/after a real failed dbt build. It also injects a publication write failure after DELETE and confirms transaction rollback preserves every published row. Repeated successful publication does not append metrics. A long-lived SELECT-only repeatable-read reader keeps the preceding publication ID and can first read nonempty mart rows after a new publication commits, verifying retained row versions rather than TRUNCATE behavior.

This is **atomic financial publication**, not a transaction spanning Shopify ingestion and dbt. Raw ingestion commits and audit history survive a later failure; candidate analytics views can change or fail while the dashboard keeps the previous publication. The supported pipeline/ingestion/fixture CLIs coordinate through one session advisory lock. Direct privileged SQL or manual dbt changes bypass that coordination and must not run concurrently. The tests do not establish consistency against bypassing administrators or a changing Shopify API snapshot.

### Security evidence

- Generated a new independent trigger token only in ignored local `.env`; preserved existing Shopify/database credentials and withheld all values.
- Dedicated dashboard role: SELECT on exactly six reporting tables, no analytics/raw/operations access or write/schema/temporary-table/role-switch privileges. Real denied-write tests disable the convenience read-only setting to prove ACL enforcement. A final check after dbt rebuild confirmed no grants outside reporting.
- Runtime Streamlit environment contains no SHOPIFY_*, POSTGRES_* or DBT_* settings and no `/app/.env`. Only its reader credentials and independent backend token are injected. XSRF and CORS protection remain enabled. No Docker socket or backend host port was added.
- Resolved Compose was captured privately for credential-value scanning, never printed. Repository files were checked against configured actual secret values; no matches. `.env` remains ignored. PostgreSQL and Streamlit retain exact 127.0.0.1 bindings.
- Backend errors/status are fixed safe messages, stage metadata and UUIDs. HTTP logs omit request paths/headers. dbt runs with fixed argv, shell disabled, a 900-second timeout, temporary private artifacts, discarded console output and no Shopify/trigger-token environment.

### Limits and evidence boundary

The bearer token authenticates the Streamlit service, not individual users. Anyone able to use the local dashboard can trigger the predefined operation; no individual login, remote protection, TLS or internet exposure was implemented. Docker/database administrators remain trusted. A new database requires explicit fixture loading before the default full dbt assertions and an accessible #1001 for this demo contract. Fresh-volume destructive reinitialization was not performed; existing-volume migration/startup was verified.

Live refund/discount/edit scenarios remain unavailable in the development store. **No Shopify Analytics report/ShopifyQL reconciliation was performed.** Synthetic expected values are fixture-validated; original order data and real workflow execution are API-validated. Full-copy publication suits this small POC; historical sync, deletion reconciliation, advanced accounting and automatic snapshot-schema migrations remain deferred. The workflow is not a durable job queue or distributed fencing system; process loss becomes a failed audit and requires an explicit retry. Losing the advisory-lock connection cannot instantaneously cancel an already running dbt child; inspect active processes before retrying after such a failure. This fault was not induced against the live Docker stack. Raw ingestion audits can still show running after abrupt termination, independently of recovered pipeline status.

Rendering/click/status behavior was verified with Streamlit AppTest and HTTP checks, not a graphical browser. No graphical screenshot attempt was repeated after the Phase 4A execution-policy block. Non-fatal Streamlit missing-ScriptRunContext and pandas/NumPy timedelta deprecation warnings occurred in unit tests; all checks passed without rendering exceptions. No required Phase 4B validation was omitted because tooling was unavailable.
