"""
Fundamental Analysis Module — DB-backed
========================================
Calculates Piotroski F-Score, ROE, ROCE, PAT growth, sales growth, and
earnings inflection from database-stored financial data.

All calculations use the pit_data table or multibaggers table data rather
than live API calls. yfinance ticker objects are accepted for backward
compatibility but a deprecation warning is logged.
"""

import pandas as pd

from core.observability.logger import get_logger

_log = get_logger(__name__)


def _safe_div(numerator, denominator, default=0.0):
    try:
        if denominator in (0, None):
            return default
        return numerator / denominator
    except Exception as e:
        _log.error(f"Caught unhandled exception: {e}", exc_info=True)
        return default


def _get_pit_series(symbol: str, metric_name: str, limit: int = 10) -> list[float]:
    """Fetch a time-series of PIT values for a symbol/metric, newest first."""
    try:
        from modules.data_layer.db_utils import get_db_connection

        clean_sym = symbol.replace(".NS", "").replace(".BO", "")
        with get_db_connection("pit_store.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT value FROM pit_data
                WHERE symbol = ? AND metric_name = ?
                ORDER BY as_of_date DESC
                LIMIT ?
                """,
                (clean_sym, metric_name, limit),
            )
            return [float(row[0]) for row in cursor.fetchall() if row[0] is not None]
    except Exception as exc:
        _log.debug("PIT lookup failed for %s/%s: %s", symbol, metric_name, exc)
        return []


def _has_ticker_api(obj) -> bool:
    """Check if an object looks like a yfinance Ticker (duck-typing)."""
    return hasattr(obj, "financials") and hasattr(obj, "balance_sheet")


def extract_financial_metric(df, keys, default=0, offset=0):
    """
    Finds a metric in a DataFrame using a list of possible keys or partial matches.
    Can extract values from previous years using the offset parameter.
    """
    if df.empty or len(df.columns) <= offset:
        return default

    # 1. Try exact matches first
    for key in keys:
        if key in df.index:
            val = df.loc[key].iloc[offset]
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                return val

    # 2. Try partial/fuzzy matches if no exact match found
    for key in keys:
        for index_name in df.index:
            if key.lower() in index_name.lower():
                val = df.loc[index_name].iloc[offset]
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    return val
    return default


def calculate_piotroski_f_score(ticker_or_data) -> int:
    """
    Calculates the 9-point Piotroski F-Score.

    Accepts either:
    - A yfinance Ticker object (deprecated — logs warning)
    - A dict with pre-computed fundamental data keys
    """
    # --- Dict-based path (preferred) ---
    if isinstance(ticker_or_data, dict):
        return _piotroski_from_dict(ticker_or_data)

    # --- Legacy yfinance Ticker path (deprecated) ---
    if _has_ticker_api(ticker_or_data):
        _log.warning("DEPRECATION: calculate_piotroski_f_score called with yfinance Ticker")
        return _piotroski_from_ticker(ticker_or_data)

    return 0


def _piotroski_from_dict(data: dict) -> int:
    """Compute Piotroski F-Score from pre-computed data dict."""
    f_score = 0
    try:
        roe = _safe_float(data.get("ROE%") or data.get("roe"), 0)
        cfo_pat = _safe_float(data.get("CFO_PAT_Ratio") or data.get("cfo_pat_ratio"), 0)
        de = _safe_float(data.get("Debt_Equity") or data.get("debt_equity"), 0)

        # 1. Profitability: ROA > 0 (proxy via ROE)
        if roe > 0:
            f_score += 1

        # 2. Operating Cash Flow > 0 (proxy via CFO/PAT > 0)
        if cfo_pat > 0:
            f_score += 1

        # 3. CFO > Net Income (CFO/PAT > 1.0)
        if cfo_pat > 1.0:
            f_score += 1

        # 4. ROA improving (proxy: current ROE > avg 5Y ROE)
        avg_roe = _safe_float(data.get("Avg_ROE_5Y%") or data.get("avg_roe_5y"), 0)
        if roe > avg_roe and avg_roe > 0:
            f_score += 1

        # 5. Leverage decreasing (low D/E is good)
        if 0 <= de < 0.5:
            f_score += 1
        elif 0 <= de < 1.0:
            f_score += 0  # Neutral — no point but no penalty

        # 6. Liquidity improving (proxy: we don't have current ratio, so skip or use proxy)
        # Give a point if D/E is reasonable
        if de < 1.0:
            f_score += 1

        # 7. No dilution (proxy: promoter holding stable/increasing)
        prom = _safe_float(data.get("Promoter_Holding%") or data.get("promoter_holding"), 0)
        if prom >= 50:
            f_score += 1

        # 8. Gross margin improving (proxy: operating margin positive)
        opm = _safe_float(data.get("Operating_Margin%") or data.get("opm"), 0)
        if opm > 10:
            f_score += 1

        # 9. Asset turnover improving (proxy: sales growth positive)
        sg = _safe_float(data.get("Sales_Growth_5Y%") or data.get("sales_cagr_5y"), 0)
        if sg > 0:
            f_score += 1

        return f_score
    except Exception as e:
        _log.error(f"Piotroski from dict failed: {e}", exc_info=True)
        return 0


def _piotroski_from_ticker(ticker) -> int:
    """Legacy yfinance-based Piotroski — kept for backward compat."""
    f_score = 0
    try:
        fin = ticker.financials
        bs = ticker.balance_sheet
        cf = ticker.cashflow

        if fin.empty or bs.empty or cf.empty:
            return 0

        net_income = extract_financial_metric(fin, ["Net Income", "NetIncome", "Net Income To Company", "Income"], 0, 0)
        total_assets = extract_financial_metric(bs, ["Total Assets", "Assets"], 1, 0)
        roa = _safe_div(net_income, total_assets)
        if roa > 0:
            f_score += 1

        cfo = extract_financial_metric(cf, ["Operating Cash Flow", "Operating Cashflow", "Cash From Operations"], 0, 0)
        if cfo > 0:
            f_score += 1

        net_income_prev = extract_financial_metric(fin, ["Net Income", "NetIncome", "Net Income To Company", "Income"], 0, 1)
        total_assets_prev = extract_financial_metric(bs, ["Total Assets", "Assets"], 1, 1)
        roa_prev = _safe_div(net_income_prev, total_assets_prev)
        if roa > roa_prev:
            f_score += 1

        if cfo > net_income:
            f_score += 1

        ltd = extract_financial_metric(bs, ["Long Term Debt", "Long-Term Debt"], 0, 0)
        ltd_prev = extract_financial_metric(bs, ["Long Term Debt", "Long-Term Debt"], 0, 1)
        if _safe_div(ltd, total_assets) <= _safe_div(ltd_prev, total_assets_prev):
            f_score += 1

        current_assets = extract_financial_metric(bs, ["Current Assets"], 0, 0)
        current_liab = extract_financial_metric(bs, ["Current Liabilities"], 1, 0)
        curr_ratio = _safe_div(current_assets, current_liab)
        current_assets_prev = extract_financial_metric(bs, ["Current Assets"], 0, 1)
        current_liab_prev = extract_financial_metric(bs, ["Current Liabilities"], 1, 1)
        curr_ratio_prev = _safe_div(current_assets_prev, current_liab_prev)
        if curr_ratio > curr_ratio_prev:
            f_score += 1

        shares = extract_financial_metric(bs, ["Ordinary Shares Number", "Common Stock", "Share Capital"], 0, 0)
        shares_prev = extract_financial_metric(bs, ["Ordinary Shares Number", "Common Stock", "Share Capital"], 0, 1)
        if shares <= shares_prev:
            f_score += 1

        gp = extract_financial_metric(fin, ["Gross Profit"], 0, 0)
        rev = extract_financial_metric(fin, ["Total Revenue", "Operating Revenue", "Revenue From Operations"], 1, 0)
        gm = _safe_div(gp, rev)
        gp_prev = extract_financial_metric(fin, ["Gross Profit"], 0, 1)
        rev_prev = extract_financial_metric(fin, ["Total Revenue", "Operating Revenue", "Revenue From Operations"], 1, 1)
        gm_prev = _safe_div(gp_prev, rev_prev)
        if gm > gm_prev:
            f_score += 1

        ato = _safe_div(rev, total_assets)
        ato_prev = _safe_div(rev_prev, total_assets_prev)
        if ato > ato_prev:
            f_score += 1

        return f_score
    except Exception as e:
        _log.error(f"Caught unhandled exception: {e}", exc_info=True)
        return 0


def _safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        result = float(val)
        if result != result:  # NaN check
            return default
        return result
    except (ValueError, TypeError):
        return default


def calculate_current_roe(ticker_or_data):
    """
    Derives Current ROE.

    Accepts a yfinance Ticker (deprecated) or a dict with ROE% / roe keys.
    """
    if isinstance(ticker_or_data, dict):
        return _safe_float(
            ticker_or_data.get("ROE%") or ticker_or_data.get("roe"),
            0,
        )

    if _has_ticker_api(ticker_or_data):
        _log.warning("DEPRECATION: calculate_current_roe called with yfinance Ticker")
        try:
            fin = ticker_or_data.financials
            bs = ticker_or_data.balance_sheet
            if fin.empty or bs.empty:
                return 0
            net_income = extract_financial_metric(
                fin, ["Net Income", "Net Profit", "PAT", "Profit After Tax"]
            )
            equity = extract_financial_metric(
                bs,
                ["Stockholders Equity", "Common Stock Equity", "Total Equity", "Shareholders Equity"],
            )
            roe = _safe_div(net_income, equity)
            return round(roe * 100, 2)
        except Exception as e:
            _log.error(f"Caught unhandled exception: {e}", exc_info=True)
            return 0

    return 0


def calculate_roce(ticker_or_data):
    """
    Calculates Return on Capital Employed (ROCE).
    ROCE = EBIT / (Total Assets - Current Liabilities)
    """
    if isinstance(ticker_or_data, dict):
        return _safe_float(
            ticker_or_data.get("ROCE%") or ticker_or_data.get("roce"),
            0,
        )

    if _has_ticker_api(ticker_or_data):
        _log.warning("DEPRECATION: calculate_roce called with yfinance Ticker")
        try:
            fin = ticker_or_data.financials
            bs = ticker_or_data.balance_sheet
            if fin.empty or bs.empty:
                return 0
            ebit = extract_financial_metric(fin, ["EBIT", "Operating Income", "Operating Profit"])
            total_assets = extract_financial_metric(bs, ["Total Assets"])
            current_liabilities = extract_financial_metric(
                bs, ["Current Liabilities", "Total Current Liabilities"]
            )
            capital_employed = total_assets - current_liabilities
            roce = _safe_div(ebit, capital_employed)
            return round(roce * 100, 2)
        except Exception as e:
            _log.error(f"Caught unhandled exception: {e}", exc_info=True)
            return 0

    return 0


def calculate_median_pat_growth(ticker_or_data, years=5):
    """
    Calculates the median PAT (Profit After Tax) growth over the last N years.
    """
    if isinstance(ticker_or_data, dict):
        # Use pre-computed growth fields
        pat_5y = _safe_float(ticker_or_data.get("PAT_CAGR_5Y"), 0)
        pat_3y = _safe_float(ticker_or_data.get("PAT_CAGR_3Y"), 0)
        return pat_5y if pat_5y != 0 else pat_3y

    if _has_ticker_api(ticker_or_data):
        _log.warning("DEPRECATION: calculate_median_pat_growth called with yfinance Ticker")
        try:
            import numpy as np

            fin = ticker_or_data.financials
            if fin.empty:
                return 0
            pat_keys = ["Net Income", "Net Profit", "PAT", "Profit After Tax"]
            row_key = None
            for key in pat_keys:
                if key in fin.index:
                    row_key = key
                    break
                for index_name in fin.index:
                    if key.lower() in index_name.lower():
                        row_key = index_name
                        break
                if row_key:
                    break
            if not row_key:
                return 0
            pats = fin.loc[row_key]
            if isinstance(pats, pd.DataFrame):
                pats = pats.iloc[0]
            pats = pats.iloc[::-1]
            if len(pats) < 2:
                return 0
            growths = []
            for i in range(1, len(pats)):
                prev = pats.iloc[i - 1]
                curr = pats.iloc[i]
                if prev != 0 and pd.notna(prev) and pd.notna(curr):
                    growths.append((curr - prev) / abs(prev))
            if not growths:
                return 0
            median_growth = np.median(growths)
            return round(float(median_growth) * 100, 2)
        except Exception as e:
            _log.error(f"Caught unhandled exception: {e}", exc_info=True)
            return 0

    return 0


def calculate_recent_sales_growth(ticker_or_data):
    """
    Calculates Sales Growth (YoY) from the last two financial years.
    """
    if isinstance(ticker_or_data, dict):
        sg = _safe_float(
            ticker_or_data.get("Sales_Growth_TTM%")
            or ticker_or_data.get("sales_growth")
            or ticker_or_data.get("Sales_Growth_5Y%")
            or ticker_or_data.get("sales_cagr_5y"),
            0,
        )
        return sg

    if _has_ticker_api(ticker_or_data):
        _log.warning("DEPRECATION: calculate_recent_sales_growth called with yfinance Ticker")
        try:
            fin = ticker_or_data.financials
            if fin.empty:
                return 0
            revenue_keys = [
                "Total Revenue", "Operating Revenue",
                "Revenue From Operations", "Net Sales",
            ]
            row_key = None
            for key in revenue_keys:
                if key in fin.index:
                    row_key = key
                    break
                for index_name in fin.index:
                    if key.lower() in index_name.lower():
                        row_key = index_name
                        break
                if row_key:
                    break
            if not row_key:
                return 0
            revs = fin.loc[row_key]
            if isinstance(revs, pd.DataFrame):
                revs = revs.iloc[0]
            if len(revs) < 2:
                return 0
            curr_rev = revs.iloc[0]
            prev_rev = revs.iloc[1]
            if pd.isna(curr_rev) or pd.isna(prev_rev) or prev_rev == 0:
                return 0
            growth = _safe_div(curr_rev - prev_rev, prev_rev)
            return round(growth * 100, 2)
        except Exception as e:
            _log.error(f"Caught unhandled exception: {e}", exc_info=True)
            return 0

    return 0


def check_earnings_inflection(ticker_or_data):
    """
    Detects detailed earnings acceleration (Phase 12).
    Returns a dict with status and score (0-5).

    Accepts a dict with quarterly growth keys or a yfinance Ticker (deprecated).
    """
    if isinstance(ticker_or_data, dict):
        return _earnings_inflection_from_dict(ticker_or_data)

    if _has_ticker_api(ticker_or_data):
        _log.warning("DEPRECATION: check_earnings_inflection called with yfinance Ticker")
        return _earnings_inflection_from_ticker(ticker_or_data)

    return {"score": 0, "status": False}


def _earnings_inflection_from_dict(data: dict) -> dict:
    """Compute earnings inflection from pre-computed data."""
    score = 0
    eps_growth = _safe_float(data.get("EPS_Growth%") or data.get("eps_growth"), 0)
    sg_ttm = _safe_float(data.get("Sales_Growth_TTM%") or data.get("sales_growth"), 0)
    opm = _safe_float(data.get("Operating_Margin%") or data.get("opm"), 0)
    avg_opm = _safe_float(data.get("Avg_OPM_5Y%") or data.get("avg_opm_5y"), 0)

    # Revenue acceleration
    if sg_ttm > 15:
        score += 1
    if sg_ttm > 25:
        score += 1

    # Earnings acceleration
    if eps_growth > 20:
        score += 1
    if eps_growth > 40:
        score += 1

    # Margin expansion
    if avg_opm > 0 and opm > avg_opm:
        score += 1

    return {"score": score, "status": score >= 3}


def _earnings_inflection_from_ticker(ticker) -> dict:
    """Legacy yfinance-based earnings inflection."""
    score = 0
    try:
        q_fin = ticker.quarterly_financials
        if q_fin.empty or len(q_fin.columns) < 3:
            return {"score": 0, "status": False}

        if "Total Revenue" not in q_fin.index or "Net Income" not in q_fin.index:
            return {"score": 0, "status": False}

        rev = q_fin.loc["Total Revenue"]
        rev_curr = rev.iloc[0]
        rev_prev = rev.iloc[1]
        rev_prev2 = rev.iloc[2]

        rev_growth_curr = _safe_div(rev_curr - rev_prev, rev_prev)
        rev_growth_prev = _safe_div(rev_prev - rev_prev2, rev_prev2)

        if rev_growth_curr > rev_growth_prev:
            score += 1
        if rev_growth_curr > 0.15:
            score += 1

        ni = q_fin.loc["Net Income"]
        ni_curr = ni.iloc[0]
        ni_prev = ni.iloc[1]
        ni_prev2 = ni.iloc[2]

        ni_growth_curr = _safe_div(ni_curr - ni_prev, abs(ni_prev))
        ni_growth_prev = _safe_div(ni_prev - ni_prev2, abs(ni_prev2))

        if ni_growth_curr > ni_growth_prev:
            score += 1
        if ni_growth_curr > 0.20:
            score += 1

        margin_curr = _safe_div(ni_curr, rev_curr)
        margin_prev = _safe_div(ni_prev, rev_prev)
        if margin_curr > margin_prev:
            score += 1

        return {"score": score, "status": score >= 3}
    except Exception as e:
        _log.error(f"Caught unhandled exception: {e}", exc_info=True)
        return {"score": 0, "status": False}


def analyze_margins_and_leverage(ticker_or_data):
    """
    Phase 14: Analyzes Operating Leverage and Margin Trends.
    Returns a dict with 'Margin_Trend' (bool) and 'Operating_Leverage' (bool).
    """
    if isinstance(ticker_or_data, dict):
        opm = _safe_float(ticker_or_data.get("Operating_Margin%") or ticker_or_data.get("opm"), 0)
        avg_opm = _safe_float(ticker_or_data.get("Avg_OPM_5Y%") or ticker_or_data.get("avg_opm_5y"), 0)
        sg = _safe_float(ticker_or_data.get("Sales_Growth_TTM%") or ticker_or_data.get("sales_growth"), 0)
        eps_g = _safe_float(ticker_or_data.get("EPS_Growth%") or ticker_or_data.get("eps_growth"), 0)

        margin_trend = opm > avg_opm if avg_opm > 0 else False
        op_leverage = eps_g > (sg * 1.2) if sg > 0 else False

        return {"Margin_Trend": margin_trend, "Operating_Leverage": op_leverage}

    if _has_ticker_api(ticker_or_data):
        _log.warning("DEPRECATION: analyze_margins_and_leverage called with yfinance Ticker")
        try:
            fin = ticker_or_data.financials
            if fin.empty or len(fin.columns) < 3 or "Total Revenue" not in fin.index:
                return {"Margin_Trend": False, "Operating_Leverage": False}

            if "Operating Income" in fin.index:
                op_inc = fin.loc["Operating Income"]
            elif "EBIT" in fin.index:
                op_inc = fin.loc["EBIT"]
            else:
                return {"Margin_Trend": False, "Operating_Leverage": False}

            rev = fin.loc["Total Revenue"]
            m_curr = _safe_div(op_inc.iloc[0], rev.iloc[0])
            m_prev = _safe_div(op_inc.iloc[1], rev.iloc[1])
            m_prev2 = _safe_div(op_inc.iloc[2], rev.iloc[2])
            margin_expansion = m_curr > m_prev > m_prev2
            op_growth = _safe_div(op_inc.iloc[0] - op_inc.iloc[1], abs(op_inc.iloc[1]))
            rev_growth = _safe_div(rev.iloc[0] - rev.iloc[1], abs(rev.iloc[1]))
            op_leverage = op_growth > (rev_growth * 1.2)
            return {"Margin_Trend": margin_expansion, "Operating_Leverage": op_leverage}
        except Exception as e:
            _log.error(f"Caught unhandled exception: {e}", exc_info=True)
            return {"Margin_Trend": False, "Operating_Leverage": False}

    return {"Margin_Trend": False, "Operating_Leverage": False}
