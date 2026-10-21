"""Server-to-server fixed operations only. No secret is sent to the browser."""
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler


class Unavailable(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


def request(path, method="GET"):
    try:
        token = os.environ["PIPELINE_TRIGGER_TOKEN"]
        # Operator-supplied Compose setting only, never a dashboard input.
        base = os.environ.get("PIPELINE_API_URL", "http://app:8080")
        if base != "http://app:8080":
            raise ValueError("Unexpected backend address")
        req = Request(base + path, data=b"" if method == "POST" else None,
                      method=method, headers={"Authorization": "Bearer " + token})
        try:
            with build_opener(NoRedirect()).open(req, timeout=5) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 403:
                raise Unavailable("Pipeline execution is disabled in read-only demo mode.") from None
            if exc.code == 409:
                return {"status": "already_running"}
            raise
    except Unavailable:
        raise
    except Exception:
        raise Unavailable("Pipeline control is unavailable. Ask the operator to check backend health and authentication.") from None


def status():
    return request("/status")


def trigger():
    return request("/runs", "POST")
