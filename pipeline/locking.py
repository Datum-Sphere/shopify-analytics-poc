"""One session lock shared by supported source-writing entry points."""
LOCK_KEY = 736481204


def acquire(connection):
    acquired = connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]
    connection.commit()
    return acquired


def release(connection):
    connection.rollback()
    connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    connection.commit()
