"""Tests for the metrics collector."""

import logging
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import warnings

from ptu_advisor.config import AnalysisConfig
from ptu_advisor.metrics.collector import MetricsCollector
from ptu_advisor.metrics.models import AggregationType, MetricName, TimeSeries


@pytest.fixture
def config():
    """Create a test configuration."""
    return AnalysisConfig(
        resource_group="test-rg",
        workspace="test-workspace",
        deployment="test-deployment",
        subscription_id="test-subscription",
        lookback_days=7,
    )


@pytest.fixture
def mock_credential():
    """Create a mock Azure credential."""
    credential = MagicMock()
    credential.get_token.return_value = MagicMock(token="test-token")
    return credential


class TestMetricsCollector:
    """Tests for MetricsCollector."""
    
    def test_init(self, mock_credential, config):
        """Test collector initialization."""
        with patch('ptu_advisor.metrics.collector.get_subscription_id', return_value="test-sub"):
            with patch('ptu_advisor.metrics.collector.MonitorManagementClient'):
                with patch('ptu_advisor.metrics.collector.CognitiveServicesManagementClient'):
                    collector = MetricsCollector(mock_credential, config)
                    
                    assert collector.config == config
                    assert collector.subscription_id == "test-sub"

    def test_collect_metric_aggregates_total_by_timestamp_sorted(
        self,
        mock_credential,
        config,
    ):
        """TOTAL aggregation should sum values across series per timestamp."""
        with patch('ptu_advisor.metrics.collector.get_subscription_id', return_value="test-sub"):
            with patch('ptu_advisor.metrics.collector.MonitorManagementClient'):
                with patch('ptu_advisor.metrics.collector.CognitiveServicesManagementClient'):
                    collector = MetricsCollector(mock_credential, config)

        t1 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)

        dp1_s1 = MagicMock(time_stamp=t2, total=2.0, average=None, minimum=None, maximum=None, count=None)
        dp2_s1 = MagicMock(time_stamp=t1, total=1.0, average=None, minimum=None, maximum=None, count=None)
        dp1_s2 = MagicMock(time_stamp=t2, total=4.0, average=None, minimum=None, maximum=None, count=None)
        dp2_s2 = MagicMock(time_stamp=t1, total=2.0, average=None, minimum=None, maximum=None, count=None)

        ts1 = MagicMock(data=[dp1_s1, dp2_s1])
        ts2 = MagicMock(data=[dp1_s2, dp2_s2])
        metric = MagicMock(timeseries=[ts1, ts2], unit="Count")
        response = MagicMock(value=[metric])

        collector._monitor_client = MagicMock()
        collector._monitor_client.metrics.list.return_value = response

        result = collector._collect_metric(
            resource_id="/subscriptions/test/resource",
            metric_name=MetricName.REQUESTS,
            aggregation=AggregationType.TOTAL,
            start_time=t1,
            end_time=t2,
        )

        assert result is not None
        assert result.timestamps == [t1, t2]
        assert result.values == [3.0, 6.0]

    def test_collect_metric_aggregates_average_by_timestamp_sorted(
        self,
        mock_credential,
        config,
    ):
        """AVERAGE aggregation should average values across series per timestamp."""
        with patch('ptu_advisor.metrics.collector.get_subscription_id', return_value="test-sub"):
            with patch('ptu_advisor.metrics.collector.MonitorManagementClient'):
                with patch('ptu_advisor.metrics.collector.CognitiveServicesManagementClient'):
                    collector = MetricsCollector(mock_credential, config)

        t1 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)

        dp1_s1 = MagicMock(time_stamp=t2, total=None, average=200.0, minimum=None, maximum=None, count=None)
        dp2_s1 = MagicMock(time_stamp=t1, total=None, average=100.0, minimum=None, maximum=None, count=None)
        dp1_s2 = MagicMock(time_stamp=t2, total=None, average=100.0, minimum=None, maximum=None, count=None)
        dp2_s2 = MagicMock(time_stamp=t1, total=None, average=300.0, minimum=None, maximum=None, count=None)

        ts1 = MagicMock(data=[dp1_s1, dp2_s1])
        ts2 = MagicMock(data=[dp1_s2, dp2_s2])
        metric = MagicMock(timeseries=[ts1, ts2], unit="Milliseconds")
        response = MagicMock(value=[metric])

        collector._monitor_client = MagicMock()
        collector._monitor_client.metrics.list.return_value = response

        result = collector._collect_metric(
            resource_id="/subscriptions/test/resource",
            metric_name=MetricName.TIME_TO_FIRST_BYTE,
            aggregation=AggregationType.AVERAGE,
            start_time=t1,
            end_time=t2,
        )

        assert result is not None
        assert result.timestamps == [t1, t2]
        assert result.values == [200.0, 150.0]

    def test_collect_metric_records_missing_diagnostic(self, mock_credential, config):
        """No points should produce a missing diagnostic entry."""
        with patch('ptu_advisor.metrics.collector.get_subscription_id', return_value="test-sub"):
            with patch('ptu_advisor.metrics.collector.MonitorManagementClient'):
                with patch('ptu_advisor.metrics.collector.CognitiveServicesManagementClient'):
                    collector = MetricsCollector(mock_credential, config)

        collector._monitor_client = MagicMock()
        collector._monitor_client.metrics.list.return_value = MagicMock(value=[])

        result = collector._collect_metric(
            resource_id="/subscriptions/test/resource",
            metric_name=MetricName.REQUESTS,
            aggregation=AggregationType.TOTAL,
            start_time=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc),
        )

        assert result is None
        diagnostics = collector.get_diagnostics()
        assert diagnostics
        metric_items = diagnostics["metrics"]
        assert metric_items
        assert metric_items[-1]["status"] == "missing"

    def test_collect_emits_missing_metric_warning(self, mock_credential):
        """collect() should log info for missing metrics."""
        config = AnalysisConfig(
            resource_group="test-rg",
            workspace="test-workspace",
            deployment="",
            subscription_id="test-subscription",
            lookback_days=7,
        )
        with patch('ptu_advisor.metrics.collector.get_subscription_id', return_value="test-sub"):
            with patch('ptu_advisor.metrics.collector.MonitorManagementClient'):
                with patch('ptu_advisor.metrics.collector.CognitiveServicesManagementClient'):
                    collector = MetricsCollector(mock_credential, config)

        collector._collect_metric = MagicMock(return_value=None)
        collector._collect_percentile_metric = MagicMock(return_value=None)

        with patch("ptu_advisor.metrics.collector.logger") as mock_logger:
            collector.collect()

        assert mock_logger.info.call_count > 0
        assert any("No data for metric" in str(call) for call in mock_logger.info.call_args_list)


class TestTimeSeries:
    """Tests for TimeSeries data structure."""
    
    def test_empty_time_series(self):
        """Test empty time series handling."""
        ts = TimeSeries(
            timestamps=[],
            values=[],
            metric_name="test",
        )
        
        assert ts.mean == 0.0
        assert ts.std == 0.0
        assert ts.cv == 0.0
        assert ts.min == 0.0
        assert ts.max == 0.0
        assert ts.total == 0.0
    
    def test_time_series_statistics(self):
        """Test time series statistical calculations."""
        ts = TimeSeries(
            timestamps=[datetime.now(timezone.utc) for _ in range(5)],
            values=[10.0, 20.0, 30.0, 40.0, 50.0],
            metric_name="test",
        )
        
        assert ts.mean == 30.0
        assert ts.min == 10.0
        assert ts.max == 50.0
        assert ts.total == 150.0
        assert ts.p50 == 30.0
    
    def test_coefficient_of_variation(self):
        """Test CV calculation."""
        # Constant values should have CV = 0
        ts_constant = TimeSeries(
            timestamps=[datetime.now(timezone.utc) for _ in range(5)],
            values=[10.0, 10.0, 10.0, 10.0, 10.0],
            metric_name="test",
        )
        
        assert ts_constant.cv == 0.0
        
        # Variable values should have positive CV
        ts_variable = TimeSeries(
            timestamps=[datetime.now(timezone.utc) for _ in range(5)],
            values=[10.0, 20.0, 30.0, 40.0, 50.0],
            metric_name="test",
        )
        
        assert ts_variable.cv > 0
    
    def test_zero_percentage(self):
        """Test zero percentage calculation."""
        ts = TimeSeries(
            timestamps=[datetime.now(timezone.utc) for _ in range(10)],
            values=[0, 0, 10, 20, 0, 30, 0, 40, 50, 0],
            metric_name="test",
        )
        
        assert ts.zero_percentage == 0.5  # 5 out of 10 are zero
        assert ts.non_zero_count == 5
