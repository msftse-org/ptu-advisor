"""Tests for prompt-cache impact calculations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ptu_advisor.cost.cache import (
    build_cache_impact,
    calculate_cache_aware_spillover,
    generate_cache_aware_cost_curves,
)
from ptu_advisor.metrics.models import TimeSeries


def _series(values: list[float], name: str, offsets: list[int] | None = None) -> TimeSeries:
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    offsets = offsets or list(range(len(values)))
    return TimeSeries(
        timestamps=[base + timedelta(minutes=offset) for offset in offsets],
        values=values,
        metric_name=name,
    )


def test_observed_cache_reduces_only_prompt_utilization() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([200.0], "prompt"),
        completion_tokens=_series([20.0], "completion"),
        cache_match_rate=_series([0.5], "cache"),
        active_tokens=None,
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
    )

    assert impact.source == "observed"
    assert impact.quality == "good"
    assert impact.applied is True
    assert impact.match_rate_pct == [50.0]
    assert impact.cached_prompt_tokens == [100.0]
    assert impact.active_prompt_tokens == [100.0]
    assert impact.raw_normalized_tpm == [280.0]
    assert impact.adjusted_normalized_tpm == [180.0]


def test_active_tokens_infers_cached_prompt_volume() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([200.0], "prompt"),
        completion_tokens=_series([20.0], "completion"),
        cache_match_rate=None,
        active_tokens=_series([120.0], "active"),
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
    )

    assert impact.source == "inferred"
    assert impact.match_rate_pct == [50.0]
    assert impact.cached_prompt_tokens == [100.0]


def test_active_tokens_fills_missing_direct_cache_intervals() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([200.0, 200.0], "prompt"),
        completion_tokens=_series([20.0, 20.0], "completion"),
        cache_match_rate=_series([0.5], "cache", offsets=[0]),
        active_tokens=_series([120.0], "active", offsets=[1]),
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
    )

    assert impact.source == "mixed"
    assert impact.coverage_pct == 100.0
    assert impact.match_rate_pct == [50.0, 50.0]


def test_direct_cache_disagreement_with_active_tokens_is_disclosed() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([200.0], "prompt"),
        completion_tokens=_series([20.0], "completion"),
        cache_match_rate=_series([0.8], "cache"),
        active_tokens=_series([120.0], "active"),
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
    )

    assert impact.match_rate_pct == [80.0]
    assert impact.validation_warnings
    assert "disagreed" in impact.validation_warnings[0]


@pytest.mark.parametrize("active", [10.0, 221.0, float("nan"), float("inf")])
def test_active_tokens_outside_documented_bounds_are_unavailable(active: float) -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([200.0], "prompt"),
        completion_tokens=_series([20.0], "completion"),
        cache_match_rate=None,
        active_tokens=_series([active], "active"),
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
    )

    assert impact.source == "unavailable"
    assert impact.quality == "unavailable"
    assert impact.applied is False
    assert impact.coverage_pct == 0.0
    assert impact.match_rate_pct == [None]
    assert impact.adjusted_normalized_tpm == impact.raw_normalized_tpm


def test_partial_coverage_uses_zero_benefit_for_missing_intervals() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([100.0, 100.0], "prompt", offsets=[0, 1]),
        completion_tokens=_series([10.0, 10.0], "completion", offsets=[0, 1]),
        cache_match_rate=_series([0.5], "cache", offsets=[0]),
        active_tokens=None,
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
    )

    assert impact.quality == "partial"
    assert impact.coverage_pct == 50.0
    assert impact.match_rate_pct == [50.0, None]
    assert impact.cached_prompt_tokens == [50.0, 0.0]
    assert impact.adjusted_normalized_tpm == [90.0, 140.0]


def test_limited_coverage_does_not_change_primary_calculation() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([100.0, 100.0, 100.0], "prompt"),
        completion_tokens=_series([10.0, 10.0, 10.0], "completion"),
        cache_match_rate=_series([0.9], "cache", offsets=[0]),
        active_tokens=None,
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
    )

    assert impact.quality == "limited"
    assert impact.applied is False
    assert impact.adjusted_normalized_tpm == impact.raw_normalized_tpm


def test_conservative_aggregate_can_apply_valid_cache_below_half_coverage() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([100.0], "prompt"),
        completion_tokens=_series([10.0], "completion"),
        cache_match_rate=_series([0.2], "cache"),
        active_tokens=None,
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
        coverage_pct_override=40.0,
        missing_evidence_as_zero=True,
    )

    assert impact.quality == "limited"
    assert impact.applied is True
    assert impact.adjusted_normalized_tpm == [120.0]


def test_manual_override_is_applied_and_labeled() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([100.0, 200.0], "prompt"),
        completion_tokens=_series([10.0, 20.0], "completion"),
        cache_match_rate=None,
        active_tokens=None,
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
        cache_mode="override",
        override_pct=40.0,
    )

    assert impact.source == "override"
    assert impact.quality == "good"
    assert impact.match_rate_pct == [40.0, 40.0]
    assert impact.coverage_pct == 100.0


def test_disabled_mode_ignores_observed_cache() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([100.0], "prompt"),
        completion_tokens=_series([10.0], "completion"),
        cache_match_rate=_series([0.8], "cache"),
        active_tokens=None,
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
        cache_mode="disabled",
    )

    assert impact.source == "disabled"
    assert impact.applied is False
    assert impact.adjusted_normalized_tpm == impact.raw_normalized_tpm


def test_foundry_documented_cache_sizing_example() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([200_000.0], "prompt"),
        completion_tokens=_series([20_000.0], "completion"),
        cache_match_rate=_series([0.5], "cache"),
        active_tokens=None,
        output_multiplier=8,
        input_tpm_per_ptu=3_400,
        min_ptu=15,
        ptu_increment=5,
    )

    assert impact.raw_normalized_tpm == [360_000.0]
    assert impact.adjusted_normalized_tpm == [260_000.0]
    assert impact.no_cache_recommended_ptu == 110
    assert impact.cache_aware_recommended_ptu == 80
    assert impact.ptu_avoided == 30


def test_override_requires_rate() -> None:
    with pytest.raises(ValueError, match="override_pct"):
        build_cache_impact(
            prompt_tokens=_series([100.0], "prompt"),
            completion_tokens=_series([10.0], "completion"),
            cache_match_rate=None,
            active_tokens=None,
            output_multiplier=4,
            input_tpm_per_ptu=100,
            min_ptu=1,
            ptu_increment=1,
            cache_mode="override",
        )


def test_override_rejects_out_of_range_rate() -> None:
    with pytest.raises(ValueError, match="between 0 and 100"):
        build_cache_impact(
            prompt_tokens=_series([100.0], "prompt"),
            completion_tokens=_series([10.0], "completion"),
            cache_match_rate=None,
            active_tokens=None,
            output_multiplier=4,
            input_tpm_per_ptu=100,
            min_ptu=1,
            ptu_increment=1,
            cache_mode="override",
            override_pct=101.0,
        )


def test_cache_aware_spillover_preserves_fixed_ptu_cost() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([200.0, 200.0], "prompt"),
        completion_tokens=_series([20.0, 20.0], "completion"),
        cache_match_rate=_series([0.5, 0.5], "cache"),
        active_tokens=None,
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
    )

    result = calculate_cache_aware_spillover(
        impact=impact,
        selected_ptu=1,
        ptu_capacity_per_unit=100,
        ptu_hourly_rate=2.0,
        reservation_discount=0.5,
        payg_input_rate_per_million=2.0,
        payg_output_rate_per_million=8.0,
    )

    assert result["ptu_monthly_cost"] == pytest.approx(720.0)
    assert result["avg_spillover_normalized_tpm"] == pytest.approx(80.0)
    assert result["spillover_input_tokens_monthly"] == pytest.approx(3_840_000.0)
    assert result["spillover_output_tokens_monthly"] == pytest.approx(384_000.0)
    assert result["spillover_cost"] == pytest.approx(10.752)


def test_missing_completion_series_disables_cache_adjustment() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([200.0], "prompt"),
        completion_tokens=None,
        cache_match_rate=_series([0.5], "cache"),
        active_tokens=None,
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
    )

    assert impact.applied is False
    assert impact.raw_normalized_tpm == []
    assert impact.adjusted_normalized_tpm == []


def test_misaligned_completion_series_disables_cache_adjustment() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([200.0, 200.0], "prompt", offsets=[0, 1]),
        completion_tokens=_series([20.0], "completion", offsets=[0]),
        cache_match_rate=_series([0.5, 0.5], "cache", offsets=[0, 1]),
        active_tokens=None,
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
    )

    assert impact.applied is False
    assert impact.adjusted_normalized_tpm == []


def test_limited_coverage_does_not_reduce_spillover_input() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([100.0, 100.0, 100.0], "prompt"),
        completion_tokens=_series([0.0, 0.0, 0.0], "completion"),
        cache_match_rate=_series([0.9], "cache", offsets=[0]),
        active_tokens=None,
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
    )

    result = calculate_cache_aware_spillover(
        impact=impact,
        selected_ptu=1,
        ptu_capacity_per_unit=50,
        ptu_hourly_rate=1.0,
        reservation_discount=1.0,
        payg_input_rate_per_million=2.0,
        payg_output_rate_per_million=8.0,
    )

    assert impact.applied is False
    assert result["spillover_input_tokens_monthly"] == pytest.approx(50 * 43_200)


def test_cache_token_totals_scale_by_metric_interval() -> None:
    impact = build_cache_impact(
        prompt_tokens=_series([100.0, 100.0], "prompt"),
        completion_tokens=_series([0.0, 0.0], "completion"),
        cache_match_rate=_series([0.5, 0.5], "cache"),
        active_tokens=None,
        output_multiplier=4,
        input_tpm_per_ptu=100,
        min_ptu=1,
        ptu_increment=1,
        interval_minutes=5,
    )

    assert impact.total_cached_prompt_tokens == pytest.approx(500.0)
    assert impact.total_active_prompt_tokens == pytest.approx(500.0)


def test_cache_aware_curve_uses_distinct_payg_and_spillover_slopes() -> None:
    curve, break_even, upper_break_even = generate_cache_aware_cost_curves(
        selected_ptu=1,
        ptu_capacity_raw_tpm=100.0,
        ptu_monthly_cost=100.0,
        payg_rate_per_raw_million=10.0,
        spillover_rate_per_raw_million=20.0,
        max_tpm=400.0,
        num_points=5,
    )

    # Above capacity, hybrid rises twice as fast as PAYG, so legacy parallel-line
    # math would be incorrect. At 200 TPM: PAYG=86.4, hybrid=186.4.
    row = curve.iloc[2]
    assert row["payg_monthly"] == pytest.approx(86.4)
    assert row["ptu_spill_monthly"] == pytest.approx(186.4)
    assert break_even is None
    assert upper_break_even is None


def test_cache_aware_curve_reports_two_break_even_bounds() -> None:
    curve, lower, upper = generate_cache_aware_cost_curves(
        selected_ptu=1,
        ptu_capacity_raw_tpm=100.0,
        ptu_monthly_cost=20.0,
        payg_rate_per_raw_million=10.0,
        spillover_rate_per_raw_million=20.0,
        max_tpm=400.0,
        num_points=401,
    )

    assert not curve.empty
    assert lower is not None
    assert upper is not None
    assert lower < 100 < upper


def test_cache_aware_curve_does_not_miss_narrow_break_even_range() -> None:
    _curve, lower, upper = generate_cache_aware_cost_curves(
        selected_ptu=1,
        ptu_capacity_raw_tpm=100.0,
        ptu_monthly_cost=43.1,
        payg_rate_per_raw_million=10.0,
        spillover_rate_per_raw_million=20.0,
        max_tpm=400.0,
    )

    assert lower == pytest.approx(99.7685, rel=1e-4)
    assert upper == pytest.approx(100.2315, rel=1e-4)


def test_cache_aware_curve_extends_to_upper_crossing() -> None:
    curve, lower, upper = generate_cache_aware_cost_curves(
        selected_ptu=1,
        ptu_capacity_raw_tpm=100.0,
        ptu_monthly_cost=20.0,
        payg_rate_per_raw_million=10.0,
        spillover_rate_per_raw_million=20.0,
        max_tpm=110.0,
    )

    assert lower is not None
    assert upper is not None
    assert curve["sustained_tpm"].max() >= upper


def test_cache_aware_curve_ignores_floating_point_slope_noise() -> None:
    curve, lower, upper = generate_cache_aware_cost_curves(
        selected_ptu=1,
        ptu_capacity_raw_tpm=100.0,
        ptu_monthly_cost=100.0,
        payg_rate_per_raw_million=10.000000000001,
        spillover_rate_per_raw_million=10.0,
        max_tpm=400.0,
    )

    assert lower is None
    assert upper is None
    assert curve["sustained_tpm"].max() == pytest.approx(400.0)
