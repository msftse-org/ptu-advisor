"""Tests for PTU model eligibility — deployment gate & visual indicators.

Tests cover:
1. DeploymentInfo.ptu_eligible field on the dataclass
2. /api/discovery/deployments enrichment with ptu_eligible flag
3. /api/analyze rejection of non-PTU-eligible models (HTTP 422)
4. get_model_config() returns None for non-PTU models
5. get_model_family() classifies models into human-readable families (Phase 2)
6. get_ineligibility_reason() returns model-specific explanations (Phase 2)
7. /api/discovery/deployments includes model_family and ineligibility_reason (Phase 2)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from ptu_advisor.config import get_ineligibility_reason, get_model_config, get_model_family
from ptu_advisor.metrics.models import DeploymentInfo


# ---------------------------------------------------------------------------
# DeploymentInfo.ptu_eligible field
# ---------------------------------------------------------------------------


class TestDeploymentInfoEligibility:
    """Verify the ptu_eligible field on DeploymentInfo dataclass."""

    def test_default_is_false(self):
        dep = DeploymentInfo(name="test", model="gpt-4o", sku_type="Standard")
        assert dep.ptu_eligible is False

    def test_can_set_true(self):
        dep = DeploymentInfo(name="test", model="gpt-4o", sku_type="Standard", ptu_eligible=True)
        assert dep.ptu_eligible is True

    def test_can_set_false_explicitly(self):
        dep = DeploymentInfo(
            name="test", model="embedding", sku_type="Standard", ptu_eligible=False
        )
        assert dep.ptu_eligible is False


# ---------------------------------------------------------------------------
# get_model_config() for non-PTU models
# ---------------------------------------------------------------------------


class TestNonPtuModelConfig:
    """Verify get_model_config returns None for models not in MODEL_CAPACITY_CONFIGS."""

    @pytest.mark.parametrize(
        "model_name",
        [
            "text-embedding-ada-002",
            "text-embedding-3-small",
            "text-embedding-3-large",
            "dall-e-3",
            "whisper",
            "tts",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k",
            "Llama-3-70b",
            "Mistral-large",
            "Phi-3-medium",
            "Cohere-command-r",
            "some-random-model",
        ],
    )
    def test_non_ptu_model_returns_none(self, model_name: str):
        assert get_model_config(model_name) is None

    @pytest.mark.parametrize(
        "model_name",
        [
            "gpt-5",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "gpt-4o",
            "gpt-4o-mini",
            "o1",
            "o3-mini",
            "o4-mini",
        ],
    )
    def test_ptu_model_returns_config(self, model_name: str):
        cfg = get_model_config(model_name)
        assert cfg is not None

    @pytest.mark.parametrize(
        "model_name",
        [
            "gpt-4o (2024-11-20)",
            "GPT-4O",
            "gpt-4.1-mini (2025-04-14)",
            "GPT-5",
        ],
    )
    def test_ptu_model_fuzzy_match(self, model_name: str):
        """Models with version suffixes or case differences still match."""
        cfg = get_model_config(model_name)
        assert cfg is not None


# ---------------------------------------------------------------------------
# /api/discovery/deployments enrichment
# ---------------------------------------------------------------------------


class TestDeploymentDiscoveryEligibility:
    """Verify /api/discovery/deployments enriches response with ptu_eligible."""

    @patch("ptu_advisor.api.server.get_azure_credential")
    @patch("ptu_advisor.api.server.list_deployments")
    def test_eligible_deployment_gets_true(self, mock_list, mock_cred):
        from ptu_advisor.api.server import deployments

        mock_cred.return_value = MagicMock()
        mock_list.return_value = [
            DeploymentInfo(
                name="gpt4o-prod", model="gpt-4o", sku_type="Standard", sku_capacity=120
            ),
        ]

        result = deployments(
            subscription_id="sub-1",
            resource_group="rg-1",
            account_name="acct-1",
        )

        assert len(result) == 1
        assert result[0]["ptu_eligible"] is True
        assert result[0]["name"] == "gpt4o-prod"
        assert result[0]["model"] == "gpt-4o"

    @patch("ptu_advisor.api.server.get_azure_credential")
    @patch("ptu_advisor.api.server.list_deployments")
    def test_ineligible_deployment_gets_false(self, mock_list, mock_cred):
        from ptu_advisor.api.server import deployments

        mock_cred.return_value = MagicMock()
        mock_list.return_value = [
            DeploymentInfo(
                name="embed-prod",
                model="text-embedding-3-large",
                sku_type="Standard",
                sku_capacity=350,
            ),
        ]

        result = deployments(
            subscription_id="sub-1",
            resource_group="rg-1",
            account_name="acct-1",
        )

        assert len(result) == 1
        assert result[0]["ptu_eligible"] is False
        assert result[0]["model"] == "text-embedding-3-large"

    @patch("ptu_advisor.api.server.get_azure_credential")
    @patch("ptu_advisor.api.server.list_deployments")
    def test_mixed_deployments_eligibility(self, mock_list, mock_cred):
        from ptu_advisor.api.server import deployments

        mock_cred.return_value = MagicMock()
        mock_list.return_value = [
            DeploymentInfo(
                name="gpt4o-prod", model="gpt-4o", sku_type="Standard", sku_capacity=120
            ),
            DeploymentInfo(
                name="embed-prod",
                model="text-embedding-3-large",
                sku_type="Standard",
                sku_capacity=350,
            ),
            DeploymentInfo(
                name="gpt5-preview",
                model="gpt-5 (2025-06-01)",
                sku_type="Standard",
                sku_capacity=60,
            ),
            DeploymentInfo(
                name="dalle-prod", model="dall-e-3", sku_type="Standard", sku_capacity=10
            ),
        ]

        result = deployments(
            subscription_id="sub-1",
            resource_group="rg-1",
            account_name="acct-1",
        )

        assert len(result) == 4
        eligibility = {r["name"]: r["ptu_eligible"] for r in result}
        assert eligibility["gpt4o-prod"] is True
        assert eligibility["embed-prod"] is False
        assert eligibility["gpt5-preview"] is True
        assert eligibility["dalle-prod"] is False

    @patch("ptu_advisor.api.server.get_azure_credential")
    @patch("ptu_advisor.api.server.list_deployments")
    def test_empty_deployments_returns_empty_list(self, mock_list, mock_cred):
        from ptu_advisor.api.server import deployments

        mock_cred.return_value = MagicMock()
        mock_list.return_value = []

        result = deployments(
            subscription_id="sub-1",
            resource_group="rg-1",
            account_name="acct-1",
        )

        assert result == []


# ---------------------------------------------------------------------------
# /api/analyze eligibility guard (live mode)
# ---------------------------------------------------------------------------


class TestAnalyzeEligibilityGuard:
    """Verify /api/analyze rejects non-PTU-eligible models with HTTP 422."""

    def _make_live_request(self, **overrides):
        from ptu_advisor.api.server import AnalyzeRequest

        defaults = {
            "mode": "live",
            "subscription_id": "sub-1",
            "resource_group": "rg-1",
            "workspace": "ws-1",
            "deployment": "test-dep",
            "lookback_days": 7,
            "granularity_minutes": 5,
        }
        defaults.update(overrides)
        return AnalyzeRequest(**defaults)

    @patch("ptu_advisor.api.server.get_azure_credential")
    @patch("ptu_advisor.api.server.MetricsCollector")
    def test_rejects_non_ptu_model(self, MockCollector, mock_cred):
        from fastapi import HTTPException
        from ptu_advisor.api.server import analyze
        from ptu_advisor.metrics.models import DeploymentMetrics, TimeSeries

        mock_cred.return_value = MagicMock()

        now = datetime.now(timezone.utc)
        metrics = DeploymentMetrics(
            deployment_name="embed-dep",
            model_name="text-embedding-3-large",
            start_time=now - timedelta(days=7),
            end_time=now,
            tokens_per_minute=TimeSeries(
                timestamps=[now], values=[100.0], metric_name="TokensPerMinute"
            ),
            requests_per_minute=TimeSeries(
                timestamps=[now], values=[10.0], metric_name="RequestsPerMinute"
            ),
        )

        collector_instance = MagicMock()
        collector_instance.collect.return_value = metrics
        MockCollector.return_value = collector_instance

        request = self._make_live_request(deployment="embed-dep")

        with pytest.raises(HTTPException) as exc_info:
            analyze(request)

        assert exc_info.value.status_code == 422
        assert "text-embedding-3-large" in exc_info.value.detail
        assert "does not support PTU" in exc_info.value.detail

    @patch("ptu_advisor.api.server.get_azure_credential")
    @patch("ptu_advisor.api.server.MetricsCollector")
    def test_rejects_legacy_model(self, MockCollector, mock_cred):
        from fastapi import HTTPException
        from ptu_advisor.api.server import analyze
        from ptu_advisor.metrics.models import DeploymentMetrics, TimeSeries

        mock_cred.return_value = MagicMock()

        now = datetime.now(timezone.utc)
        metrics = DeploymentMetrics(
            deployment_name="gpt35-dep",
            model_name="gpt-3.5-turbo",
            start_time=now - timedelta(days=7),
            end_time=now,
            tokens_per_minute=TimeSeries(
                timestamps=[now], values=[500.0], metric_name="TokensPerMinute"
            ),
            requests_per_minute=TimeSeries(
                timestamps=[now], values=[50.0], metric_name="RequestsPerMinute"
            ),
        )

        collector_instance = MagicMock()
        collector_instance.collect.return_value = metrics
        MockCollector.return_value = collector_instance

        request = self._make_live_request(deployment="gpt35-dep")

        with pytest.raises(HTTPException) as exc_info:
            analyze(request)

        assert exc_info.value.status_code == 422
        assert "gpt-3.5-turbo" in exc_info.value.detail

    def test_demo_mode_bypasses_eligibility_gate(self):
        """Demo mode doesn't hit the eligibility gate because it uses demo scenarios."""
        from ptu_advisor.api.server import AnalyzeRequest, analyze

        request = AnalyzeRequest(
            mode="demo",
            focus_topic="Cost Reduction",
            lookback_days=7,
            granularity_minutes=5,
        )

        # Should not raise — demo mode uses PTU-eligible models
        result = analyze(request)
        assert result.recommendation is not None

    @patch("ptu_advisor.api.server.get_azure_credential")
    @patch("ptu_advisor.api.server.MetricsCollector")
    def test_error_message_lists_eligible_models(self, MockCollector, mock_cred):
        """The 422 error message should mention eligible model families."""
        from fastapi import HTTPException
        from ptu_advisor.api.server import analyze
        from ptu_advisor.metrics.models import DeploymentMetrics, TimeSeries

        mock_cred.return_value = MagicMock()

        now = datetime.now(timezone.utc)
        metrics = DeploymentMetrics(
            deployment_name="dalle-dep",
            model_name="dall-e-3",
            start_time=now - timedelta(days=7),
            end_time=now,
            tokens_per_minute=TimeSeries(
                timestamps=[now], values=[0.0], metric_name="TokensPerMinute"
            ),
            requests_per_minute=TimeSeries(
                timestamps=[now], values=[1.0], metric_name="RequestsPerMinute"
            ),
        )

        collector_instance = MagicMock()
        collector_instance.collect.return_value = metrics
        MockCollector.return_value = collector_instance

        request = self._make_live_request(deployment="dalle-dep")

        with pytest.raises(HTTPException) as exc_info:
            analyze(request)

        detail = exc_info.value.detail
        assert "GPT-4o" in detail
        assert "GPT-4.1" in detail
        assert "GPT-5" in detail
        assert "o1" in detail
        assert "o3-mini" in detail
        assert "o4-mini" in detail


# ---------------------------------------------------------------------------
# Phase 2: get_model_family() classification
# ---------------------------------------------------------------------------


class TestGetModelFamily:
    """Verify get_model_family classifies models into human-readable families."""

    @pytest.mark.parametrize(
        "model_name,expected_family",
        [
            ("gpt-5", "GPT-5"),
            ("gpt-5 (2025-06-01)", "GPT-5"),
            ("GPT-5", "GPT-5"),
            ("gpt-4.1", "GPT-4.1"),
            ("gpt-4.1 (2025-04-14)", "GPT-4.1"),
            ("gpt-4.1-mini", "GPT-4.1 Mini"),
            ("gpt-4.1-mini (2025-04-14)", "GPT-4.1 Mini"),
            ("gpt-4.1-nano", "GPT-4.1 Nano"),
            ("gpt-4o", "GPT-4o"),
            ("gpt-4o (2024-11-20)", "GPT-4o"),
            ("GPT-4O", "GPT-4o"),
            ("gpt-4o-mini", "GPT-4o Mini"),
            ("o1", "o1"),
            ("o3-mini", "o3-mini"),
            ("o4-mini", "o4-mini"),
            ("text-embedding-ada-002", "Embedding"),
            ("text-embedding-3-small", "Embedding"),
            ("text-embedding-3-large", "Embedding"),
            ("dall-e-3", "DALL-E"),
            ("whisper", "Whisper"),
            ("tts", "TTS"),
            ("gpt-3.5-turbo", "GPT-3.5 (Legacy)"),
            ("gpt-3.5-turbo-16k", "GPT-3.5 (Legacy)"),
        ],
    )
    def test_known_models(self, model_name: str, expected_family: str):
        assert get_model_family(model_name) == expected_family

    @pytest.mark.parametrize(
        "model_name",
        [
            "Llama-3-70b",
            "Mistral-large",
            "Phi-3-medium",
            "Cohere-command-r",
            "some-random-model",
        ],
    )
    def test_unknown_models_return_other(self, model_name: str):
        assert get_model_family(model_name) == "Other"

    def test_longer_match_takes_priority(self):
        """gpt-4o-mini must match 'GPT-4o Mini' not 'GPT-4o'."""
        assert get_model_family("gpt-4o-mini") == "GPT-4o Mini"
        assert get_model_family("gpt-4.1-mini") == "GPT-4.1 Mini"
        assert get_model_family("gpt-4.1-nano") == "GPT-4.1 Nano"


# ---------------------------------------------------------------------------
# Phase 2: get_ineligibility_reason()
# ---------------------------------------------------------------------------


class TestGetIneligibilityReason:
    """Verify model-specific ineligibility reasons."""

    def test_embedding_reason(self):
        reason = get_ineligibility_reason("Embedding")
        assert "Embedding models" in reason
        assert "per-token" in reason

    def test_dalle_reason(self):
        reason = get_ineligibility_reason("DALL-E")
        assert "Image generation" in reason

    def test_whisper_reason(self):
        reason = get_ineligibility_reason("Whisper")
        assert "Audio models" in reason

    def test_tts_reason(self):
        reason = get_ineligibility_reason("TTS")
        assert "Audio models" in reason

    def test_legacy_gpt35_reason(self):
        reason = get_ineligibility_reason("GPT-3.5 (Legacy)")
        assert "retired" in reason
        assert "GPT-4o-mini" in reason

    def test_other_model_default_reason(self):
        reason = get_ineligibility_reason("Other")
        assert "does not support Provisioned Throughput Units" in reason

    def test_ptu_eligible_family_returns_default(self):
        """Eligible families like 'GPT-4o' are not in INELIGIBILITY_REASONS."""
        reason = get_ineligibility_reason("GPT-4o")
        assert "does not support Provisioned Throughput Units" in reason


# ---------------------------------------------------------------------------
# Phase 2: /api/discovery/deployments — model_family & ineligibility_reason
# ---------------------------------------------------------------------------


class TestDeploymentDiscoveryPhase2:
    """Verify /api/discovery/deployments includes model_family and ineligibility_reason."""

    @patch("ptu_advisor.api.server.get_azure_credential")
    @patch("ptu_advisor.api.server.list_deployments")
    def test_eligible_deployment_has_model_family(self, mock_list, mock_cred):
        from ptu_advisor.api.server import deployments

        mock_cred.return_value = MagicMock()
        mock_list.return_value = [
            DeploymentInfo(
                name="gpt4o-prod", model="gpt-4o", sku_type="Standard", sku_capacity=120
            ),
        ]

        result = deployments(
            subscription_id="sub-1",
            resource_group="rg-1",
            account_name="acct-1",
        )

        assert len(result) == 1
        assert result[0]["model_family"] == "GPT-4o"
        assert result[0]["ptu_eligible"] is True
        # Eligible deployments should NOT have ineligibility_reason
        assert "ineligibility_reason" not in result[0]

    @patch("ptu_advisor.api.server.get_azure_credential")
    @patch("ptu_advisor.api.server.list_deployments")
    def test_ineligible_deployment_has_reason(self, mock_list, mock_cred):
        from ptu_advisor.api.server import deployments

        mock_cred.return_value = MagicMock()
        mock_list.return_value = [
            DeploymentInfo(
                name="embed-prod",
                model="text-embedding-3-large",
                sku_type="Standard",
                sku_capacity=350,
            ),
        ]

        result = deployments(
            subscription_id="sub-1",
            resource_group="rg-1",
            account_name="acct-1",
        )

        assert len(result) == 1
        assert result[0]["model_family"] == "Embedding"
        assert result[0]["ptu_eligible"] is False
        assert "ineligibility_reason" in result[0]
        assert "Embedding models" in result[0]["ineligibility_reason"]

    @patch("ptu_advisor.api.server.get_azure_credential")
    @patch("ptu_advisor.api.server.list_deployments")
    def test_mixed_deployments_families(self, mock_list, mock_cred):
        from ptu_advisor.api.server import deployments

        mock_cred.return_value = MagicMock()
        mock_list.return_value = [
            DeploymentInfo(
                name="gpt4o-prod", model="gpt-4o", sku_type="Standard", sku_capacity=120
            ),
            DeploymentInfo(
                name="embed-prod",
                model="text-embedding-3-large",
                sku_type="Standard",
                sku_capacity=350,
            ),
            DeploymentInfo(
                name="gpt5-preview",
                model="gpt-5 (2025-06-01)",
                sku_type="Standard",
                sku_capacity=60,
            ),
            DeploymentInfo(
                name="dalle-prod", model="dall-e-3", sku_type="Standard", sku_capacity=10
            ),
        ]

        result = deployments(
            subscription_id="sub-1",
            resource_group="rg-1",
            account_name="acct-1",
        )

        families = {r["name"]: r["model_family"] for r in result}
        assert families["gpt4o-prod"] == "GPT-4o"
        assert families["embed-prod"] == "Embedding"
        assert families["gpt5-preview"] == "GPT-5"
        assert families["dalle-prod"] == "DALL-E"

        # Only ineligible deployments have ineligibility_reason
        reasons = {r["name"]: r.get("ineligibility_reason") for r in result}
        assert reasons["gpt4o-prod"] is None
        assert reasons["gpt5-preview"] is None
        assert reasons["embed-prod"] is not None
        assert reasons["dalle-prod"] is not None
