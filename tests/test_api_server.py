from fastapi.testclient import TestClient

from ptu_advisor.api.server import app


client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_focus_topics_endpoint_returns_list():
    response = client.get("/api/focus-topics")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) > 0
    assert "name" in payload[0]
    assert "tagline" in payload[0]


def test_demo_analyze_returns_expected_shape():
    response = client.post(
        "/api/analyze",
        json={
            "mode": "demo",
            "focus_topic": "Cost Reduction",
            "lookback_days": 14,
            "reservation_type": "Monthly Commitment (Estimated 64% off)",
            "baseline_percentile": 75,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    for key in [
        "recommendation",
        "confidence",
        "summary",
        "explanation",
        "what_would_change",
        "data_quality",
        "analysis_period",
        "dimensions",
        "metrics",
        "charts",
        "cost_analysis",
        "insights",
    ]:
        assert key in payload

    assert "tokens" in payload["charts"]
    assert "requests" in payload["charts"]
    assert "latency" in payload["charts"]
    assert "cost_curves" in payload["charts"]
    assert "payg" in payload["cost_analysis"]
    assert "hybrid" in payload["cost_analysis"]
    assert "formula_blocks" in payload["cost_analysis"]


def test_demo_analyze_supports_granularity_and_time_window():
    response = client.post(
        "/api/analyze",
        json={
            "mode": "demo",
            "focus_topic": "Cost Reduction",
            "lookback_days": 14,
            "granularity_minutes": 15,
            "window_start": "2026-02-01T00:00:00Z",
            "window_end": "2026-02-01T12:00:00Z",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["lookback_days"] >= 1
    assert isinstance(payload["charts"]["tokens"]["timestamps"], list)


def test_live_analyze_without_required_fields_returns_400():
    response = client.post("/api/analyze", json={"mode": "live"})

    assert response.status_code == 400
    assert "required in live mode" in response.json().get("detail", "")
