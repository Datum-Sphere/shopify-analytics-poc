# Shopify Analytics POC project rules

These rules apply throughout this repository. Follow the current README and preserve the existing architecture.

## Architecture

- Python Shopify Admin GraphQL ingestion -> PostgreSQL raw layer -> dbt Core models/tests -> Streamlit/Plotly dashboard.
- Docker Compose (`compose.yaml`) is the default runtime.
- Keep the MVP simple, modular and reproducible. No Airflow, Kubernetes or paid cloud services.

## Financial correctness

- Treat [docs/FINANCIALS.md](docs/FINANCIALS.md) as the authoritative project financial contract.
- Explicitly define each model's grain, keys, event dates, currencies and metric semantics; prevent duplicate amounts from one-to-many joins.
- Never equate merchandise returns, payment refunds and accounting revenue.
- Never silently calculate unsupported financial adjustments: flag them, fail relevant quality checks and document limitations.
- Keep synthetic and live Shopify datasets separate using the existing dataset flags and scoped keys.
- Preserve ingestion and reporting idempotency; reprocessing must not inflate source counts or metrics.
- Distinguish fixture-validated, live-API-validated and Shopify-report-reconciled results; never claim report reconciliation without evidence.

## Security

- Never commit `.env`, credentials, access tokens or real customer PII. Never print or log secrets; keep tokens in memory.
- Keep PostgreSQL and backend services private. Preserve the authorized localhost-only DataGrip binding `127.0.0.1:5432:5432`; backend services have no public host ports.
- Keep Streamlit bound to localhost (`127.0.0.1:8501`) unless remote access is explicitly requested. Never expose Shopify credentials to Streamlit.
- The dashboard must never execute arbitrary shell commands. Any pipeline-trigger interface must authorize callers and allow only predefined operations, never user-supplied commands.
- Future remote access must use a protected Cloudflare Tunnel, not Tailscale. Do not implement remote exposure until explicitly requested; keep database/backend services private.

## Engineering workflow

- Inspect existing code, tests and documentation before changes. Make focused, incremental changes and preserve existing functionality.
- Add or update tests for new behavior. Run relevant Python, dbt, Docker Compose and security checks using [README.md](README.md); scale validation to the change.
- Never claim a validation passed without executing it. Record limitations, unsupported cases, and checks that could not run with their reasons.
- Keep documentation consistent with implementation and the financial contract.
- Commit and push only after validation succeeds. Never include secrets or unrelated changes.
