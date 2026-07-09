from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_landing_page_returns_200() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "AI Solution Sales Insight Agent" in response.text
    assert "/demo" in response.text


def test_demo_page_returns_200() -> None:
    client = TestClient(app)

    response = client.get("/demo")

    assert response.status_code == 200
    assert "Run Agent" in response.text
    assert "Evidence" in response.text
    assert "Fallback" in response.text
    assert "Enterprise Context" in response.text
    assert "Skill Trace" in response.text
    assert "Shadow Debug" in response.text


def test_demo_page_includes_solution_insight_fetch_call() -> None:
    client = TestClient(app)

    response = client.get("/demo")
    script_response = client.get("/static/demo.js")

    assert response.status_code == 200
    assert script_response.status_code == 200
    assert "/static/demo.js" in response.text
    assert 'fetch("/solution-insight"' in script_response.text
    assert "Shadow retrieval is diagnostic only and does not affect the formal answer." in response.text
