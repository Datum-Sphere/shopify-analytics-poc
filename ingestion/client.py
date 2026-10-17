"""Read-only Shopify transport with in-memory expiring tokens and bounded retries."""
import random
import re
import time

import requests

from ingestion.config import IngestionError


class ShopifyClient:
    def __init__(self, config, session=None, sleep=time.sleep, clock=time.monotonic):
        self.config = config
        self.session = session or requests.Session()
        self.sleep = sleep
        self.clock = clock
        self._token = None
        self._expires_at = 0

    def close(self):
        self._token = None
        self.session.close()

    def _wait(self, attempt, response=None):
        delay = 2 ** attempt + random.uniform(0, 0.25)
        if response is not None:
            try:
                delay = max(delay, float(response.headers.get("Retry-After", 0)))
            except (ValueError, TypeError):
                pass
        self.sleep(min(delay, 60))

    def _post(self, path, operation, **kwargs):
        for attempt in range(4):
            try:
                response = self.session.post(
                    f"https://{self.config.store}{path}", timeout=(10, 60),
                    allow_redirects=False, **kwargs,
                )
            except requests.RequestException:
                if attempt == 3:
                    raise IngestionError(f"{operation}: network/timeout failure after 4 attempts") from None
                self._wait(attempt)
                continue
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt == 3:
                    raise IngestionError(f"{operation}: transient HTTP failure after 4 attempts")
                self._wait(attempt, response)
                continue
            return response

    def token(self):
        if self._token and self.clock() < self._expires_at:
            return self._token
        response = self._post("/admin/oauth/access_token", "authentication", data={
            "grant_type": "client_credentials", "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        })
        if response.status_code != 200:
            raise IngestionError("authentication: token request rejected; check app installation and client credentials")
        try:
            body = response.json()
            token = body["access_token"]
            lifetime = int(body["expires_in"])
            if not isinstance(token, str) or not token or lifetime <= 0:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise IngestionError("authentication: invalid token response") from None
        self._token = token
        self._expires_at = self.clock() + max(0, lifetime - min(60, lifetime / 10))
        return self._token

    def graphql(self, query, variables=None):
        # All extraction operations must explicitly be queries, never mutations.
        if not query.lstrip().startswith("query "):
            raise IngestionError("graphql: only explicit read-only queries are allowed")
        refreshed = False
        for attempt in range(4):
            response = self._post(f"/admin/api/{self.config.version}/graphql.json", "graphql",
                                  headers={"X-Shopify-Access-Token": self.token()},
                                  json={"query": query, "variables": variables or {}})
            if response.status_code == 401 and not refreshed:
                self._token = None
                refreshed = True
                continue
            if response.status_code != 200:
                code = response.status_code
                raise IngestionError(f"graphql: HTTP {code}; check credentials, installation and granted read scopes")
            actual_version = response.headers.get("X-Shopify-API-Version")
            if actual_version and actual_version != self.config.version:
                raise IngestionError("graphql: server API version differs from SHOPIFY_API_VERSION; refusing silent fallback")
            try:
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                raise IngestionError("graphql: invalid JSON response") from None
            errors = body.get("errors")
            if errors:
                codes = {e.get("extensions", {}).get("code") for e in errors if isinstance(e, dict)}
                if codes == {"THROTTLED"} and attempt < 3:
                    self._wait(attempt)
                    continue
                if "ACCESS_DENIED" in codes:
                    raise IngestionError("graphql: access denied; check existing read scopes and protected-data access")
                # Shopify error messages may echo input; never persist/log them.
                fields = sorted({e.get("extensions", {}).get("fieldName", "") for e in errors
                                 if isinstance(e, dict)})
                fields = [f for f in fields if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", f) and f in query]
                hint = ": fields=" + ",".join(fields) if fields else ""
                raise IngestionError("graphql: query rejected or throttling exhausted; inspect query fields and API version" + hint)
            if not isinstance(body.get("data"), dict):
                raise IngestionError("graphql: missing data object")
            cost = body.get("extensions", {}).get("cost", {})
            throttle = cost.get("throttleStatus", {})
            available = throttle.get("currentlyAvailable", 1000)
            restore = throttle.get("restoreRate", 50)
            requested = cost.get("requestedQueryCost", 0)
            if restore > 0 and available < requested:
                self.sleep(min((requested - available) / restore, 60))
            return body["data"]
        raise IngestionError("graphql: authentication refresh or retry budget exhausted")

    def paginate(self, query, path, variables=None):
        values = dict(variables or {})
        cursor = None
        seen = set()
        while True:
            data = self.graphql(query, {**values, "after": cursor})
            try:
                connection = data
                for key in path:
                    connection = connection[key]
                nodes = connection["nodes"]
                page = connection["pageInfo"]
                if not isinstance(nodes, list) or not isinstance(page["hasNextPage"], bool):
                    raise ValueError
                yield from nodes
                if not page["hasNextPage"]:
                    return
                cursor = page["endCursor"]
                if not cursor or cursor in seen:
                    raise ValueError
                seen.add(cursor)
            except (KeyError, TypeError, ValueError):
                raise IngestionError("pagination: missing connection or non-advancing cursor") from None
