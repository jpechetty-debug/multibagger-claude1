from __future__ import annotations

from modules.reporting.score_diagnostics import _build_checklist_status, _infer_active_ceilings


def _diagnostic_stock(**overrides):
    stock = {
        "symbol": "DIAG.NS",
        "market_cap_cr": 301.0,
        "pe_ratio": 30.0,
        "avg_roe_5y": 22.0,
        "roe": 20.0,
        "debt_equity": 0.4,
        "cfo_pat_ratio": 1.3,
        "down_from_52w": 8.0,
        "sales_cagr_5y": 18.0,
        "sales_growth": 16.0,
        "eps_growth": 12.0,
        "promoter_holding": 55.0,
        "inst_holding": 20.0,
        "f_score": 7,
        "sector": "Technology",
        "value_gap": 10.0,
        "price": 1000.0,
        "rs_rating": 1.2,
        "pledge_pct": 0.0,
    }
    stock.update(overrides)
    return stock


def test_score_diagnostics_uses_real_checklist_gate_thresholds():
    status = _build_checklist_status(_diagnostic_stock())

    assert status["items"]["Market Cap > 300 Cr"] is True
    assert status["items"]["PE < 50"] is True
    assert all("1000 Cr" not in label for label in status["items"])
    assert status["passed"] == 12
    assert status["total"] == 12


def test_score_diagnostics_reports_real_ceiling_rule_names():
    ceilings = _infer_active_ceilings(
        _diagnostic_stock(
            market_cap_cr=50.0,
            pe_ratio=90.0,
            avg_roe_5y=-20.0,
            roe=-20.0,
            debt_equity=2.0,
            cfo_pat_ratio=0.2,
            down_from_52w=70.0,
            sales_cagr_5y=-12.0,
            sales_growth=-8.0,
            eps_growth=-20.0,
            promoter_holding=10.0,
            f_score=1,
            value_gap=-80.0,
            profit_margin=-5.0,
            pledge_pct=30.0,
        )
    )
    names = [ceiling["name"] for ceiling in ceilings]

    assert any(name.startswith("Value Destruction Spline") for name in names)
    assert any(name.startswith("Declining Revenue Spline") for name in names)
    assert any(name.startswith("Overvaluation Spline") for name in names)
    assert any(name.startswith("High Pledge Risk") for name in names)
    assert any(name == "Institutional Quality Gate 0/12" for name in names)
