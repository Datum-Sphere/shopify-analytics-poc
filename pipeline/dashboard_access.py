"""Provision a dedicated dashboard login; never grant raw-data or write access."""
import os
from pathlib import Path

from psycopg import sql

from ingestion.storage import connect
from pipeline.run import initialize
from pipeline.publication import MODELS

ROLE = "shopify_dashboard"
VIEWS = (*MODELS, "publication")


def provision():
    password = os.environ.get("DASHBOARD_DB_PASSWORD", "")
    if len(password) < 20 or password.startswith("replace-with-") or password == os.environ.get("DBT_ENV_SECRET_POSTGRES_PASSWORD"):
        raise ValueError("Set a separate random DASHBOARD_DB_PASSWORD of at least 20 characters")
    with connect() as connection:
        # Suppress SQL text during credential provisioning, including error statements.
        connection.execute("SET LOCAL log_statement = 'none'")
        connection.execute("SET LOCAL log_min_error_statement = 'panic'")
        connection.execute(Path(__file__).resolve().parents[1].joinpath("ingestion/schema.sql").read_text())
        connection.execute("CREATE SCHEMA IF NOT EXISTS analytics")
        # Bootstrap metadata only. Candidate financial data is never auto-published.
        connection.commit()
        initialize(connection)
        connection.execute("SET LOCAL log_statement = 'none'")
        connection.execute("SET LOCAL log_min_error_statement = 'panic'")
        if connection.execute("SELECT current_user").fetchone()[0] == ROLE:
            raise ValueError("Dashboard provisioning requires the application database owner")
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,)).fetchone():
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(ROLE)))
        if connection.execute("SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=%s", (ROLE,)).fetchone():
            raise ValueError("Dashboard role must have no role memberships")
        connection.execute(sql.SQL("ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}")
                           .format(sql.Identifier(ROLE), sql.Literal(password)))
        connection.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(sql.Identifier(ROLE)))
        connection.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '10s'").format(sql.Identifier(ROLE)))
        database = connection.execute("SELECT current_database()").fetchone()[0]
        connection.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database),sql.Identifier(ROLE)))
        # PostgreSQL gives PUBLIC temporary-table access by default. Remove that
        # and public-schema CREATE so this login cannot bypass SELECT-only grants.
        connection.execute(sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute(sql.SQL("REVOKE ALL ON SCHEMA raw, analytics, operations, reporting FROM {}").format(sql.Identifier(ROLE)))
        connection.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA raw, analytics, operations, reporting FROM {}").format(sql.Identifier(ROLE)))
        connection.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA raw, analytics, operations, reporting FROM {}").format(sql.Identifier(ROLE)))
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA reporting TO {}").format(sql.Identifier(ROLE)))
        for view in VIEWS:
            if connection.execute("SELECT to_regclass(%s)", ("reporting."+view,)).fetchone()[0]:
                connection.execute(sql.SQL("GRANT SELECT ON {}.{} TO {}")
                                   .format(sql.Identifier("reporting"),sql.Identifier(view),sql.Identifier(ROLE)))


if __name__ == "__main__":
    try:
        provision()
    except Exception:
        raise SystemExit("Dashboard access setup failed; check the separate password and database owner configuration") from None
    print("Dashboard SELECT-only access configured")
