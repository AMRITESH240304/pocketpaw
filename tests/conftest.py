"""Pytest configuration."""

from unittest.mock import patch

import pytest

from pocketpaw.security.audit import AuditLogger


@pytest.fixture(autouse=True)
def _isolate_audit_log(tmp_path):
    """Prevent tests from writing to the real ~/.pocketpaw/audit.jsonl.

    Creates a temp audit logger per test and patches the singleton so
    ToolRegistry.execute() and any other callers write to a throwaway file.
    """
    temp_logger = AuditLogger(log_path=tmp_path / "audit.jsonl")
    with (
        patch("pocketpaw.security.audit._audit_logger", temp_logger),
        patch("pocketpaw.security.audit.get_audit_logger", return_value=temp_logger),
        patch("pocketpaw.tools.registry.get_audit_logger", return_value=temp_logger),
    ):
        yield temp_logger


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Clear in-memory rate-limiter buckets between tests.

    The module-level ``api_limiter``, ``auth_limiter``, and ``ws_limiter``
    singletons accumulate request counts across tests when the full suite
    runs, causing tests that check for 401 responses to receive 429 instead.
    Resetting the bucket dicts after each test prevents this state leak.
    """
    from pocketpaw.security.rate_limiter import api_limiter, auth_limiter, ws_limiter

    yield
    for limiter in (api_limiter, auth_limiter, ws_limiter):
        limiter._buckets.clear()
