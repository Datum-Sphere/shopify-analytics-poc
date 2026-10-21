"""Internal authenticated fixed-operation HTTP interface; no command/SQL inputs."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading

from ingestion.storage import connect
from pipeline.run import prepare, execute, status
from runtime_config import remote_demo_read_only


def token_from_env():
    token = os.environ.get("PIPELINE_TRIGGER_TOKEN", "")
    other = (os.environ.get("DASHBOARD_DB_PASSWORD"), os.environ.get("DBT_ENV_SECRET_POSTGRES_PASSWORD"),
             os.environ.get("SHOPIFY_CLIENT_ID"), os.environ.get("SHOPIFY_CLIENT_SECRET"))
    if len(token) < 32 or token.startswith("replace-with-") or token in other or not token.isascii():
        raise ValueError("Configure an independent random PIPELINE_TRIGGER_TOKEN of at least 32 ASCII characters")
    return token


def start():
    connection = connect()
    try:
        run_id = prepare(connection, origin="dashboard")
        if not run_id:
            connection.close()
            return None
        def worker():
            try:
                result = execute(connection, run_id)
                print(json.dumps(result), flush=True)  # fixed messages and UUID only
            except Exception:
                print('Pipeline worker stopped; check database health.', flush=True)
            finally:
                connection.close()
        threading.Thread(target=worker, name="pipeline-worker", daemon=True).start()
        return str(run_id)
    except Exception:
        connection.close()  # also releases any session lock on thread-start failure
        raise


class Handler(BaseHTTPRequestHandler):
    server_version = "Pipeline"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        pass  # no request paths/headers/provider payloads in logs

    def reply(self, code, body):
        encoded = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def authorized(self):
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(supplied.encode(), ("Bearer " + self.server.token).encode())

    def do_GET(self):
        try:
            if self.path == "/health":
                with connect() as connection:
                    connection.execute("SELECT 1")
                self.reply(200, {"status": "ok"})
            elif not self.authorized():
                self.reply(401, {"error": "Unauthorized"})
            elif self.path == "/status":
                with connect() as connection:
                    self.reply(200, status(connection))
            else:
                self.reply(404, {"error": "Unknown operation"})
        except Exception:
            self.reply(503, {"error": "Pipeline backend unavailable"})

    def do_POST(self):
        try:
            self.close_connection = True
            # Enforce deployment policy before auth, body parsing or admission.
            # Possession of a valid token never overrides read-only demo mode.
            if self.server.remote_demo_read_only and self.path.split("?", 1)[0] == "/runs":
                self.reply(403, {"error": "Pipeline execution is disabled in read-only demo mode."})
            elif not self.authorized():
                self.reply(401, {"error": "Unauthorized"})
            elif self.path != "/runs":
                self.reply(404, {"error": "Unknown operation"})
            elif self.headers.get("Content-Length", "0") != "0" or self.headers.get("Transfer-Encoding"):
                self.reply(400, {"error": "This operation accepts no parameters or request body"})
            else:
                run_id = start()
                self.reply(202 if run_id else 409, {"status": "running" if run_id else "already_running", "run_id": run_id})
        except Exception:
            self.reply(503, {"error": "Pipeline backend unavailable"})


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, *_):
        print("Internal HTTP request failed.", flush=True)


def make_server(address=("0.0.0.0", 8080)):
    read_only = remote_demo_read_only()  # Reject invalid configuration before binding.
    token = token_from_env()
    server = Server(address, Handler)
    server.token = token
    server.remote_demo_read_only = read_only
    return server
