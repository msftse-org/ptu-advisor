"""Tests for ptu_advisor.cost.calculator — break-even and cost curve functions."""

import numpy as np
import pandas as pd
import pytest

from ptu_advisor.cost.calculator import (
    calculate_break_even,
    calculate_spillover_cost,
    generate_cost_curves,
    calculate_ptu_costs,
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
