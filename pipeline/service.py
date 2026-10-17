"""Idle application host for future orchestration, with graceful shutdown."""

import signal
import threading

from pipeline.healthcheck import check_database


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    check_database()
    print("Pipeline environment ready; ingestion is not implemented.", flush=True)
    stop.wait()


if __name__ == "__main__":
    main()
