"""Tests for ptu_advisor.cost.calculator — break-even and cost curve functions."""

import numpy as np
import pandas as pd
import pytest

from ptu_advisor.cost.calculator import (
    calculate_break_even,
    calculate_break_even_for_fixed_ptu,
    calculate_ptu_costs,
    calculate_spillover_cost,
    generate_cost_curves,
    generate_cost_curves_fixed_ptu,
)


@pytest.fixture
def tpm_values():
    """Simulated TPM distribution for tests."""
    np.random.seed(42)
    return np.random.normal(50_000, 15_000, 1000).clip(5000).tolist()


class TestCalculateBreakEven:
    def test_returns_float_when_crossover_exists(self):
        be = calculate_break_even(
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_blended_rate=4.75,
            reservation_discount=0.303,
            min_ptu=15,
            ptu_increment=5,
            max_search_tpm=200_000,
        )
        assert be is not None
        assert isinstance(be, float)
        assert be > 0

    def test_returns_none_when_no_crossover(self):
        # With no reservation discount, PTU is so expensive it never crosses PAYG
        be = calculate_break_even(
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=100.0,
            payg_blended_rate=0.01,
            reservation_discount=1.0,
            max_search_tpm=200_000,
        )
        assert be is None


class TestGenerateCostCurves:
    def test_returns_dataframe_with_expected_columns(self, tpm_values):
        curves = generate_cost_curves(
            tpm_values=tpm_values,
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_blended_rate=4.75,
            payg_rate_per_1k=0.00475,
            reservation_discount=0.303,
            min_ptu=15,
            ptu_increment=5,
        )
        assert isinstance(curves, pd.DataFrame)
        assert list(curves.columns) == [
            "baseline_tpm",
            "payg_monthly",
            "ptu_spill_monthly",
            "ptu_units",
        ]
        assert len(curves) == 150

    def test_empty_tpm_returns_empty_df(self):
        curves = generate_cost_curves(
            tpm_values=[],
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_blended_rate=4.75,
            payg_rate_per_1k=0.00475,
        )
        assert len(curves) == 0


class TestCalculateSpilloverCost:
    def test_returns_expected_keys(self, tpm_values):
        result = calculate_spillover_cost(
            tpm_values=tpm_values,
            baseline_percentile=75,
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_rate_per_1k=0.00475,
            reservation_discount=0.303,
        )
        expected_keys = {
            "baseline_tpm",
            "peak_tpm",
            "baseline_ptu",
            "ptu_capacity_tpm",
            "spillover_tokens_monthly",
            "avg_spillover_tpm",
            "ptu_monthly_full",
            "ptu_monthly_cost",
            "spillover_cost",
            "total_hybrid_cost",
            "spillover_pct",
        }
        assert set(result.keys()) == expected_keys

    def test_empty_tpm_returns_defaults(self):
        result = calculate_spillover_cost(
            tpm_values=[],
            baseline_percentile=75,
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_rate_per_1k=0.00475,
        )
        assert result["baseline_ptu"] == 15
        assert result["total_hybrid_cost"] == 0

    def test_total_hybrid_equals_ptu_plus_spillover(self, tpm_values):
        result = calculate_spillover_cost(
            tpm_values=tpm_values,
            baseline_percentile=50,
            ptu_capacity_per_unit=2500,
            ptu_hourly_rate=1.0,
            payg_rate_per_1k=0.00475,
            reservation_discount=0.361,
        )
        assert result["total_hybrid_cost"] == pytest.approx(
            result["ptu_monthly_cost"] + result["spillover_cost"]
        )


class TestCalculatePtuCosts:
    def test_known_model(self):
        result = calculate_ptu_costs(peak_tpm=50_000, model="gpt-4o")
        assert result["tpm_per_ptu"] == 2500
        assert result["global_ptu"] >= 15
        assert result["regional_ptu"] >= 50

    def test_unknown_model_falls_back_to_gpt4o(self):
        result = calculate_ptu_costs(peak_tpm=50_000, model="unknown-model")
        assert result["tpm_per_ptu"] == 2500

    def test_uses_canonical_capacity_rates_and_month_length(self):
        result = calculate_ptu_costs(peak_tpm=50_000, model="gpt-4.1")

        assert result["tpm_per_ptu"] == 3000
        assert result["global_monthly"] == result["global_ptu"] * 1.0 * 720
        assert result["regional_monthly"] == result["regional_ptu"] * 2.0 * 720


# ============================================================================
# v2: calculate_break_even_for_fixed_ptu  (REQ-COST-102)
# ============================================================================


class TestCalculateBreakEvenForFixedPtu:
    """Tests for the v2 fixed-PTU analytical break-even.

    REQ-COST-102: Break-even TPM correctness within tolerance.
    """

    # Standard test parameters (gpt-4o-like)
    PTU_CAPACITY = 2500.0  # TPM per PTU
    PTU_HOURLY = 2.0  # $/hr per PTU
    PAYG_RATE = 6.00  # $/1M tokens (blended)

    def test_REQ_COST_102_analytical_break_even_matches_manual(self):
        """Break-even = PTU_fixed x 1M / (43200 x rate), verified manually."""
        selected_ptu = 50
        discount = 0.303
        ptu_fixed = selected_ptu * self.PTU_HOURLY * 720 * discount
        expected_be = ptu_fixed * 1_000_000 / (43_200 * self.PAYG_RATE)

        result = calculate_break_even_for_fixed_ptu(
            selected_ptu=selected_ptu,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            reservation_discount=discount,
        )
        assert result is not None
        assert result == pytest.approx(expected_be, rel=0.02)

    def test_REQ_COST_102_break_even_within_flat_phase(self):
        """Break-even must occur within the flat phase (tpm <= PTU capacity)."""
        selected_ptu = 50
        ptu_capacity_tpm = selected_ptu * self.PTU_CAPACITY  # 125,000

        result = calculate_break_even_for_fixed_ptu(
            selected_ptu=selected_ptu,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            reservation_discount=0.303,
        )
        assert result is not None
        assert result <= ptu_capacity_tpm

    def test_REQ_COST_102_returns_none_when_ptu_always_expensive(self):
        """When PTU fixed cost is too high, break-even exceeds capacity -> None."""
        # Very expensive PTU, very cheap PAYG
        result = calculate_break_even_for_fixed_ptu(
            selected_ptu=15,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=100.0,
            payg_blended_rate=0.01,
        )
        assert result is None

    def test_REQ_COST_102_returns_none_when_payg_rate_zero(self):
        """Zero PAYG rate means PAYG cost is always 0 -> no crossover."""
        result = calculate_break_even_for_fixed_ptu(
            selected_ptu=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=0.0,
        )
        assert result is None

    def test_REQ_COST_102_returns_none_when_payg_rate_negative(self):
        """Negative PAYG rate is invalid -> returns None."""
        result = calculate_break_even_for_fixed_ptu(
            selected_ptu=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=-1.0,
        )
        assert result is None

    def test_REQ_COST_102_higher_ptu_commitment_raises_break_even(self):
        """More PTU -> higher fixed cost -> need more traffic to justify."""
        params = dict(
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            reservation_discount=0.303,
        )
        be_low = calculate_break_even_for_fixed_ptu(selected_ptu=15, **params)
        be_high = calculate_break_even_for_fixed_ptu(selected_ptu=50, **params)
        assert be_low is not None
        assert be_high is not None
        assert be_high > be_low

    def test_REQ_COST_102_reservation_discount_lowers_break_even(self):
        """Deeper discount -> lower PTU fixed cost -> break-even at lower TPM."""
        # Use a high PAYG rate so even full-price PTU has break-even in flat phase
        params = dict(
            selected_ptu=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=15.0,  # high enough for full-price break-even in flat phase
        )
        be_no_discount = calculate_break_even_for_fixed_ptu(reservation_discount=1.0, **params)
        be_with_discount = calculate_break_even_for_fixed_ptu(reservation_discount=0.303, **params)
        assert be_no_discount is not None
        assert be_with_discount is not None
        assert be_with_discount < be_no_discount

    def test_REQ_COST_102_no_discount_uses_full_price(self):
        """reservation_discount=1.0 means no discount (full price)."""
        selected_ptu = 30
        # Use high PAYG rate so full-price PTU break-even stays in flat phase
        payg_rate = 15.0
        ptu_fixed = selected_ptu * self.PTU_HOURLY * 720  # discount=1.0 -> full
        expected_be = ptu_fixed * 1_000_000 / (43_200 * payg_rate)

        result = calculate_break_even_for_fixed_ptu(
            selected_ptu=selected_ptu,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=payg_rate,
            reservation_discount=1.0,
        )
        assert result is not None
        assert result == pytest.approx(expected_be, rel=0.001)

    def test_REQ_COST_102_minimum_ptu_produces_lowest_break_even(self):
        """Min PTU (15) should have the lowest break-even TPM."""
        params = dict(
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            reservation_discount=0.303,
        )
        be_min = calculate_break_even_for_fixed_ptu(selected_ptu=15, **params)
        be_med = calculate_break_even_for_fixed_ptu(selected_ptu=75, **params)
        assert be_min is not None
        assert be_med is not None
        assert be_min < be_med

    def test_REQ_COST_102_break_even_is_positive(self):
        """Break-even TPM must always be > 0 when it exists."""
        result = calculate_break_even_for_fixed_ptu(
            selected_ptu=15,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            reservation_discount=0.303,
        )
        assert result is not None
        assert result > 0

    def test_REQ_COST_102_break_even_linearly_proportional_to_ptu(self):
        """Break-even scales linearly with selected PTU (fixed rate/capacity)."""
        params = dict(
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            reservation_discount=0.303,
        )
        be_20 = calculate_break_even_for_fixed_ptu(selected_ptu=20, **params)
        be_40 = calculate_break_even_for_fixed_ptu(selected_ptu=40, **params)
        assert be_20 is not None
        assert be_40 is not None
        # BE is proportional to PTU count: be_40 / be_20 ~ 2.0
        assert be_40 / be_20 == pytest.approx(2.0, rel=0.01)


# ============================================================================
# v2: generate_cost_curves_fixed_ptu  (REQ-UX-101, REQ-UX-103)
# ============================================================================


class TestGenerateCostCurvesFixedPtu:
    """Tests for v2 cost curve generation with fixed PTU commitment.

    REQ-UX-101: Break-even marker visible -- requires correct curve data.
    REQ-UX-103: Slider updates cost outputs -- curves must regenerate correctly.
    """

    PTU_CAPACITY = 2500.0
    PTU_HOURLY = 2.0
    PAYG_RATE = 6.00

    def test_REQ_UX_101_returns_dataframe_with_expected_columns(self):
        """Curve data must have sustained_tpm, payg_monthly, ptu_spill_monthly."""
        df = generate_cost_curves_fixed_ptu(
            selected_ptu=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
        )
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == [
            "sustained_tpm",
            "payg_monthly",
            "ptu_spill_monthly",
        ]

    def test_REQ_UX_103_default_200_sample_points(self):
        """Default num_points=200 produces 200 rows."""
        df = generate_cost_curves_fixed_ptu(
            selected_ptu=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
        )
        assert len(df) == 200

    def test_REQ_UX_103_custom_num_points(self):
        """Custom num_points is respected."""
        df = generate_cost_curves_fixed_ptu(
            selected_ptu=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            num_points=100,
        )
        assert len(df) == 100

    def test_REQ_UX_101_payg_starts_at_zero(self):
        """PAYG cost at TPM=0 must be 0."""
        df = generate_cost_curves_fixed_ptu(
            selected_ptu=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
        )
        assert df.iloc[0]["payg_monthly"] == pytest.approx(0.0)

    def test_REQ_UX_101_payg_increases_monotonically(self):
        """PAYG line must be strictly non-decreasing."""
        df = generate_cost_curves_fixed_ptu(
            selected_ptu=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
        )
        payg = df["payg_monthly"].values
        assert all(payg[i] <= payg[i + 1] for i in range(len(payg) - 1))

    def test_REQ_UX_101_ptu_flat_phase_is_constant(self):
        """Below PTU capacity, PTU+Spillover must be constant (flat phase)."""
        selected_ptu = 50
        ptu_capacity_tpm = selected_ptu * self.PTU_CAPACITY  # 125,000

        df = generate_cost_curves_fixed_ptu(
            selected_ptu=selected_ptu,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            max_tpm=200_000,
        )
        flat_rows = df[df["sustained_tpm"] <= ptu_capacity_tpm]
        assert len(flat_rows) > 1
        # All values in flat phase should be the same
        ptu_costs = flat_rows["ptu_spill_monthly"].values
        assert all(c == pytest.approx(ptu_costs[0], abs=0.01) for c in ptu_costs)

    def test_REQ_UX_101_ptu_rising_phase_after_capacity(self):
        """Above PTU capacity, PTU+Spillover must increase (spillover adds cost)."""
        selected_ptu = 50
        ptu_capacity_tpm = selected_ptu * self.PTU_CAPACITY  # 125,000

        df = generate_cost_curves_fixed_ptu(
            selected_ptu=selected_ptu,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            max_tpm=200_000,
        )
        rising_rows = df[df["sustained_tpm"] > ptu_capacity_tpm]
        assert len(rising_rows) > 1
        costs = rising_rows["ptu_spill_monthly"].values
        assert all(costs[i] <= costs[i + 1] for i in range(len(costs) - 1))

    def test_REQ_UX_101_rising_phase_parallel_to_payg(self):
        """In the rising phase, marginal slope equals PAYG slope (parallel lines)."""
        selected_ptu = 50
        ptu_capacity_tpm = selected_ptu * self.PTU_CAPACITY

        df = generate_cost_curves_fixed_ptu(
            selected_ptu=selected_ptu,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            max_tpm=300_000,
            num_points=300,
        )
        rising = df[df["sustained_tpm"] > ptu_capacity_tpm * 1.05]
        if len(rising) >= 3:
            # Compute slopes of PAYG and PTU in the rising region
            tpm_vals = rising["sustained_tpm"].values
            payg_vals = rising["payg_monthly"].values
            ptu_vals = rising["ptu_spill_monthly"].values
            payg_slope = (payg_vals[-1] - payg_vals[0]) / (tpm_vals[-1] - tpm_vals[0])
            ptu_slope = (ptu_vals[-1] - ptu_vals[0]) / (tpm_vals[-1] - tpm_vals[0])
            assert ptu_slope == pytest.approx(payg_slope, rel=0.01)

    def test_REQ_UX_101_flat_phase_cost_matches_manual(self):
        """Flat phase cost = selected_ptu x hourly x 720 x discount."""
        selected_ptu = 50
        discount = 0.303
        expected_fixed = selected_ptu * self.PTU_HOURLY * 720 * discount

        df = generate_cost_curves_fixed_ptu(
            selected_ptu=selected_ptu,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            reservation_discount=discount,
        )
        # First row (tpm=0) should be the fixed PTU cost
        assert df.iloc[0]["ptu_spill_monthly"] == pytest.approx(expected_fixed, rel=0.001)

    def test_REQ_UX_103_slider_change_shifts_flat_level(self):
        """Different PTU commitment -> different flat level cost."""
        params = dict(
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
        )
        df_low = generate_cost_curves_fixed_ptu(selected_ptu=15, **params)
        df_high = generate_cost_curves_fixed_ptu(selected_ptu=100, **params)
        # At tpm=0, higher PTU -> higher fixed cost
        assert df_high.iloc[0]["ptu_spill_monthly"] > df_low.iloc[0]["ptu_spill_monthly"]

    def test_REQ_UX_103_slider_change_shifts_inflection_point(self):
        """More PTU -> inflection point (start of spillover) moves right."""
        params = dict(
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            max_tpm=300_000,
            num_points=300,
        )
        df_low = generate_cost_curves_fixed_ptu(selected_ptu=15, **params)
        df_high = generate_cost_curves_fixed_ptu(selected_ptu=100, **params)

        # Find first row where cost rises above the flat level
        def find_inflection(df):
            flat_cost = df.iloc[0]["ptu_spill_monthly"]
            rising = df[df["ptu_spill_monthly"] > flat_cost + 1.0]
            return rising.iloc[0]["sustained_tpm"] if len(rising) > 0 else 0

        inflect_low = find_inflection(df_low)
        inflect_high = find_inflection(df_high)
        assert inflect_high > inflect_low

    def test_REQ_UX_101_payg_cost_formula_matches_manual(self):
        """PAYG cost = tpm x 43200 / 1M x blended_rate."""
        df = generate_cost_curves_fixed_ptu(
            selected_ptu=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            max_tpm=100_000,
            num_points=50,
        )
        # Check a row with non-zero TPM
        row = df.iloc[10]
        tpm = row["sustained_tpm"]
        expected_payg = tpm * 43_200 / 1_000_000 * self.PAYG_RATE
        assert row["payg_monthly"] == pytest.approx(expected_payg, rel=0.001)

    def test_REQ_UX_103_reservation_discount_reduces_flat_cost(self):
        """Reservation discount lowers the flat phase of PTU+Spillover."""
        params = dict(
            selected_ptu=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
        )
        df_full = generate_cost_curves_fixed_ptu(reservation_discount=1.0, **params)
        df_disc = generate_cost_curves_fixed_ptu(reservation_discount=0.303, **params)
        assert df_disc.iloc[0]["ptu_spill_monthly"] < df_full.iloc[0]["ptu_spill_monthly"]

    def test_REQ_UX_101_max_tpm_respected(self):
        """Sample points stay within [0, max_tpm]."""
        max_tpm = 150_000
        df = generate_cost_curves_fixed_ptu(
            selected_ptu=50,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
            max_tpm=max_tpm,
        )
        assert df["sustained_tpm"].max() <= max_tpm + 1
        assert df["sustained_tpm"].min() >= 0

    def test_REQ_UX_101_ptu_spill_never_negative(self):
        """PTU+Spillover cost must never be negative."""
        df = generate_cost_curves_fixed_ptu(
            selected_ptu=15,
            ptu_capacity_per_unit=self.PTU_CAPACITY,
            ptu_hourly_rate=self.PTU_HOURLY,
            payg_blended_rate=self.PAYG_RATE,
        )
        assert (df["ptu_spill_monthly"] >= 0).all()
