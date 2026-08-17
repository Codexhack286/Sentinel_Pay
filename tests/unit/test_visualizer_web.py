"""Tests for the GET /visualize web page (services/api/app.py)."""

from fastapi.testclient import TestClient

from services.api.app import app

client = TestClient(app)


def test_visualize_page_renders_both_scenes():
    resp = client.get("/visualize")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Scene A" in resp.text
    assert "Scene B" in resp.text
    assert "AUTHORIZED" in resp.text
    assert "DENIED" in resp.text
