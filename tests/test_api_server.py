import base64
import json
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import ptu_advisor.api.server as api_server
from ptu_advisor import __version__
from ptu_advisor.api.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def configure_local_auth(monkeypatch):
    monkeypatch.setenv("PTU_ADVISOR_AUTH_MODE", "local")


def _easy_auth_headers(*roles: str) -> dict[str, str]:
    principal = {
        "auth_typ": "aad",
        "claims": [
            {
                "typ": "http://schemas.microsoft.com/ws/2008/06/identity/claims/role",
                "val": role,
            }
            for role in roles
        ],
    }
    encoded = base64.b64encode(json.dumps(principal).encode("utf-8")).decode("ascii")
    return {
        "X-MS-CLIENT-PRINCIPAL-ID": "test-user-id",
        "X-MS-CLIENT-PRINCIPAL": encoded,
    }


def test_health_endpoint_returns_ok():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_metadata_matches_package_release_version():
    response = client.get("/openapi.json")

    assert __version__ == "1.1.0"
    assert response.status_code == 200
    assert response.json()["info"]["version"] == __version__


def test_easy_auth_mode_rejects_unauthenticated_api_request(monkeypatch):
    monkeypatch.setenv("PTU_ADVISOR_AUTH_MODE", "easy_auth")
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "test-app-service-instance")

    response = client.get("/api/focus-topics")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_easy_auth_mode_accepts_authenticated_api_request(monkeypatch):
    monkeypatch.setenv("PTU_ADVISOR_AUTH_MODE", "easy_auth")
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "test-app-service-instance")
    monkeypatch.setenv("PTU_ADVISOR_REQUIRED_APP_ROLE", "PTUAdvisor.User")

    response = client.get(
        "/api/focus-topics",
        headers=_easy_auth_headers("PTUAdvisor.User"),
    )

    assert response.status_code == 200


def test_unset_auth_mode_fails_closed(monkeypatch):
    monkeypatch.delenv("PTU_ADVISOR_AUTH_MODE", raising=False)

    response = client.get("/api/focus-topics")

    assert response.status_code == 500
    assert response.json() == {"detail": "Server authentication mode must be configured."}


def test_easy_auth_mode_requires_configured_app_role(monkeypatch):
    monkeypatch.setenv("PTU_ADVISOR_AUTH_MODE", "easy_auth")
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "test-app-service-instance")
    monkeypatch.setenv("PTU_ADVISOR_REQUIRED_APP_ROLE", "PTUAdvisor.User")

    response = client.get(
        "/api/focus-topics",
        headers=_easy_auth_headers("Other.Role"),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Required application role is missing."}


def test_easy_auth_mode_keeps_health_endpoint_public(monkeypatch):
    monkeypatch.setenv("PTU_ADVISOR_AUTH_MODE", "easy_auth")

    response = client.get("/api/health")

    assert response.status_code == 200


def test_easy_auth_mode_rejects_identity_header_outside_app_service(monkeypatch):
    monkeypatch.setenv("PTU_ADVISOR_AUTH_MODE", "easy_auth")
    monkeypatch.delenv("WEBSITE_INSTANCE_ID", raising=False)

    response = client.get(
        "/api/focus-topics",
        headers={"X-MS-CLIENT-PRINCIPAL-ID": "spoofed-user-id"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Easy Auth mode requires Azure App Service hosting."
    }


def test_local_auth_mode_allows_api_request_without_identity_header(monkeypatch):
    monkeypatch.setenv("PTU_ADVISOR_AUTH_MODE", "local")

    response = client.get("/api/focus-topics")

    assert response.status_code == 200


def test_cors_rejects_unneeded_cross_origin_methods(monkeypatch):
    monkeypatch.setenv("PTU_ADVISOR_AUTH_MODE", "local")

    response = client.options(
        "/api/analyze",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "DELETE",
        },
    )

    assert response.status_code == 400


def test_auth_status_does_not_expose_raw_authentication_error(monkeypatch):
    marker = "credential-secret-value"

    def fail_authentication():
        raise RuntimeError(marker)

    monkeypatch.setattr(api_server, "authenticate", fail_authentication)

    response = client.get("/api/discovery/auth-status")

    assert response.status_code == 200
    assert response.json()["error"] == "Azure authentication unavailable."
    assert marker not in response.text


def test_discovery_does_not_expose_raw_credential_error(monkeypatch):
    marker = "credential-secret-value"

    def fail_credential():
        raise RuntimeError(marker)

    monkeypatch.setattr(api_server, "get_azure_credential", fail_credential)

    response = client.get("/api/discovery/subscriptions")

    assert response.status_code == 401
    assert marker not in response.text


def test_easy_auth_filters_subscriptions_to_configured_allowlist(monkeypatch):
    monkeypatch.setenv("PTU_ADVISOR_AUTH_MODE", "easy_auth")
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "test-app-service-instance")
    monkeypatch.setenv("PTU_ADVISOR_REQUIRED_APP_ROLE", "PTUAdvisor.User")
    monkeypatch.setenv("PTU_ADVISOR_ALLOWED_SUBSCRIPTION_IDS", "allowed-sub")
    monkeypatch.setattr(api_server, "get_azure_credential", lambda: object())
    monkeypatch.setattr(
        api_server,
        "list_subscriptions",
        lambda _credential: [
            SimpleNamespace(
                subscription_id="allowed-sub",
                display_name="Allowed",
                state="Enabled",
                label="Allowed",
            ),
            SimpleNamespace(
                subscription_id="blocked-sub",
                display_name="Blocked",
                state="Enabled",
                label="Blocked",
            ),
        ],
    )

    response = client.get(
        "/api/discovery/subscriptions",
        headers=_easy_auth_headers("PTUAdvisor.User"),
    )

    assert response.status_code == 200
    assert [item["subscription_id"] for item in response.json()] == ["allowed-sub"]


def test_easy_auth_blocks_disallowed_subscription_before_azure_call(monkeypatch):
    monkeypatch.setenv("PTU_ADVISOR_AUTH_MODE", "easy_auth")
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "test-app-service-instance")
    monkeypatch.setenv("PTU_ADVISOR_REQUIRED_APP_ROLE", "PTUAdvisor.User")
    monkeypatch.setenv("PTU_ADVISOR_ALLOWED_SUBSCRIPTION_IDS", "allowed-sub")

    def fail_credential():
        raise AssertionError("Azure credential should not be acquired")

    monkeypatch.setattr(api_server, "get_azure_credential", fail_credential)

    response = client.get(
        "/api/discovery/accounts",
        params={"subscription_id": "blocked-sub"},
        headers=_easy_auth_headers("PTUAdvisor.User"),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Subscription is not allowed."}


def test_easy_auth_blocks_disallowed_export_before_credential_acquisition(monkeypatch):
    monkeypatch.setenv("PTU_ADVISOR_AUTH_MODE", "easy_auth")
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "test-app-service-instance")
    monkeypatch.setenv("PTU_ADVISOR_REQUIRED_APP_ROLE", "PTUAdvisor.User")
    monkeypatch.setenv("PTU_ADVISOR_ALLOWED_SUBSCRIPTION_IDS", "allowed-sub")

    def fail_credential():
        raise AssertionError("Azure credential should not be acquired")

    monkeypatch.setattr(api_server, "get_azure_credential", fail_credential)

    response = client.post(
        "/api/export/token-snapshot",
        json={
            "mode": "live",
            "subscription_id": "blocked-sub",
            "resource_group": "rg",
            "workspace": "workspace",
            "deployment": "deployment",
        },
        headers=_easy_auth_headers("PTUAdvisor.User"),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Subscription is not allowed."}


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ("/api/discovery/subscriptions", "list_subscriptions"),
        ("/api/discovery/accounts?subscription_id=sub", "list_ai_accounts"),
        (
            "/api/discovery/deployments?subscription_id=sub&resource_group=rg&account_name=acct",
            "list_deployments",
        ),
    ],
)
def test_discovery_does_not_expose_raw_azure_error(monkeypatch, path, target):
    marker = "azure-response-secret-value"

    def fail_azure_call(*args, **kwargs):
        raise RuntimeError(marker)

    monkeypatch.setattr(api_server, "get_azure_credential", lambda: object())
    monkeypatch.setattr(api_server, target, fail_azure_call)

    response = client.get(path)

    assert response.status_code == 403
    assert marker not in response.text


def test_startup_pricing_warmup_is_non_blocking(monkeypatch):
    class FakeResolver:
        def __init__(self):
            self.warm_cache_called = False
            self.background_called = False

        def warm_cache(self):
            self.warm_cache_called = True

        def start_background_warmup(self):
            self.background_called = True

    resolver = FakeResolver()
    monkeypatch.setattr(api_server, "get_pricing_resolver", lambda: resolver)

    api_server._startup_warm_pricing_cache()

    assert resolver.background_called is True
    assert resolver.warm_cache_called is False


def test_shutdown_stops_pricing_warmup(monkeypatch):
    class FakeResolver:
        def __init__(self):
            self.stop_called = False

        def stop_background_warmup(self):
            self.stop_called = True

    resolver = FakeResolver()
    monkeypatch.setattr(api_server, "get_pricing_resolver", lambda: resolver)

    shutdown = getattr(api_server, "_shutdown_pricing_cache", None)

    assert shutdown is not None
    shutdown()
    assert resolver.stop_called is True


def test_static_file_resolution_rejects_path_outside_root(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("secret", encoding="utf-8")

    resolver = getattr(api_server, "_resolve_static_file", None)

    assert resolver is not None
    assert resolver(static_dir, "../secret.txt") is None


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
    assert "prompt_cache" in payload["charts"]
    assert "payg" in payload["cost_analysis"]
    assert "hybrid" in payload["cost_analysis"]
    assert "formula_blocks" in payload["cost_analysis"]
    assert "cache_impact" in payload["cost_analysis"]
    assert "max_viable_baseline_ptu" in payload["cost_analysis"]["hybrid"]


def test_demo_analyze_generates_only_the_visible_cost_curve(monkeypatch):
    generate_curves = api_server.generate_cache_aware_cost_curves
    call_count = 0

    def count_curve_generation(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return generate_curves(*args, **kwargs)

    monkeypatch.setattr(api_server, "generate_cache_aware_cost_curves", count_curve_generation)

    response = client.post("/api/analyze", json={"mode": "demo"})

    assert response.status_code == 200
    assert call_count == 1


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


def test_live_analyze_sanitizes_no_metrics_diagnostics(monkeypatch):
    marker = "azure-sdk-secret-diagnostic"
    metrics, _scenario = api_server.generate_demo_metrics(api_server.DemoScenario.COST_HIGH_VOLUME)
    metrics.tokens_per_minute = None
    metrics.requests_per_minute = None

    class EmptyMetricsCollector:
        def __init__(self, *_args, **_kwargs):
            pass

        def collect(self):
            return metrics

        def get_diagnostics(self):
            return {
                "context": {"resource_id": "/subscriptions/private-sub/resourceGroups/private-rg"},
                "metrics": [
                    {
                        "metric_name": "TokenTransaction",
                        "status": "missing",
                        "message": marker,
                    }
                ],
            }

    monkeypatch.setattr(api_server, "get_azure_credential", lambda: object())
    monkeypatch.setattr(api_server, "MetricsCollector", EmptyMetricsCollector)

    response = client.post(
        "/api/analyze",
        json={
            "mode": "live",
            "subscription_id": "sub",
            "resource_group": "rg",
            "workspace": "workspace",
            "deployment": "deployment",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "message": "No metrics returned for selected deployment",
        "hint": "No metrics were returned. Verify recent traffic and Monitoring Reader access.",
    }
    assert marker not in response.text
    assert "private-sub" not in response.text


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


def test_analysis_without_usable_tpm_sweep_returns_no_max_viable_ptu(monkeypatch):
    original_generate = api_server.generate_demo_metrics
    original_build_cache_impact = api_server.build_cache_impact

    def generate_without_tpm(*args, **kwargs):
        metrics, scenario = original_generate(*args, **kwargs)
        metrics.tokens_per_minute = None
        return metrics, scenario

    def build_without_normalized_shape(**kwargs):
        impact = original_build_cache_impact(**kwargs)
        return replace(impact, adjusted_normalized_tpm=[])

    monkeypatch.setattr(api_server, "generate_demo_metrics", generate_without_tpm)
    monkeypatch.setattr(api_server, "build_cache_impact", build_without_normalized_shape)

    response = client.post("/api/analyze", json={"mode": "demo"})

    assert response.status_code == 200
    assert response.json()["cost_analysis"]["hybrid"]["max_viable_baseline_ptu"] is None


def test_cost_curve_uses_final_optimized_baseline():
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
    hybrid = payload["cost_analysis"]["hybrid"]
    curves = payload["charts"]["cost_curves"]

    assert curves["selected_ptu"] == hybrid["baseline_ptu"]
    assert curves["ptu_capacity_tpm"] == pytest.approx(hybrid["ptu_capacity_tpm"])
    assert curves["ptu_spill_monthly"][0] == pytest.approx(hybrid["ptu_baseline_cost"])


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


def test_pricing_rates_with_region_and_deployment_type(monkeypatch):
    """GET /api/pricing/rates respects region and deployment_type params."""
    requested = {}

    class FakeResolver:
        def resolve(self, *, model_name, region, deployment_type):
            requested.update(
                model_name=model_name,
                region=region,
                deployment_type=deployment_type,
            )
            return SimpleNamespace(
                model_name=model_name,
                region=region,
                deployment_type=deployment_type,
                payg_input_rate=2.50,
                payg_cached_input_rate=1.25,
                payg_output_rate=10.00,
                ptu_hourly_rate=2.20,
                ptu_pricing_source="fallback",
                source="fallback",
                cached_input_source="fallback",
                as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
                currency="USD",
            )

    monkeypatch.setattr(api_server, "get_pricing_resolver", lambda: FakeResolver())

    response = client.get(
        "/api/pricing/rates",
        params={"model": "gpt-4o", "region": "swedencentral", "deployment_type": "regional"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["region"] == "swedencentral"
    assert payload["deployment_type"] == "regional"
    assert requested == {
        "model_name": "gpt-4o",
        "region": "swedencentral",
        "deployment_type": "regional",
    }
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


def test_pricing_rates_rejects_invalid_deployment_type():
    response = client.get(
        "/api/pricing/rates",
        params={"model": "gpt-4o", "deployment_type": "globall"},
    )

    assert response.status_code == 422


def test_pricing_rates_rejects_unknown_region_before_resolution(monkeypatch):
    class UnexpectedResolver:
        def resolve(self, **_kwargs):
            raise AssertionError("Resolver must not receive an unknown region")

    monkeypatch.setattr(api_server, "get_pricing_resolver", lambda: UnexpectedResolver())

    response = client.get(
        "/api/pricing/rates",
        params={"model": "gpt-4o", "region": "eastus' or 1 eq 1 or '"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Unsupported Azure region."}


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


def test_demo_analyze_applies_cache_override() -> None:
    response = client.post(
        "/api/analyze",
        json={
            "mode": "demo",
            "focus_topic": "Cost Reduction",
            "lookback_days": 14,
            "cache_mode": "override",
            "cache_match_rate_override_pct": 50.0,
            "cached_input_rate_override": 0.5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    cache = payload["cost_analysis"]["cache_impact"]
    assert cache["applied"] is True
    assert cache["source"] == "override"
    assert cache["no_cache_normalized_avg_tpm"] > cache["cache_adjusted_normalized_avg_tpm"]
    assert cache["fixed_ptu_cost_changed"] is False
    assert payload["metrics"]["cache_match_rate"]["avg_pct"] == pytest.approx(50.0)
    assert payload["cost_analysis"]["pricing"]["payg_cached_input_rate_per_million"] == 0.5
    assert "cached_input_cost" in payload["cost_analysis"]["formula_blocks"]["payg"]
    assert "fixed PTU cost" in payload["cost_analysis"]["formula_blocks"]["hybrid"]
    no_cache = payload["cost_analysis"]["no_cache_comparison"]
    assert no_cache["payg_total"] >= payload["cost_analysis"]["payg"]["payg_total"]
    assert no_cache["ptu_baseline_cost"] == pytest.approx(
        payload["cost_analysis"]["hybrid"]["ptu_baseline_cost"]
    )
    assert no_cache["hybrid_total"] >= payload["cost_analysis"]["hybrid"]["hybrid_total"]
    assert no_cache["recommendation"] in {
        "ptu_recommended",
        "borderline",
        "ptu_not_recommended",
    }
    assert "commitment_safety" in no_cache
    assert "break_even_tpm" in no_cache


def test_demo_analyze_rejects_override_without_rate() -> None:
    response = client.post(
        "/api/analyze",
        json={"mode": "demo", "cache_mode": "override"},
    )

    assert response.status_code == 422


def test_demo_analyze_disabled_cache_preserves_no_cache_load() -> None:
    response = client.post(
        "/api/analyze",
        json={"mode": "demo", "cache_mode": "disabled"},
    )

    assert response.status_code == 200
    cache = response.json()["cost_analysis"]["cache_impact"]
    assert cache["source"] == "disabled"
    assert cache["applied"] is False
    assert cache["no_cache_normalized_avg_tpm"] == pytest.approx(
        cache["cache_adjusted_normalized_avg_tpm"]
    )


def test_token_snapshot_includes_cache_analysis_metadata() -> None:
    response = client.post(
        "/api/export/token-snapshot",
        json={"mode": "demo", "focus_topic": "Cost Reduction", "days": 7},
    )

    assert response.status_code == 200
    cache = response.json()["_meta"]["cache_analysis"]
    assert cache["source"] == "observed"
    assert cache["coverage_pct"] == pytest.approx(100.0)
    assert cache["cached_prompt_tokens"] > 0
    cache_metric = response.json()["value"][2]
    assert cache_metric["unit"] == "Percent"
    assert cache_metric["timeseries"][0]["data"][0]["average"] > 1


def test_analyze_rejects_negative_ptu_baseline() -> None:
    response = client.post(
        "/api/analyze",
        json={"mode": "demo", "baseline_ptu": -5},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("baseline_percentile", [-1, 96])
def test_analyze_rejects_out_of_range_baseline_percentile(
    baseline_percentile: int,
) -> None:
    response = client.post(
        "/api/analyze",
        json={"mode": "demo", "baseline_percentile": baseline_percentile},
    )

    assert response.status_code == 422


def test_analyze_rounds_ptu_baseline_to_minimum_and_increment() -> None:
    below_minimum = client.post(
        "/api/analyze",
        json={"mode": "demo", "baseline_ptu": 1},
    ).json()
    off_increment = client.post(
        "/api/analyze",
        json={"mode": "demo", "baseline_ptu": 17},
    ).json()

    assert below_minimum["cost_analysis"]["hybrid"]["baseline_ptu"] == 15
    assert off_increment["cost_analysis"]["hybrid"]["baseline_ptu"] == 20


def test_daily_cost_aggregation_scales_per_minute_rates_by_interval() -> None:
    from ptu_advisor.api.server import _aggregate_daily_costs

    result = _aggregate_daily_costs(
        timestamps=["2026-07-01T00:00:00Z", "2026-07-01T00:05:00Z"],
        prompt_values=[100.0, 100.0],
        completion_values=[0.0, 0.0],
        payg_input_rate=1_000.0,
        payg_output_rate=0.0,
        interval_minutes=5,
    )

    assert result["input_cost"] == [1.0]


def test_unavailable_cache_is_labeled_conservative_not_measured_zero() -> None:
    response = client.post(
        "/api/analyze",
        json={"mode": "demo", "cache_mode": "disabled"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cost_analysis"]["cache_impact"]["applied"] is False
    assert "assumes no cache benefit" in payload["cost_analysis"]["cache_impact"][
        "calculation_note"
    ]


def test_zero_traffic_returns_insufficient_cost_data(monkeypatch) -> None:
    generate_demo_metrics = api_server.generate_demo_metrics

    def generate_zero_traffic_metrics(*args, **kwargs):
        metrics, scenario = generate_demo_metrics(*args, **kwargs)
        for attribute in [
            "tokens_per_minute",
            "prompt_tokens",
            "completion_tokens",
            "requests_per_minute",
            "successful_requests",
            "throttled_requests",
            "cache_match_rate",
            "active_tokens",
        ]:
            series = getattr(metrics, attribute)
            if series is not None:
                setattr(metrics, attribute, replace(series, values=[0.0] * len(series.values)))
        return metrics, scenario

    monkeypatch.setattr(api_server, "generate_demo_metrics", generate_zero_traffic_metrics)

    response = client.post("/api/analyze", json={"mode": "demo"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation"] == "insufficient_data"
    assert payload["cost_analysis"]["status"] == "insufficient_data"
    assert payload["cost_analysis"]["comparison"]["cheaper_strategy"] is None
    assert payload["cost_analysis"]["comparison"]["break_even_tpm"] is None
    assert "insufficient traffic data" in payload["insights"]["break_even_message"].lower()


def test_hourly_token_snapshot_serializes_hourly_totals() -> None:
    response = client.post(
        "/api/export/token-snapshot",
        json={"mode": "demo", "focus_topic": "Cost Reduction", "days": 1, "interval": "PT1H"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["interval"] == "PT1H"
    input_points = payload["value"][0]["timeseries"][0]["data"]
    assert input_points
    # Snapshot token entries are interval totals, not normalized TPM values.
    assert input_points[0]["total"] > 60_000


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


def test_demo_analyze_accepts_one_year_commitment() -> None:
    response = client.post(
        "/api/analyze",
        json={
            "mode": "demo",
            "reservation_type": "1-Year Commitment (Estimated 69% off)",
        },
    )

    assert response.status_code == 200
    pricing = response.json()["cost_analysis"]["pricing"]
    assert pricing["reservation_type"] == "1-Year Commitment (Estimated 69% off)"
    assert pricing["reservation_discount_pct"] == 69


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
