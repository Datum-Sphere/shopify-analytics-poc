"""Strict deployment settings shared by the dashboard and internal HTTP host."""
import os


def remote_demo_read_only():
    value = os.environ.get("REMOTE_DEMO_READ_ONLY", "false")
    if value not in ("true", "false"):
        # Do not echo unexpected environment content; it could contain a secret.
        raise ValueError("REMOTE_DEMO_READ_ONLY must be exactly 'true' or 'false'.")
    return value == "true"
