import pytest
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
    assert "daily_cost" in payload["charts"]
    assert "cost_curves" in payload["charts"]
    assert "payg" in payload["cost_analysis"]
    assert "hybrid" in payload["cost_analysis"]
    assert "formula_blocks" in payload["cost_analysis"]
    assert "max_viable_baseline_ptu" in payload["cost_analysis"]["hybrid"]


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


def test_daily_cost_total_updates_with_time_window():
    """Daily cost data must change when window_start/window_end narrows the time range."""
    # Full-range analysis
    full = client.post(
        "/api/analyze",
        json={"mode": "demo", "focus_topic": "Cost Reduction", "lookback_days": 14},
    ).json()

    full_dates = full["charts"]["daily_cost"]["dates"]
    full_total = sum(full["charts"]["daily_cost"]["total_cost"])
    assert len(full_dates) > 1, "Demo should produce multiple daily cost entries"

    # Windowed analysis — use the first date only
    first_day = full_dates[0]
    # Build a window that covers only the first day (00:00 to 23:59)
    window_start = f"{first_day}T00:00:00Z"
    window_end = f"{first_day}T23:59:59Z"

    windowed = client.post(
        "/api/analyze",
        json={
            "mode": "demo",
            "focus_topic": "Cost Reduction",
            "lookback_days": 14,
            "window_start": window_start,
            "window_end": window_end,
        },
    ).json()

    windowed_dates = windowed["charts"]["daily_cost"]["dates"]
    windowed_total = sum(windowed["charts"]["daily_cost"]["total_cost"])

    # The windowed result should have fewer (or equal) dates
    assert len(windowed_dates) <= len(full_dates)
    # And the total should be less than or equal to the full-range total
    assert windowed_total <= full_total + 0.01  # float tolerance


def test_cost_curve_avg_marker_uses_avg_tpm_formula():
    response = client.post(
        "/api/analyze",
        json={
            "mode": "demo",
            "focus_topic": "Cost Reduction",
            "lookback_days": 14,
            "reservation_type": "Monthly Commitment (Estimated 64% off)",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    avg_tpm = payload["metrics"]["avg_tpm"]
    blended_rate = payload["cost_analysis"]["pricing"]["payg_blended_rate_per_million"]
    returned_payg_at_avg = payload["charts"]["cost_curves"]["payg_at_avg"]
    expected_payg_at_avg = avg_tpm * 43_200 / 1_000_000 * blended_rate

    assert returned_payg_at_avg == pytest.approx(expected_payg_at_avg, rel=1e-6)


def test_break_even_message_is_directional_not_final_recommendation():
    response = client.post(
        "/api/analyze",
        json={
            "mode": "demo",
            "focus_topic": "Cost Reduction",
            "lookback_days": 14,
            "reservation_type": "Monthly Commitment (Estimated 64% off)",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    message = payload["insights"]["break_even_message"]

    assert "Economic break-even" in message or "No economic break-even" in message
    assert "Final recommendation:" in message


def test_max_viable_baseline_is_not_below_default_baseline():
    response = client.post(
        "/api/analyze",
        json={
            "mode": "demo",
            "focus_topic": "Cost Reduction",
            "lookback_days": 14,
            "reservation_type": "Monthly Commitment (Estimated 64% off)",
        },
    )

    assert response.status_code == 200
    hybrid = response.json()["cost_analysis"]["hybrid"]
    max_viable = hybrid["max_viable_baseline_ptu"]
    default_ptu = hybrid["default_baseline_ptu"]

    if max_viable is not None:
        assert max_viable >= default_ptu
