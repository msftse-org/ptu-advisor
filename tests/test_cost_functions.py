"""Tests for dashboard cost functions: spillover, break-even, cost curves, PTU costs."""

import pytest
import numpy as np

from ptu_advisor.cost.calculator import (
    calculate_spillover_cost,
    calculate_break_even,
    generate_cost_curves,
    calculate_ptu_costs,
)


# ============================================================================
# calculate_spillover_cost
# ============================================================================


class TestCalculateSpilloverCost:
    """Tests for the spillover cost calculation."""

    # Common params
    PTU_CAPACITY = 2500.0  # TPM per PTU
    PTU_HOURLY = 1.0
    PAYG_RATE = 4.75  # per 1K tokens

    def test_basic_calculation(self):
        """Basic spillover with normally distributed TPM."""
        np.random.seed(42)
        tpm_values = list(np.random.normal(50_000, 15_000, 1000))
        result = calculate_spillover_cost(
            tpm_values=tpm_values,
            baseline_percentile=75,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_rate_per_1k=self.PAYG_RATE,
        )
        assert result["baseline_ptu"] >= 15
        assert result["total_hybrid_cost"] > 0
        assert result["ptu_monthly_cost"] + result["spillover_cost"] == pytest.approx(
            result["total_hybrid_cost"], abs=0.01
        )

    def test_empty_tpm_values(self):
        """Empty input returns zeros with minimum PTU."""
        result = calculate_spillover_cost(
            tpm_values=[],
            baseline_percentile=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_rate_per_1k=self.PAYG_RATE,
        )
        assert result["baseline_ptu"] == 15
        assert result["total_hybrid_cost"] == 0
        assert result["spillover_pct"] == 0

    def test_zero_percentile_uses_minimum_ptu(self):
        """Baseline percentile 0 → exactly 15 PTU (global min)."""
        tpm_values = [50_000.0] * 100
        result = calculate_spillover_cost(
            tpm_values=tpm_values,
            baseline_percentile=0,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_rate_per_1k=self.PAYG_RATE,
        )
        assert result["baseline_ptu"] == 15

    def test_high_percentile_low_spillover(self):
        """P95 baseline → very little spillover."""
        tpm_values = [50_000.0] * 100
        result = calculate_spillover_cost(
            tpm_values=tpm_values,
            baseline_percentile=95,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_rate_per_1k=self.PAYG_RATE,
        )
        # Constant values → P95 = all values → no spillover
        assert result["spillover_pct"] == 0
        assert result["spillover_cost"] == 0

    def test_reservation_discount_reduces_cost(self):
        """Reservation discount should reduce PTU cost."""
        tpm_values = [50_000.0] * 100
        no_discount = calculate_spillover_cost(
            tpm_values=tpm_values,
            baseline_percentile=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_rate_per_1k=self.PAYG_RATE,
            reservation_discount=0.0,
        )
        with_discount = calculate_spillover_cost(
            tpm_values=tpm_values,
            baseline_percentile=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_rate_per_1k=self.PAYG_RATE,
            reservation_discount=0.303,
        )
        assert with_discount["ptu_monthly_cost"] < no_discount["ptu_monthly_cost"]

    def test_spillover_pct_range(self):
        """Spillover percentage should be between 0 and 100."""
        np.random.seed(42)
        tpm_values = list(np.random.normal(50_000, 20_000, 500))
        result = calculate_spillover_cost(
            tpm_values=tpm_values,
            baseline_percentile=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_rate_per_1k=self.PAYG_RATE,
        )
        assert 0 <= result["spillover_pct"] <= 100


# ============================================================================
# calculate_break_even
# ============================================================================


class TestCalculateBreakEven:
    """Tests for break-even TPM calculation."""

    def test_returns_float_or_none(self):
        result = calculate_break_even(
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_blended_rate=4.75,
        )
        assert result is None or isinstance(result, float)

    def test_finds_break_even_point(self):
        """With reasonable rates, should find a break-even."""
        result = calculate_break_even(
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_blended_rate=10.0,  # High enough for PAYG slope > PTU slope
        )
        # Should find a crossover
        assert result is not None
        assert result > 0

    def test_break_even_increases_with_higher_ptu_cost(self):
        """Higher PTU rate → higher break-even TPM."""
        low = calculate_break_even(
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=0.5,
            payg_blended_rate=4.75,
        )
        high = calculate_break_even(
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=2.0,
            payg_blended_rate=4.75,
        )
        if low is not None and high is not None:
            assert high > low

    def test_reservation_discount_lowers_break_even(self):
        """Reservation discount → crossover at lower TPM."""
        no_discount = calculate_break_even(
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_blended_rate=4.75,
            reservation_discount=1.0,  # No discount
        )
        with_discount = calculate_break_even(
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_blended_rate=4.75,
            reservation_discount=0.303,  # 70% off
        )
        if no_discount is not None and with_discount is not None:
            assert with_discount < no_discount

    def test_no_crossover_returns_none(self):
        """If PAYG is always cheaper than PTU minimum, return None."""
        result = calculate_break_even(
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=100.0,  # Very expensive PTU
            payg_blended_rate=0.001,  # Very cheap PAYG
            max_search_tpm=10_000,
        )
        assert result is None


# ============================================================================
# generate_cost_curves
# ============================================================================


class TestGenerateCostCurves:
    """Tests for cost curve generation."""

    def test_returns_dataframe_with_expected_columns(self):
        np.random.seed(42)
        tpm_values = list(np.random.normal(50_000, 10_000, 200))
        df = generate_cost_curves(
            tpm_values=tpm_values,
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_blended_rate=4.75,
            payg_rate_per_1k=4.75,
        )
        assert "baseline_tpm" in df.columns
        assert "payg_monthly" in df.columns
        assert "ptu_spill_monthly" in df.columns
        assert "ptu_units" in df.columns

    def test_has_150_sample_points(self):
        tpm_values = [50_000.0] * 100
        df = generate_cost_curves(
            tpm_values=tpm_values,
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_blended_rate=4.75,
            payg_rate_per_1k=4.75,
        )
        assert len(df) == 150

    def test_empty_tpm_returns_empty_dataframe(self):
        df = generate_cost_curves(
            tpm_values=[],
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_blended_rate=4.75,
            payg_rate_per_1k=4.75,
        )
        assert len(df) == 0

    def test_payg_cost_increases_with_tpm(self):
        """PAYG cost should be monotonically increasing."""
        tpm_values = [50_000.0] * 100
        df = generate_cost_curves(
            tpm_values=tpm_values,
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_blended_rate=4.75,
            payg_rate_per_1k=4.75,
        )
        payg = df["payg_monthly"].values
        assert all(payg[i] <= payg[i + 1] for i in range(len(payg) - 1))

    def test_ptu_units_meet_minimum(self):
        """PTU units should always be >= min_ptu."""
        tpm_values = [1000.0] * 50
        df = generate_cost_curves(
            tpm_values=tpm_values,
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_blended_rate=4.75,
            payg_rate_per_1k=4.75,
            min_ptu=15,
        )
        assert all(df["ptu_units"] >= 15)


# ============================================================================
# calculate_ptu_costs
# ============================================================================


class TestCalculatePtuCosts:
    """Tests for the simple PTU cost calculator."""

    def test_known_model(self):
        result = calculate_ptu_costs(50_000, "gpt-4o")
        assert isinstance(result, dict)
        assert result["global_ptu"] >= 15
        assert result["global_monthly"] > 0

    def test_unknown_model_defaults(self):
        """Unknown model should still return a result with defaults."""
        result = calculate_ptu_costs(50_000, "unknown-model")
        assert isinstance(result, dict)
        assert result["global_ptu"] >= 15

    def test_higher_tpm_needs_more_ptu(self):
        low = calculate_ptu_costs(10_000, "gpt-4o")
        high = calculate_ptu_costs(200_000, "gpt-4o")
        assert high["global_ptu"] >= low["global_ptu"]

    def test_completion_ratio_affects_cost(self):
        """Higher completion ratio → more effective TPM → more PTU."""
        low_comp = calculate_ptu_costs(50_000, "gpt-4o", completion_ratio=0.1)
        high_comp = calculate_ptu_costs(50_000, "gpt-4o", completion_ratio=0.9)
        assert high_comp["global_ptu"] >= low_comp["global_ptu"]
