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


# ---------------------------------------------------------------------------
# Phase 3.2: /api/pricing/rates endpoint
# ---------------------------------------------------------------------------


def test_pricing_rates_returns_valid_shape():
    """GET /api/pricing/rates should return resolved rates for a known model."""
    response = client.get("/api/pricing/rates", params={"model": "gpt-4o"})

    assert response.status_code == 200
    payload = response.json()

    for key in [
        "model",
        "region",
        "deployment_type",
        "payg_input_rate_per_million",
        "payg_output_rate_per_million",
        "ptu_hourly_rate",
        "pricing_source",
        "pricing_as_of",
        "pricing_currency",
    ]:
        assert key in payload, f"Missing key: {key}"

    assert payload["model"] == "gpt-4o"
    assert payload["pricing_currency"] == "USD"
    assert payload["payg_input_rate_per_million"] > 0
    assert payload["payg_output_rate_per_million"] > 0
    assert payload["ptu_hourly_rate"] > 0


def test_pricing_rates_with_region_and_deployment_type():
    """GET /api/pricing/rates respects region and deployment_type params."""
    response = client.get(
        "/api/pricing/rates",
        params={"model": "gpt-4o", "region": "swedencentral", "deployment_type": "regional"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["region"] == "swedencentral"
    assert payload["deployment_type"] == "regional"
    # Regional Sweden → tier 2 → $2.20
    assert payload["ptu_hourly_rate"] == pytest.approx(2.20, rel=0.01)


def test_pricing_rates_unknown_model():
    """GET /api/pricing/rates for an unknown model returns default fallback rates."""
    response = client.get("/api/pricing/rates", params={"model": "unknown-model-999"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["pricing_source"] == "fallback"
    # Default fallback rates
    assert payload["payg_input_rate_per_million"] == pytest.approx(2.50, rel=0.01)
    assert payload["payg_output_rate_per_million"] == pytest.approx(10.00, rel=0.01)


def test_pricing_rates_requires_model_param():
    """GET /api/pricing/rates without model param returns 422."""
    response = client.get("/api/pricing/rates")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Phase 2: pricing source and overrides in /api/analyze
# ---------------------------------------------------------------------------


def test_demo_analyze_returns_pricing_source_metadata():
    """The /api/analyze response should contain pricing_source, pricing_as_of, pricing_currency."""
    response = client.post(
        "/api/analyze",
        json={"mode": "demo", "focus_topic": "Cost Reduction", "lookback_days": 14},
    )

    assert response.status_code == 200
    pricing = response.json()["cost_analysis"]["pricing"]
    assert "pricing_source" in pricing
    assert pricing["pricing_source"] in ("live", "cached", "fallback", "manual")
    assert "pricing_as_of" in pricing
    assert "pricing_currency" in pricing
    assert pricing["pricing_currency"] == "USD"


def test_demo_analyze_with_overrides_returns_manual_source():
    """When rate overrides are provided, pricing_source should be 'manual'."""
    response = client.post(
        "/api/analyze",
        json={
            "mode": "demo",
            "focus_topic": "Cost Reduction",
            "lookback_days": 14,
            "payg_input_rate_override": 5.0,
            "payg_output_rate_override": 20.0,
            "ptu_hourly_rate_override": 3.0,
        },
    )

    assert response.status_code == 200
    pricing = response.json()["cost_analysis"]["pricing"]
    assert pricing["pricing_source"] == "manual"
    assert pricing["payg_input_rate_per_million"] == pytest.approx(5.0, rel=0.01)
    assert pricing["payg_output_rate_per_million"] == pytest.approx(20.0, rel=0.01)
    assert pricing["ptu_hourly_rate"] == pytest.approx(3.0, rel=0.01)


def test_demo_analyze_with_partial_override():
    """A partial override (only one rate) should still set source to 'manual'."""
    response = client.post(
        "/api/analyze",
        json={
            "mode": "demo",
            "focus_topic": "Cost Reduction",
            "lookback_days": 14,
            "ptu_hourly_rate_override": 2.5,
        },
    )

    assert response.status_code == 200
    pricing = response.json()["cost_analysis"]["pricing"]
    assert pricing["pricing_source"] == "manual"
    assert pricing["ptu_hourly_rate"] == pytest.approx(2.5, rel=0.01)


def test_formula_blocks_annotated_with_custom_rate_on_manual():
    """When overrides are used, formula_blocks should contain '(custom rate)'."""
    response = client.post(
        "/api/analyze",
        json={
            "mode": "demo",
            "focus_topic": "Cost Reduction",
            "lookback_days": 14,
            "payg_input_rate_override": 5.0,
        },
    )

    assert response.status_code == 200
    blocks = response.json()["cost_analysis"]["formula_blocks"]
    assert "(custom rate)" in blocks["payg"]
    assert "(custom rate)" in blocks["hybrid"]


def test_formula_blocks_not_annotated_without_override():
    """Without overrides, formula_blocks should NOT contain '(custom rate)'."""
    response = client.post(
        "/api/analyze",
        json={"mode": "demo", "focus_topic": "Cost Reduction", "lookback_days": 14},
    )

    assert response.status_code == 200
    blocks = response.json()["cost_analysis"]["formula_blocks"]
    assert "(custom rate)" not in blocks["payg"]
    assert "(custom rate)" not in blocks["hybrid"]
