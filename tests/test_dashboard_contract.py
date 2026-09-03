from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_dashboard_uses_fixed_ptu_break_even() -> None:
    source = (REPO_ROOT / "ptu_advisor/dashboard/app.py").read_text(encoding="utf-8")

    assert "calculate_break_even_for_fixed_ptu(" in source
    assert "calculate_break_even(" not in source