"""Idle application host for future orchestration, with graceful shutdown."""

import signal
import threading

from pipeline.healthcheck import check_database
from pipeline.dashboard_access import provision


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    check_database()
    try:
        provision()
    except Exception:
        raise SystemExit("Dashboard access setup failed; check the separate dashboard password and database owner configuration") from None
    print("Pipeline environment ready; automatic pipeline execution is disabled.", flush=True)
    stop.wait()


if __name__ == "__main__":
    main()
