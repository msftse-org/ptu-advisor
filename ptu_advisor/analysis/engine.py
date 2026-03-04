"""Decision engine for PTU recommendations."""

from __future__ import annotations

from datetime import datetime

from ptu_advisor.config import AnalysisConfig
from ptu_advisor.metrics.models import (
    AnalysisResult,
    DeploymentMetrics,
    DimensionScore,
    DimensionScores,
    Recommendation,
)
from ptu_advisor.analysis.dimensions import (
    CapacityPressureAnalyzer,
    LatencySensitivityAnalyzer,
    LoadPredictabilityAnalyzer,
    WorkloadShapeAnalyzer,
)


class DecisionEngine:
    """
    Main decision engine for PTU recommendations.
    
    Analyzes deployment metrics across four dimensions and produces
    a final recommendation with detailed explanations.
    """
    
    def __init__(self, config: AnalysisConfig) -> None:
        """Initialize the decision engine with configuration."""
        self.config = config
        self.thresholds = config.thresholds
        
        # Initialize dimension analyzers
        self.workload_analyzer = WorkloadShapeAnalyzer(config)
        self.capacity_analyzer = CapacityPressureAnalyzer(config)
        self.latency_analyzer = LatencySensitivityAnalyzer(config)
        self.predictability_analyzer = LoadPredictabilityAnalyzer(config)
    
    def analyze(self, metrics: DeploymentMetrics) -> AnalysisResult:
        """
        Analyze deployment metrics and produce a recommendation.
        
        Args:
            metrics: Collected deployment metrics.
            
        Returns:
            Complete analysis result with recommendation and explanations.
        """
        # Apply business hours filter if configured
        if self.config.business_hours_only:
            metrics = metrics.filter_business_hours(
                start_hour=self.config.business_hours.start_hour,
                end_hour=self.config.business_hours.end_hour,
                weekdays_only=self.config.business_hours.weekdays_only,
            )

        # Analyze each dimension
        workload_result = self.workload_analyzer.analyze(metrics)
        capacity_result = self.capacity_analyzer.analyze(metrics)
        latency_result = self.latency_analyzer.analyze(metrics)
        predictability_result = self.predictability_analyzer.analyze(metrics)
        
        # Combine into dimension scores
        dimensions = DimensionScores(
            workload_shape=workload_result,
            capacity_pressure=capacity_result,
            latency_sensitivity=latency_result,
            load_predictability=predictability_result,
        )
        
        # Make the decision
        recommendation = self._decide(dimensions)
        
        # Calculate overall confidence
        confidence = self._calculate_confidence(dimensions, metrics)
        
        # Generate explanations
        summary = self._generate_summary(recommendation, dimensions)
        explanation = self._generate_explanation(recommendation, dimensions)
        what_would_change = self._generate_what_would_change(recommendation, dimensions)
        
        # Data quality assessment
        data_quality = self._assess_data_quality(metrics)
        
        # Analysis period string
        analysis_period = (
            f"{self.config.lookback_days} days "
            f"({metrics.start_time.strftime('%b %d')} - "
            f"{metrics.end_time.strftime('%b %d, %Y')})"
        )
        
        return AnalysisResult(
            recommendation=recommendation,
            dimensions=dimensions,
            confidence=confidence,
            summary=summary,
            explanation=explanation,
            what_would_change=what_would_change,
            data_quality=data_quality,
            analysis_period=analysis_period,
        )
    
    def _decide(self, dimensions: DimensionScores) -> Recommendation:
        """
        Make the final PTU recommendation based on dimension scores.
        
        Decision logic:
        - ≥3 positive dimensions → PTU Recommended
        - 2 positive dimensions → Borderline
        - <2 positive dimensions → PTU Not Recommended
        """
        positive_count = dimensions.positive_count
        
        # Check for insufficient data
        insufficient_count = sum(
            1 for d in dimensions.all_dimensions 
            if d.score == DimensionScore.INSUFFICIENT
        )
        
        if insufficient_count >= 2:
            return Recommendation.BORDERLINE
        
        if positive_count >= self.thresholds.min_positive_for_ptu:
            return Recommendation.PTU_RECOMMENDED
        elif positive_count >= self.thresholds.min_positive_for_borderline:
            return Recommendation.BORDERLINE
        else:
            return Recommendation.PTU_NOT_RECOMMENDED
    
    def _calculate_confidence(
        self, 
        dimensions: DimensionScores, 
        metrics: DeploymentMetrics
    ) -> float:
        """Calculate overall confidence in the recommendation."""
        # Average dimension confidence
        dim_confidence = dimensions.average_confidence
        
        # Data quantity factor
        data_points = len(metrics.timestamps)
        data_factor = min(1.0, data_points / self.thresholds.min_data_points)
        
        # Analysis period factor — use actual data span, not configured lookback
        actual_days = (metrics.end_time - metrics.start_time).total_seconds() / 86400
        days_factor = min(1.0, actual_days / self.thresholds.min_days_for_confidence)
        
        # Combine factors
        return dim_confidence * 0.5 + data_factor * 0.3 + days_factor * 0.2
    
    def _generate_summary(
        self, 
        recommendation: Recommendation, 
        dimensions: DimensionScores
    ) -> str:
        """Generate a one-sentence summary of the recommendation."""
        positive_dims = [d.name for d in dimensions.all_dimensions if d.is_positive]
        
        if recommendation == Recommendation.PTU_RECOMMENDED:
            return (
                f"PTU is recommended based on strong signals from "
                f"{', '.join(positive_dims)}."
            )
        elif recommendation == Recommendation.BORDERLINE:
            return (
                f"Results are mixed. Consider a load test to validate whether "
                f"PTU would provide measurable benefits."
            )
        else:
            return (
                f"PTU is not recommended. Your current workload characteristics "
                f"are better suited for PAYG."
            )
    
    def _generate_explanation(
        self, 
        recommendation: Recommendation, 
        dimensions: DimensionScores
    ) -> str:
        """Generate a detailed explanation of the recommendation."""
        lines = []
        
        # Header based on recommendation
        if recommendation == Recommendation.PTU_RECOMMENDED:
            lines.append(
                "Your deployment shows characteristics that align well with PTU's "
                "value proposition: predictable throughput needs, capacity pressure, "
                "or latency sensitivity."
            )
        elif recommendation == Recommendation.BORDERLINE:
            lines.append(
                "Your deployment shows mixed signals. Some dimensions favor PTU "
                "while others suggest PAYG may be sufficient."
            )
        else:
            lines.append(
                "Your deployment's usage patterns suggest PAYG is the better choice. "
                "PTU is designed for consistent, predictable workloads at scale."
            )
        
        lines.append("\n\n**Dimension Analysis:**\n")
        
        # Add each dimension's summary
        for dim in dimensions.all_dimensions:
            emoji = {
                DimensionScore.POSITIVE: "✅",
                DimensionScore.NEUTRAL: "⚖️",
                DimensionScore.NEGATIVE: "❌",
                DimensionScore.INSUFFICIENT: "❓",
            }.get(dim.score, "")
            
            lines.append(f"\n**{emoji} {dim.name}**: {dim.summary}")
        
        return "".join(lines)
    
    def _generate_what_would_change(
        self, 
        recommendation: Recommendation, 
        dimensions: DimensionScores
    ) -> str:
        """Generate explanation of what would change the recommendation."""
        changes = []
        
        if recommendation == Recommendation.PTU_RECOMMENDED:
            # What would make us not recommend PTU
            for dim in dimensions.all_dimensions:
                if dim.is_positive:
                    changes.append(
                        f"• If **{dim.name}** became less favorable (e.g., "
                        f"more variable workload, less throttling)"
                    )
        
        elif recommendation == Recommendation.PTU_NOT_RECOMMENDED:
            # What would make us recommend PTU
            for dim in dimensions.all_dimensions:
                if not dim.is_positive:
                    if dim.name == "Workload Shape":
                        changes.append(
                            "• If your workload becomes more **consistent** "
                            "(lower variance in token throughput)"
                        )
                    elif dim.name == "Capacity Pressure":
                        changes.append(
                            "• If you start experiencing **more throttling** "
                            "(increased 429 errors)"
                        )
                    elif dim.name == "Latency Sensitivity":
                        changes.append(
                            "• If **latency becomes critical** for your use case "
                            "(lower latency requirements)"
                        )
                    elif dim.name == "Load Predictability":
                        changes.append(
                            "• If usage becomes **more sustained** "
                            "(less idle time, more consistent daily patterns)"
                        )
        
        else:  # Borderline
            changes.append(
                "• Consider running a **load test** to observe behavior "
                "under production-like conditions"
            )
            changes.append(
                "• Monitor for another week to gather more data and "
                "increase confidence"
            )
            changes.append(
                "• Evaluate whether the **cost difference** between PTU and "
                "PAYG justifies the switch given current metrics"
            )
        
        if changes:
            return "\n".join(changes)
        return "No specific changes identified."
    
    def _assess_data_quality(self, metrics: DeploymentMetrics) -> str:
        """Assess the quality of collected data."""
        data_points = len(metrics.timestamps)
        days = self.config.lookback_days
        
        if data_points < 50:
            return (
                f"⚠️ Limited data: Only {data_points} data points collected. "
                f"Recommendation confidence is reduced. Consider analyzing "
                f"a longer time period."
            )
        elif data_points < 200:
            return (
                f"📊 Moderate data: {data_points} data points over {days} days. "
                f"Recommendation is reasonably confident."
            )
        else:
            return (
                f"✅ Good data: {data_points} data points over {days} days. "
                f"Recommendation is based on comprehensive data."
            )
