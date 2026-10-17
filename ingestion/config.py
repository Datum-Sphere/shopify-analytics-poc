"""Validated environment configuration; secret values never appear in repr."""
import os
import re
from dataclasses import dataclass, field


class IngestionError(Exception):
    """Only application-authored, credential-free messages cross the CLI boundary."""


@dataclass(frozen=True)
class ShopifyConfig:
    store: str
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    version: str = "2026-10"

    def __post_init__(self):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", self.store):
            raise IngestionError("configuration: SHOPIFY_STORE_DOMAIN must be a myshopify.com hostname")
        if not self.client_id or not self.client_secret or any(
            value.startswith("replace-with-") for value in (self.client_id, self.client_secret)
        ):
            raise IngestionError("configuration: set SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET")
        if not re.fullmatch(r"20[0-9]{2}-(01|04|07|10)", self.version):
            raise IngestionError("configuration: invalid SHOPIFY_API_VERSION")

    @classmethod
    def from_env(cls):
        return cls(os.getenv("SHOPIFY_STORE_DOMAIN", ""), os.getenv("SHOPIFY_CLIENT_ID", ""),
                   os.getenv("SHOPIFY_CLIENT_SECRET", ""), os.getenv("SHOPIFY_API_VERSION", "2026-10"))
