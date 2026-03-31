"""Regression test: dashboard index must return 200 on Starlette 1.0.0.

Before fix: TemplateResponse("base.html", {"request": ..., ...}) raises
TypeError on Starlette 1.0.0 because the dict becomes the name argument
and Jinja2 can't hash (dict, globals) as a cache key.

After fix: TemplateResponse(request, "base.html", {...}) works correctly.
"""

import pytest
from fastapi.testclient import TestClient


def test_dashboard_index_returns_200():
    """GET / must return 200 OK — regression for Starlette 1.0.0 compat."""
    from pocketpaw.dashboard import app

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200, (
        f"Dashboard returned {response.status_code}. "
        "This likely means TemplateResponse is using the old Starlette <1.0 "
        "signature. See: TemplateResponse(request, name, context) not "
        "TemplateResponse(name, context)."
    )


def test_dashboard_index_returns_html():
    """GET / must return text/html content."""
    from pocketpaw.dashboard import app

    client = TestClient(app)
    response = client.get("/")
    assert "text/html" in response.headers.get("content-type", "")