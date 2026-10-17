"""Check authenticated database connectivity without logging credentials."""

import os

import psycopg


def check_database():
    with psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["DBT_ENV_SECRET_POSTGRES_PASSWORD"],
        connect_timeout=5,
    ) as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)


if __name__ == "__main__":
    try:
        check_database()
    except Exception:
        raise SystemExit("Database health check failed") from None
