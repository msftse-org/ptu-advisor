"""Metrics collector for Azure AI Foundry deployments."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from azure.core.credentials import TokenCredential
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.mgmt.monitor import MonitorManagementClient

from ptu_advisor.auth import get_resource_id, get_subscription_id
from ptu_advisor.config import AnalysisConfig
from ptu_advisor.metrics.models import (
    AggregationType,
    DeploymentInfo,
    DeploymentMetrics,
    MetricName,
    TimeSeries,
)


class MetricsCollectionError(Exception):
    """Raised when metrics collection fails."""
    pass


@dataclass
class MetricDiagnostic:
    """Structured diagnostics for a metric collection attempt."""

    metric_name: str
    aggregation: str
    filter: Optional[str]
    status: str
    message: str
    series_count: int = 0
    point_count: int = 0


class MetricsCollector:
    """Collects metrics from Azure Monitor for Foundry deployments."""
    
    def __init__(self, credential: TokenCredential, config: AnalysisConfig) -> None:
        """
        Initialize the metrics collector.
        
        Args:
            credential: Azure credential for API calls.
            config: Analysis configuration.
        """
        self.credential = credential
        self.config = config
        self.subscription_id = get_subscription_id(credential, config.subscription_id)
        self._diagnostics: List[MetricDiagnostic] = []
        
        # Initialize Azure clients
        self._monitor_client = MonitorManagementClient(credential, self.subscription_id)
        self._cog_client = CognitiveServicesManagementClient(credential, self.subscription_id)

    def get_diagnostics(self) -> Dict[str, Any]:
        """Return structured collection diagnostics.

        The result contains a ``context`` dict (resource_id, subscription,
        resource_group, workspace, deployment, lookback_days) and a ``metrics``
        list with per-metric diagnostic entries.
        """
        resource_id = get_resource_id(
            subscription_id=self.subscription_id,
            resource_group=self.config.resource_group,
            workspace=self.config.workspace,
        )
        return {
            "context": {
                "resource_id": resource_id,
                "subscription_id": self.subscription_id,
                "resource_group": self.config.resource_group,
                "workspace": self.config.workspace,
                "deployment": self.config.deployment,
                "lookback_days": self.config.lookback_days,
            },
            "metrics": [asdict(item) for item in self._diagnostics],
        }

    def _record_diagnostic(
        self,
        metric_name: str,
        aggregation: AggregationType,
        filter_str: Optional[str],
        status: str,
        message: str,
        series_count: int = 0,
        point_count: int = 0,
    ) -> None:
        self._diagnostics.append(
            MetricDiagnostic(
                metric_name=metric_name,
                aggregation=aggregation.value,
                filter=filter_str,
                status=status,
                message=message,
                series_count=series_count,
                point_count=point_count,
            )
        )

    def _warn_missing_metric(self, metric_name: str, context: str) -> None:
        logger.info(
            "No data for metric '%s' (%s) — deployment may have no traffic in the lookback window.",
            metric_name,
            context,
        )
    
    def collect(self) -> DeploymentMetrics:
        """
        Collect all metrics for the configured deployment.
        
        Returns:
            DeploymentMetrics containing all collected time series.
            
        Raises:
            MetricsCollectionError: If metrics collection fails.
        """
        try:
            # Get deployment info (only if a specific deployment is targeted)
            if self.config.deployment:
                deployment_info = self._get_deployment_info()
                deploy_name = self.config.deployment
                model_name = deployment_info.model
            else:
                deployment_info = None
                deploy_name = f"{self.config.workspace} (all deployments)"
                model_name = "aggregated"
            
            # Calculate time range
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=self.config.lookback_days)
            
            # Build resource ID for the workspace (metrics are at account level)
            resource_id = get_resource_id(
                subscription_id=self.subscription_id,
                resource_group=self.config.resource_group,
                workspace=self.config.workspace,
            )
            
            # Collect metrics
            metrics = DeploymentMetrics(
                deployment_name=deploy_name,
                model_name=model_name,
                start_time=start_time,
                end_time=end_time,
            )
            if deployment_info:
                metrics.deployment_info = deployment_info
            
            # Define metrics to collect with their aggregation types.
            # Only metrics that support the ModelDeploymentName dimension
            # are included here.  Account-level-only metrics (SuccessfulCalls,
            # Ratelimit) are handled separately below.
            metric_definitions = [
                (MetricName.REQUESTS, AggregationType.TOTAL, "requests_per_minute"),
                (MetricName.PROMPT_TOKENS, AggregationType.TOTAL, "prompt_tokens"),
                (MetricName.COMPLETION_TOKENS, AggregationType.TOTAL, "completion_tokens"),
                (MetricName.TOTAL_TOKENS, AggregationType.TOTAL, "tokens_per_minute"),
                (MetricName.TIME_TO_FIRST_BYTE, AggregationType.AVERAGE, "time_to_first_byte_p50"),
                (MetricName.PTU_UTILIZATION, AggregationType.AVERAGE, "ptu_utilization"),
            ]
            
            # Collect each metric
            for metric_name, agg_type, attr_name in metric_definitions:
                try:
                    time_series = self._collect_metric(
                        resource_id=resource_id,
                        metric_name=metric_name,
                        aggregation=agg_type,
                        start_time=start_time,
                        end_time=end_time,
                    )
                    setattr(metrics, attr_name, time_series)

                    if time_series is None:
                        self._warn_missing_metric(metric_name.value, attr_name)
                    
                    # Store timestamps from first successful metric
                    if not metrics.timestamps and time_series:
                        metrics.timestamps = list(time_series.timestamps)
                        
                except Exception as e:
                    if self.config.verbose:
                        print(f"Warning: Failed to collect {metric_name.value}: {e}")

            # ── Dimension name fallback ──
            # If all metrics returned None the filter dimension
            # 'ModelDeploymentName' may not exist on this resource.
            # Retry the first metric without the deployment filter to
            # check whether data exists at the account level.
            all_none = all(
                getattr(metrics, defn[2]) is None for defn in metric_definitions
            )
            if all_none and self.config.deployment:
                probe = self._collect_metric(
                    resource_id=resource_id,
                    metric_name=MetricName.REQUESTS,
                    aggregation=AggregationType.TOTAL,
                    start_time=start_time,
                    end_time=end_time,
                    skip_deployment_filter=True,
                )
                if probe is not None:
                    logger.warning(
                        "Metrics exist at the account level but not for "
                        "deployment '%s'. The deployment may use a different "
                        "dimension name or had no traffic in the last %d days.",
                        self.config.deployment,
                        self.config.lookback_days,
                    )
                    self._record_diagnostic(
                        metric_name="(probe)",
                        aggregation=AggregationType.TOTAL,
                        filter_str=None,
                        status="fallback_probe",
                        message=(
                            f"Account-level data exists ({probe.non_zero_count} "
                            f"non-zero points) but deployment filter "
                            f"'ModelDeploymentName eq \'{self.config.deployment}\'' "
                            f"matched nothing. Verify the deployment name or "
                            f"check that there was traffic in the last "
                            f"{self.config.lookback_days} days."
                        ),
                        series_count=1,
                        point_count=len(probe.timestamps),
                    )
                else:
                    # Probe what metrics the resource actually exposes.
                    available = self._list_available_metrics(resource_id)
                    logger.warning(
                        "No metrics found at the account level for '%s'. "
                        "Available metric definitions on resource: %s",
                        self.config.workspace,
                        ", ".join(available) if available else "(none)",
                    )
                    self._record_diagnostic(
                        metric_name="(account_probe)",
                        aggregation=AggregationType.TOTAL,
                        filter_str=None,
                        status="account_empty",
                        message=(
                            f"No data at the account level for resource "
                            f"'{self.config.workspace}'. Resource ID: {resource_id}. "
                            f"Available metrics on resource: "
                            f"{', '.join(available) if available else '(none)'}. "
                            f"If the expected metrics are missing, diagnostic "
                            f"settings may not be enabled or the resource has "
                            f"had no traffic in the last "
                            f"{self.config.lookback_days} days."
                        ),
                        series_count=0,
                        point_count=0,
                    )
            
            # ── Throttled requests (HTTP 429) ──
            # The platform "Ratelimit" metric reports rate-limit *token*
            # counts (values in millions), NOT throttled request counts.
            # Instead, query AzureOpenAIRequests filtered to StatusCode 429.
            try:
                metrics.throttled_requests = self._collect_metric(
                    resource_id=resource_id,
                    metric_name=MetricName.REQUESTS,
                    aggregation=AggregationType.TOTAL,
                    start_time=start_time,
                    end_time=end_time,
                    extra_filter="StatusCode eq '429'",
                )
                if metrics.throttled_requests is None:
                    self._warn_missing_metric(MetricName.REQUESTS.value, "throttled_requests")
            except Exception as e:
                if self.config.verbose:
                    print(f"Warning: Failed to collect throttled requests: {e}")
            
            # ── Normalize TOTAL-aggregated metrics to per-minute rates ──
            # Azure Monitor returns sum-over-interval for Total aggregation.
            # E.g. with a 60-min interval a value of 600,000 means 600K
            # tokens in that hour = 10,000 TPM.  Divide by the interval so
            # all downstream code sees true per-minute values.
            interval = self.config.aggregation_interval_minutes
            if interval > 1:
                for attr in (
                    "requests_per_minute",
                    "prompt_tokens",
                    "completion_tokens",
                    "tokens_per_minute",
                    "throttled_requests",
                ):
                    ts: Optional[TimeSeries] = getattr(metrics, attr, None)
                    if ts is not None:
                        setattr(
                            metrics,
                            attr,
                            TimeSeries(
                                timestamps=ts.timestamps,
                                values=[v / interval for v in ts.values],
                                metric_name=ts.metric_name,
                                unit=ts.unit,
                            ),
                        )

            # ── Successful requests (derived) ──
            # SuccessfulCalls is account-level only (no ModelDeploymentName
            # dimension).  Derive successful = total - throttled instead.
            if metrics.requests_per_minute:
                if metrics.throttled_requests:
                    throttled_map = {
                        t.isoformat(): v
                        for t, v in zip(
                            metrics.throttled_requests.timestamps,
                            metrics.throttled_requests.values,
                        )
                    }
                    success_vals = [
                        max(0.0, total - throttled_map.get(ts.isoformat(), 0.0))
                        for ts, total in zip(
                            metrics.requests_per_minute.timestamps,
                            metrics.requests_per_minute.values,
                        )
                    ]
                else:
                    success_vals = list(metrics.requests_per_minute.values)
                
                metrics.successful_requests = TimeSeries(
                    timestamps=list(metrics.requests_per_minute.timestamps),
                    values=success_vals,
                    metric_name="SuccessfulRequests",
                    unit=metrics.requests_per_minute.unit if metrics.requests_per_minute else "",
                )
            
            # Collect latency percentiles (P95, P99)
            metrics.time_to_first_byte_p95 = self._collect_percentile_metric(
                resource_id=resource_id,
                metric_name=MetricName.TIME_TO_FIRST_BYTE,
                percentile=95,
                start_time=start_time,
                end_time=end_time,
            )
            if metrics.time_to_first_byte_p95 is None:
                self._warn_missing_metric(MetricName.TIME_TO_FIRST_BYTE.value, "time_to_first_byte_p95")
            
            metrics.time_to_first_byte_p99 = self._collect_percentile_metric(
                resource_id=resource_id,
                metric_name=MetricName.TIME_TO_FIRST_BYTE,
                percentile=99,
                start_time=start_time,
                end_time=end_time,
            )
            if metrics.time_to_first_byte_p99 is None:
                self._warn_missing_metric(MetricName.TIME_TO_FIRST_BYTE.value, "time_to_first_byte_p99")
            
            return metrics
            
        except Exception as e:
            raise MetricsCollectionError(
                f"Failed to collect metrics for deployment '{self.config.deployment}': {e}"
            ) from e
    
    def _get_deployment_info(self) -> DeploymentInfo:
        """Get information about the deployment."""
        try:
            deployment = self._cog_client.deployments.get(
                resource_group_name=self.config.resource_group,
                account_name=self.config.workspace,
                deployment_name=self.config.deployment,
            )
            
            props = deployment.properties
            return DeploymentInfo(
                name=deployment.name,
                model=props.model.name if props and props.model else "unknown",
                sku_type=deployment.sku.name if deployment.sku else "unknown",
                sku_capacity=deployment.sku.capacity if deployment.sku else None,
            )
            
        except Exception as e:
            raise MetricsCollectionError(
                f"Failed to get deployment info for '{self.config.deployment}': {e}"
            ) from e
    
    def _collect_metric(
        self,
        resource_id: str,
        metric_name: MetricName,
        aggregation: AggregationType,
        start_time: datetime,
        end_time: datetime,
        extra_filter: Optional[str] = None,
        skip_deployment_filter: bool = False,
    ) -> Optional[TimeSeries]:
        """
        Collect a single metric from Azure Monitor.
        
        Args:
            resource_id: Azure resource ID.
            metric_name: Name of the metric to collect.
            aggregation: Aggregation type.
            start_time: Start of the time range.
            end_time: End of the time range.
            extra_filter: Optional additional OData filter clause
                (e.g. ``StatusCode eq '429'``).  Combined with the
                deployment filter via ``and``.
            
        Returns:
            TimeSeries of the metric values, or None if not available.
        """
        # Calculate interval based on config
        interval = f"PT{self.config.aggregation_interval_minutes}M"
        
        # Build OData filter — use ModelDeploymentName (the correct
        # dimension name for AzureOpenAIRequests, token metrics, etc.).
        filter_parts: List[str] = []
        if self.config.deployment and not skip_deployment_filter:
            filter_parts.append(f"ModelDeploymentName eq '{self.config.deployment}'")
        if extra_filter:
            filter_parts.append(extra_filter)
        filter_str = " and ".join(filter_parts) if filter_parts else None
        
        try:
            # Format ISO 8601 timestamps explicitly — Python 3.9's
            # datetime.isoformat() may produce a space before the UTC offset
            # (e.g. "...+00:00" vs "... 00:00") which Azure Monitor rejects.
            timespan = (
                f"{start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                f"/{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )
            response = self._monitor_client.metrics.list(
                resource_uri=resource_id,
                timespan=timespan,
                interval=interval,
                metricnames=metric_name.value,
                aggregation=aggregation.value,
                filter=filter_str,
            )
            
            # Extract and aggregate time series by timestamp.
            # This avoids duplicate points when Azure returns multiple series
            # (e.g. account-wide queries across deployments/dimensions).
            values_by_timestamp: Dict[datetime, List[float]] = defaultdict(list)
            series_count = 0
            
            for metric in response.value:
                for ts in metric.timeseries:
                    series_count += 1
                    for data_point in ts.data:
                        if data_point.time_stamp:
                            value = self._get_aggregated_value(data_point, aggregation)
                            values_by_timestamp[data_point.time_stamp].append(
                                value if value is not None else 0.0
                            )
            
            if not values_by_timestamp:
                self._record_diagnostic(
                    metric_name=metric_name.value,
                    aggregation=aggregation,
                    filter_str=filter_str,
                    status="missing",
                    message="No data points returned by Azure Monitor",
                )
                return None

            ordered_timestamps = sorted(values_by_timestamp.keys())
            ordered_values: List[float] = []

            for timestamp in ordered_timestamps:
                bucket = values_by_timestamp[timestamp]
                if aggregation in (AggregationType.TOTAL, AggregationType.COUNT):
                    ordered_values.append(float(sum(bucket)))
                elif aggregation == AggregationType.AVERAGE:
                    ordered_values.append(float(sum(bucket) / len(bucket)))
                elif aggregation == AggregationType.MINIMUM:
                    ordered_values.append(float(min(bucket)))
                elif aggregation == AggregationType.MAXIMUM:
                    ordered_values.append(float(max(bucket)))
                else:
                    ordered_values.append(float(sum(bucket)))

            self._record_diagnostic(
                metric_name=metric_name.value,
                aggregation=aggregation,
                filter_str=filter_str,
                status="success",
                message="Metric collected successfully",
                series_count=series_count,
                point_count=len(ordered_timestamps),
            )
            
            return TimeSeries(
                timestamps=ordered_timestamps,
                values=ordered_values,
                metric_name=metric_name.value,
                unit=response.value[0].unit if response.value else "",
            )
            
        except Exception as e:
            self._record_diagnostic(
                metric_name=metric_name.value,
                aggregation=aggregation,
                filter_str=filter_str,
                status="error",
                message=str(e),
            )
            if self.config.verbose:
                print(f"Failed to collect metric {metric_name.value}: {e}")
            return None

    def _list_available_metrics(self, resource_id: str) -> List[str]:
        """Query Azure Monitor for the metric definitions available on *resource_id*.

        Returns a list of metric name strings.  On failure returns an empty list
        so callers can safely include the result in diagnostics.
        """
        try:
            definitions = self._monitor_client.metric_definitions.list(
                resource_uri=resource_id,
            )
            return [d.name.value for d in definitions if d.name]
        except Exception as exc:
            logger.debug("Failed to list metric definitions for %s: %s", resource_id, exc)
            return []
    
    def _collect_percentile_metric(
        self,
        resource_id: str,
        metric_name: MetricName,
        percentile: int,
        start_time: datetime,
        end_time: datetime,
    ) -> Optional[TimeSeries]:
        """
        Collect an estimated percentile metric from Azure Monitor.

        Azure Monitor's standard metrics API does not directly expose arbitrary
        percentiles.  We approximate by collecting AVERAGE and MAXIMUM
        aggregations and interpolating using the z-score for the target
        percentile under a roughly-normal latency assumption.

        Z-scores: P50 ~ 0, P90 ~ 1.28, P95 ~ 1.65, P99 ~ 2.33
        Approximation: Pn ~ AVG + (z / z_max) * (MAX - AVG)
        where z_max ~ 2.5 (approximate z for the observed maximum).
        """
        avg_metric = self._collect_metric(
            resource_id=resource_id,
            metric_name=metric_name,
            aggregation=AggregationType.AVERAGE,
            start_time=start_time,
            end_time=end_time,
        )
        max_metric = self._collect_metric(
            resource_id=resource_id,
            metric_name=metric_name,
            aggregation=AggregationType.MAXIMUM,
            start_time=start_time,
            end_time=end_time,
        )

        if not avg_metric or not max_metric:
            # Fall back to whichever is available
            fallback = avg_metric or max_metric
            if fallback:
                fallback.metric_name = f"{metric_name.value}_P{percentile}"
            return fallback

        # Z-score lookup for common percentiles
        z_scores = {50: 0.0, 90: 1.28, 95: 1.65, 99: 2.33}
        z = z_scores.get(percentile, 1.65)
        z_max = 2.5
        scale = z / z_max

        estimated_values = [
            max(avg_val, avg_val + scale * (max_val - avg_val))
            for avg_val, max_val in zip(avg_metric.values, max_metric.values)
        ]

        return TimeSeries(
            timestamps=avg_metric.timestamps,
            values=estimated_values,
            metric_name=f"{metric_name.value}_P{percentile}",
            unit=avg_metric.unit,
        )
    
    def _get_aggregated_value(self, data_point, aggregation: AggregationType) -> Optional[float]:
        """Extract the correct value based on aggregation type."""
        if aggregation == AggregationType.TOTAL:
            return data_point.total
        elif aggregation == AggregationType.AVERAGE:
            return data_point.average
        elif aggregation == AggregationType.MINIMUM:
            return data_point.minimum
        elif aggregation == AggregationType.MAXIMUM:
            return data_point.maximum
        elif aggregation == AggregationType.COUNT:
            return data_point.count
        return None


def list_workspace_deployments(
    credential: TokenCredential,
    subscription_id: Optional[str],
    resource_group: str,
    workspace: str,
) -> List[DeploymentInfo]:
    """
    List all deployments in a Foundry workspace.
    
    Args:
        credential: Azure credential.
        subscription_id: Optional subscription ID.
        resource_group: Resource group name.
        workspace: Workspace name.
        
    Returns:
        List of DeploymentInfo objects.
    """
    sub_id = get_subscription_id(credential, subscription_id)
    client = CognitiveServicesManagementClient(credential, sub_id)
    
    deployments = []
    
    try:
        for deployment in client.deployments.list(
            resource_group_name=resource_group,
            account_name=workspace,
        ):
            props = deployment.properties
            deployments.append(
                DeploymentInfo(
                    name=deployment.name,
                    model=props.model.name if props and props.model else "unknown",
                    sku_type=deployment.sku.name if deployment.sku else "unknown",
                    sku_capacity=deployment.sku.capacity if deployment.sku else None,
                )
            )
    except Exception as e:
        raise MetricsCollectionError(f"Failed to list deployments: {e}") from e
    
    return deployments
