from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


FORMAL_RESULT_FILES = [
    Path("data/evaluation/retrieval/lexical_baseline_results.v2.jsonl"),
    Path("data/evaluation/retrieval/lexical_baseline_summary.v2.json"),
    Path("data/evaluation/retrieval/vector_baseline_results.v2.jsonl"),
    Path("data/evaluation/retrieval/vector_baseline_summary.v2.json"),
    Path("data/evaluation/retrieval/hybrid_baseline_results.v2.jsonl"),
    Path("data/evaluation/retrieval/hybrid_baseline_summary.v2.json"),
    Path("data/evaluation/retrieval/retrieval_method_comparison.v2.json"),
]


def _hash_files() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in FORMAL_RESULT_FILES:
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "solution-insight-agent"}


def test_solution_insight_endpoint_returns_structured_result_without_key() -> None:
    client = TestClient(app)
    payload = {
        "user_query": "一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
        "industry": "SaaS",
        "company_size": "中型",
        "current_systems": ["CRM", "客服系统"],
        "target_goal": "提升转化和客户成功效率",
        "constraints": ["不改变现有CRM主流程"],
        "enable_shadow_retrieval": False,
        "llm_mode": "deterministic",
    }
    before_hashes = _hash_files()

    response = client.post("/solution-insight", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["llm_mode"] == "deterministic"
    assert data["requirement_summary"]
    assert isinstance(data["pain_points"], list)
    assert isinstance(data["ai_opportunity_points"], list)
    assert isinstance(data["evidence_items"], list)
    assert data["shadow_retrieval_debug"] is None
    assert data["enterprise_context"] is None
    assert data["human_confirmation_required"] is True
    assert _hash_files() == before_hashes


def test_solution_insight_endpoint_rejects_missing_query() -> None:
    client = TestClient(app)

    response = client.post("/solution-insight", json={})

    assert response.status_code == 422
    assert response.json()["detail"]


def test_shadow_retrieval_debug_is_optional_and_shown_when_enabled() -> None:
    client = TestClient(app)
    payload = {
        "user_query": "想做带证据引用的内部知识检索",
        "enable_shadow_retrieval": True,
        "llm_mode": "deterministic",
    }

    response = client.post("/solution-insight", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["shadow_retrieval_debug"] is not None
    assert data["shadow_retrieval_debug"]["hierarchical_mode"] == "shadow"
    assert data["shadow_retrieval_debug"]["candidate_count"] >= 0


def test_solution_insight_endpoint_accepts_company_id() -> None:
    client = TestClient(app)
    payload = {
        "user_query": "一家中型 SaaS 公司想提升销售线索转化和客户成功效率",
        "industry": "SaaS",
        "company_id": "demo_saas_001",
        "enable_shadow_retrieval": False,
        "llm_mode": "deterministic",
    }

    response = client.post("/solution-insight", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["enterprise_context"] is not None
    assert data["enterprise_context"]["context_source"] == "mcp_mock"
