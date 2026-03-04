"""Tests for the decision engine."""

import pytest
from datetime import datetime, timezone

from ptu_advisor.config import AnalysisConfig
from ptu_advisor.metrics.models import (
    DeploymentMetrics,
    DimensionResult,
    DimensionScore,
    DimensionScores,
    Recommendation,
    TimeSeries,
)
from ptu_advisor.analysis.engine import DecisionEngine


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


def create_dimension_result(
    name: str,
    score: DimensionScore,
    confidence: float = 0.8,
) -> DimensionResult:
    """Helper to create dimension results."""
    return DimensionResult(
        name=name,
        score=score,
        confidence=confidence,
        summary=f"Test summary for {name}",
        explanation=f"Test explanation for {name}",
        key_metrics={},
    )


class TestDecisionEngine:
    """Tests for DecisionEngine decision logic."""
    
    def test_all_positive_recommends_ptu(self, config):
        """Test that 4 positive dimensions = PTU recommended."""
        dimensions = DimensionScores(
            workload_shape=create_dimension_result("Workload Shape", DimensionScore.POSITIVE),
            capacity_pressure=create_dimension_result("Capacity Pressure", DimensionScore.POSITIVE),
            latency_sensitivity=create_dimension_result("Latency Sensitivity", DimensionScore.POSITIVE),
            load_predictability=create_dimension_result("Load Predictability", DimensionScore.POSITIVE),
        )
        
        engine = DecisionEngine(config)
        recommendation = engine._decide(dimensions)
        
        assert recommendation == Recommendation.PTU_RECOMMENDED
    
    def test_three_positive_recommends_ptu(self, config):
        """Test that 3 positive dimensions = PTU recommended."""
        dimensions = DimensionScores(
            workload_shape=create_dimension_result("Workload Shape", DimensionScore.POSITIVE),
            capacity_pressure=create_dimension_result("Capacity Pressure", DimensionScore.POSITIVE),
            latency_sensitivity=create_dimension_result("Latency Sensitivity", DimensionScore.POSITIVE),
            load_predictability=create_dimension_result("Load Predictability", DimensionScore.NEGATIVE),
        )
        
        engine = DecisionEngine(config)
        recommendation = engine._decide(dimensions)
        
        assert recommendation == Recommendation.PTU_RECOMMENDED
    
    def test_two_positive_is_borderline(self, config):
        """Test that 2 positive dimensions = Borderline."""
        dimensions = DimensionScores(
            workload_shape=create_dimension_result("Workload Shape", DimensionScore.POSITIVE),
            capacity_pressure=create_dimension_result("Capacity Pressure", DimensionScore.POSITIVE),
            latency_sensitivity=create_dimension_result("Latency Sensitivity", DimensionScore.NEGATIVE),
            load_predictability=create_dimension_result("Load Predictability", DimensionScore.NEGATIVE),
        )
        
        engine = DecisionEngine(config)
        recommendation = engine._decide(dimensions)
        
        assert recommendation == Recommendation.BORDERLINE
    
    def test_one_positive_not_recommended(self, config):
        """Test that 1 positive dimension = Not recommended."""
        dimensions = DimensionScores(
            workload_shape=create_dimension_result("Workload Shape", DimensionScore.POSITIVE),
            capacity_pressure=create_dimension_result("Capacity Pressure", DimensionScore.NEGATIVE),
            latency_sensitivity=create_dimension_result("Latency Sensitivity", DimensionScore.NEGATIVE),
            load_predictability=create_dimension_result("Load Predictability", DimensionScore.NEGATIVE),
        )
        
        engine = DecisionEngine(config)
        recommendation = engine._decide(dimensions)
        
        assert recommendation == Recommendation.PTU_NOT_RECOMMENDED
    
    def test_all_negative_not_recommended(self, config):
        """Test that 0 positive dimensions = Not recommended."""
        dimensions = DimensionScores(
            workload_shape=create_dimension_result("Workload Shape", DimensionScore.NEGATIVE),
            capacity_pressure=create_dimension_result("Capacity Pressure", DimensionScore.NEGATIVE),
            latency_sensitivity=create_dimension_result("Latency Sensitivity", DimensionScore.NEGATIVE),
            load_predictability=create_dimension_result("Load Predictability", DimensionScore.NEGATIVE),
        )
        
        engine = DecisionEngine(config)
        recommendation = engine._decide(dimensions)
        
        assert recommendation == Recommendation.PTU_NOT_RECOMMENDED
    
    def test_neutral_dimensions_not_counted(self, config):
        """Test that neutral dimensions don't count as positive."""
        dimensions = DimensionScores(
            workload_shape=create_dimension_result("Workload Shape", DimensionScore.NEUTRAL),
            capacity_pressure=create_dimension_result("Capacity Pressure", DimensionScore.NEUTRAL),
            latency_sensitivity=create_dimension_result("Latency Sensitivity", DimensionScore.NEUTRAL),
            load_predictability=create_dimension_result("Load Predictability", DimensionScore.NEUTRAL),
        )
        
        engine = DecisionEngine(config)
        recommendation = engine._decide(dimensions)
        
        assert recommendation == Recommendation.PTU_NOT_RECOMMENDED
    
    def test_insufficient_data_is_borderline(self, config):
        """Test that multiple insufficient dimensions = Borderline."""
        dimensions = DimensionScores(
            workload_shape=create_dimension_result("Workload Shape", DimensionScore.INSUFFICIENT),
            capacity_pressure=create_dimension_result("Capacity Pressure", DimensionScore.INSUFFICIENT),
            latency_sensitivity=create_dimension_result("Latency Sensitivity", DimensionScore.POSITIVE),
            load_predictability=create_dimension_result("Load Predictability", DimensionScore.POSITIVE),
        )
        
        engine = DecisionEngine(config)
        recommendation = engine._decide(dimensions)
        
        assert recommendation == Recommendation.BORDERLINE


class TestDecisionEngineIntegration:
    """Integration tests for the full analysis flow."""
    
    def test_full_analysis_flow(self, config, timestamps):
        """Test the complete analysis flow with real metrics."""
        metrics = DeploymentMetrics(
            deployment_name="test-deployment",
            model_name="gpt-4o",
            start_time=timestamps[0],
            end_time=timestamps[-1],
            timestamps=timestamps,
            tokens_per_minute=TimeSeries(
                timestamps=timestamps,
                values=[1000.0] * 200,
                metric_name="tpm",
            ),
            requests_per_minute=TimeSeries(
                timestamps=timestamps,
                values=[50.0] * 200,
                metric_name="rpm",
            ),
            throttled_requests=TimeSeries(
                timestamps=timestamps,
                values=[5.0] * 200,
                metric_name="throttled",
            ),
            successful_requests=TimeSeries(
                timestamps=timestamps,
                values=[50.0] * 200,
                metric_name="successful",
            ),
            time_to_first_byte_p50=TimeSeries(
                timestamps=timestamps,
                values=[500.0] * 200,
                metric_name="p50",
            ),
            time_to_first_byte_p95=TimeSeries(
                timestamps=timestamps,
                values=[1000.0] * 200,
                metric_name="p95",
            ),
            time_to_first_byte_p99=TimeSeries(
                timestamps=timestamps,
                values=[1500.0] * 200,
                metric_name="p99",
            ),
        )
        
        engine = DecisionEngine(config)
        result = engine.analyze(metrics)
        
        # Verify result structure
        assert result.recommendation in [
            Recommendation.PTU_RECOMMENDED,
            Recommendation.BORDERLINE,
            Recommendation.PTU_NOT_RECOMMENDED,
        ]
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.summary) > 0
        assert len(result.explanation) > 0
        assert len(result.what_would_change) > 0
        assert result.dimensions is not None
