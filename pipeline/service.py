"""Internal pipeline HTTP host; no automatic Shopify runs at startup."""

import signal
import threading

from pipeline.healthcheck import check_database
from pipeline.dashboard_access import provision
from pipeline.api import make_server


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    check_database()
    try:
        provision()
    except Exception:
        raise SystemExit("Dashboard access setup failed; check the separate dashboard password and database owner configuration") from None
    server = make_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Authenticated pipeline interface ready on the Docker network.", flush=True)
    stop.wait()
    server.shutdown()
    server.server_close()


if __name__ == "__main__":
    main()
