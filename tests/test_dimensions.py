"""Tests for dimension analyzers."""

import pytest
from datetime import datetime, timezone

from ptu_advisor.config import AnalysisConfig, ThresholdConfig
from ptu_advisor.metrics.models import (
    DeploymentMetrics,
    DimensionScore,
    TimeSeries,
)
from ptu_advisor.analysis.dimensions import (
    WorkloadShapeAnalyzer,
    CapacityPressureAnalyzer,
    LatencySensitivityAnalyzer,
    LoadPredictabilityAnalyzer,
)


@pytest.fixture
def config():
    """Create a test configuration."""
    return AnalysisConfig(
        resource_group="test-rg",
        workspace="test-workspace",
        deployment="test-deployment",
        lookback_days=14,
    )


@pytest.fixture
def timestamps():
    """Create test timestamps."""
    return [datetime.now(timezone.utc) for _ in range(200)]


class TestWorkloadShapeAnalyzer:
    """Tests for WorkloadShapeAnalyzer."""
    
    def test_stable_workload(self, config, timestamps):
        """Test that stable workloads score positive."""
        # Create stable metrics (low variance)
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
            tokens_per_minute=TimeSeries(
                timestamps=timestamps,
                values=[100.0] * 200,  # Constant = no variance
                metric_name="tpm",
            ),
        )
        
        analyzer = WorkloadShapeAnalyzer(config)
        result = analyzer.analyze(metrics)
        
        assert result.score == DimensionScore.POSITIVE
        assert "stable" in result.summary.lower()
    
    def test_spiky_workload(self, config, timestamps):
        """Test that spiky workloads score negative."""
        import random
        random.seed(42)
        
        # Create spiky metrics (high variance)
        spiky_values = [random.randint(0, 1000) for _ in range(200)]
        
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
            tokens_per_minute=TimeSeries(
                timestamps=timestamps,
                values=spiky_values,
                metric_name="tpm",
            ),
        )
        
        analyzer = WorkloadShapeAnalyzer(config)
        result = analyzer.analyze(metrics)
        
        # High variance should score negative or neutral
        assert result.score in [DimensionScore.NEGATIVE, DimensionScore.NEUTRAL]
    
    def test_insufficient_data(self, config):
        """Test handling of insufficient data."""
        timestamps = [datetime.now(timezone.utc) for _ in range(10)]  # Too few
        
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
            tokens_per_minute=TimeSeries(
                timestamps=timestamps,
                values=[100.0] * 10,
                metric_name="tpm",
            ),
        )
        
        analyzer = WorkloadShapeAnalyzer(config)
        result = analyzer.analyze(metrics)
        
        assert result.score == DimensionScore.INSUFFICIENT


class TestCapacityPressureAnalyzer:
    """Tests for CapacityPressureAnalyzer."""
    
    def test_high_throttling(self, config, timestamps):
        """Test that high throttling scores positive (PTU would help)."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
            throttled_requests=TimeSeries(
                timestamps=timestamps,
                values=[10.0] * 200,  # Many throttled
                metric_name="throttled",
            ),
            successful_requests=TimeSeries(
                timestamps=timestamps,
                values=[100.0] * 200,
                metric_name="successful",
            ),
            tokens_per_minute=TimeSeries(
                timestamps=timestamps,
                values=[1000.0] * 200,
                metric_name="tpm",
            ),
        )
        
        analyzer = CapacityPressureAnalyzer(config)
        result = analyzer.analyze(metrics)
        
        # High throttling should indicate PTU benefit
        assert result.score == DimensionScore.POSITIVE
        assert result.key_metrics["throttling_rate"] > 0.05
    
    def test_no_throttling(self, config, timestamps):
        """Test that no throttling scores negative."""
        # Create TPM values that vary so avg/max < 0.5 (low utilization)
        # Mix of low values with occasional higher ones
        tpm_values = [50.0] * 180 + [200.0] * 20  # avg ~65, max=200, util ~32%
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
            throttled_requests=TimeSeries(
                timestamps=timestamps,
                values=[0.0] * 200,  # No throttling
                metric_name="throttled",
            ),
            successful_requests=TimeSeries(
                timestamps=timestamps,
                values=[100.0] * 200,
                metric_name="successful",
            ),
            tokens_per_minute=TimeSeries(
                timestamps=timestamps,
                values=tpm_values,  # Low avg utilization (avg/max < 0.5)
                metric_name="tpm",
            ),
        )
        
        analyzer = CapacityPressureAnalyzer(config)
        result = analyzer.analyze(metrics)
        
        assert result.score == DimensionScore.NEGATIVE
        assert result.key_metrics["throttling_rate"] == 0.0


class TestLatencySensitivityAnalyzer:
    """Tests for LatencySensitivityAnalyzer."""
    
    def test_high_latency(self, config, timestamps):
        """Test that high latency scores positive."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
            time_to_first_byte_p50=TimeSeries(
                timestamps=timestamps,
                values=[1000.0] * 200,  # 1000ms
                metric_name="p50",
            ),
            time_to_first_byte_p95=TimeSeries(
                timestamps=timestamps,
                values=[6000.0] * 200,  # 6000ms - high!
                metric_name="p95",
            ),
            time_to_first_byte_p99=TimeSeries(
                timestamps=timestamps,
                values=[10000.0] * 200,  # 10s - very high variance
                metric_name="p99",
            ),
        )
        
        analyzer = LatencySensitivityAnalyzer(config)
        result = analyzer.analyze(metrics)
        
        assert result.score == DimensionScore.POSITIVE
    
    def test_stable_low_latency(self, config, timestamps):
        """Test that stable low latency scores negative."""
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
            time_to_first_byte_p50=TimeSeries(
                timestamps=timestamps,
                values=[500.0] * 200,  # 500ms
                metric_name="p50",
            ),
            time_to_first_byte_p95=TimeSeries(
                timestamps=timestamps,
                values=[800.0] * 200,  # 800ms - stable
                metric_name="p95",
            ),
            time_to_first_byte_p99=TimeSeries(
                timestamps=timestamps,
                values=[900.0] * 200,  # 900ms - very stable
                metric_name="p99",
            ),
        )
        
        analyzer = LatencySensitivityAnalyzer(config)
        result = analyzer.analyze(metrics)
        
        assert result.score == DimensionScore.NEGATIVE


class TestLoadPredictabilityAnalyzer:
    """Tests for LoadPredictabilityAnalyzer."""
    
    def test_sustained_load(self, config, timestamps):
        """Test that sustained load scores positive."""
        # Create a repeating daily pattern (24-hour cycle) so correlation is high
        # This simulates predictable daily load patterns
        # All values are >= 30% of max (100) to ensure 100% sustained rate
        daily_pattern = [35, 40, 45, 50, 60, 70, 80, 90, 100, 95, 90, 85,  # hours 0-11
                         80, 75, 70, 65, 60, 55, 50, 45, 40, 38, 35, 33]   # hours 12-23
        # Repeat for ~8 days (192 hours) + some extra
        rpm_values = (daily_pattern * 9)[:200]  # 216 values, take 200
        
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
            requests_per_minute=TimeSeries(
                timestamps=timestamps,
                values=[float(v) for v in rpm_values],  # Predictable daily pattern
                metric_name="rpm",
            ),
        )
        
        analyzer = LoadPredictabilityAnalyzer(config)
        result = analyzer.analyze(metrics)
        
        assert result.score == DimensionScore.POSITIVE
        assert result.key_metrics["sustained_traffic_pct"] == 1.0
    
    def test_sparse_load(self, config, timestamps):
        """Test that sparse load scores negative."""
        # Mostly zeros
        sparse_values = [0.0] * 160 + [100.0] * 40  # 20% active
        
        metrics = DeploymentMetrics(
            deployment_name="test",
            model_name="gpt-4",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
            requests_per_minute=TimeSeries(
                timestamps=timestamps,
                values=sparse_values,
                metric_name="rpm",
            ),
        )
        
        analyzer = LoadPredictabilityAnalyzer(config)
        result = analyzer.analyze(metrics)
        
        assert result.score == DimensionScore.NEGATIVE
        assert result.key_metrics["sustained_traffic_pct"] < 0.3
