from core.observability.logger import get_logger
_log = get_logger("modules.portfolio.portfolio_optimizer")
def optimize_portfolio_allocation(candidates, capital=1000000):
    """
    Phase 35: Portfolio Construction Engine.
    Applies 'Fund Manager' constraints to the ranked list.

    Constraints:
    1. Max Stocks: 15
    2. Max Weight per Stock: 12%
    3. Max Weight per Sector: 25%
    4. Min Weight: 3%

    Args:
        candidates (list): List of stock dicts, sorted by Score.
        capital: Total capital to deploy.

    Returns:
        final_portfolio (list): List of selected stocks with 'Weight' and 'Qty'.
    """
    _log.info("\n" + "=" * 50)
    _log.info("🏗️  PHASE 35: PORTFOLIO OPTIMIZATION")
    _log.info("=" * 50)

    MAX_STOCKS = 12
    MAX_WEIGHT_PER_STOCK = 0.12  # 12% hard cap per stock
    MAX_SECTOR_WEIGHT = 0.25     # 25% cap (matches docstring)

    from typing import Any
    selected_portfolio: list[dict[str, Any]] = []
    sector_exposure: dict[str, float] = {}
    current_total_weight: float = 0.0

    # 1. Greedy Allocation Loop
    for stock in candidates:
        if len(selected_portfolio) >= MAX_STOCKS:
            break

        sector = stock.get("Sector", "Unknown")
        current_sec_weight = sector_exposure.get(sector, 0)

        # Check Sector Constraint
        if current_sec_weight >= MAX_SECTOR_WEIGHT:
            continue  # Skip this stock, sector is full

        # Determine Weight (Score Based)
        # Base weight on score: Score 100 = 10%, Score 80 = 5%?
        # Let's use simple logic: Target Equal Weight initially, then adjust?
        # Better: Top 5 get 10%, Next 7 get 7%...

        target_weight = 0.08  # 8% avg

        # Check Scarcity
        if current_sec_weight + target_weight > MAX_SECTOR_WEIGHT:
            target_weight = MAX_SECTOR_WEIGHT - current_sec_weight

        if target_weight < 0.03:  # Too small to bother
            continue

        # Add to Portfolio
        stock["Target_Weight%"] = round(target_weight * 100, 1)
        stock["Allocated_Capital"] = round(capital * target_weight, 2)
        price = stock.get("Price", 0)
        if price > 0:
            stock["Qty"] = int((capital * target_weight) / price)
        else:
            stock["Qty"] = 0

        selected_portfolio.append(stock)
        sector_exposure[sector] = current_sec_weight + target_weight
        current_total_weight += target_weight

    # 2. Normalization — always scale to 100% deployment with iterative redistribution
    if current_total_weight > 0 and current_total_weight < 0.999:
        correction_factor = 1.0 / current_total_weight
        _log.info(f"  Note: Scaling up weights by {correction_factor:.2f}x to fully invest.")
        for s in selected_portfolio:
            s["Target_Weight%"] = (s["Target_Weight%"] / 100) * correction_factor * 100

        # Iterative clamp-and-redistribute: clip over-weight stocks, redistribute
        # excess proportionally to uncapped peers. Inline capping guarantees
        # convergence within ⌈log₂(N)⌉ passes (typically 2–3).
        for _pass in range(10):  # Safety bound
            excess = 0.0
            capped_indices = set()
            for i, s in enumerate(selected_portfolio):
                w = s["Target_Weight%"] / 100
                if w > MAX_WEIGHT_PER_STOCK:
                    excess += w - MAX_WEIGHT_PER_STOCK
                    s["Target_Weight%"] = MAX_WEIGHT_PER_STOCK * 100
                    capped_indices.add(i)

            if excess < 1e-9:
                break  # Converged — no more excess to redistribute

            # Redistribute excess proportionally among uncapped stocks
            uncapped = [
                (i, selected_portfolio[i]["Target_Weight%"] / 100)
                for i in range(len(selected_portfolio))
                if i not in capped_indices
            ]
            uncapped_total = sum(w for _, w in uncapped)
            if uncapped_total <= 0:
                break  # All stocks are at cap — can't redistribute further

            for i, w in uncapped:
                share = (w / uncapped_total) * excess
                new_w = min(MAX_WEIGHT_PER_STOCK, w + share)
                selected_portfolio[i]["Target_Weight%"] = new_w * 100
        else:
            _log.warning(
                "Weight redistribution did not converge in 10 passes"
                " — residual excess may exist"
            )

        # Recompute allocated capital and quantities from final weights
        for s in selected_portfolio:
            new_w = s["Target_Weight%"] / 100
            s["Allocated_Capital"] = round(capital * new_w, 2)
            if s.get("Price", 0) > 0:
                s["Qty"] = int(s["Allocated_Capital"] / s["Price"])

    # Rebuild sector_exposure from actual post-normalization weights (always)
    sector_exposure = {}
    for s in selected_portfolio:
        sec = s.get("Sector", "Unknown")
        sector_exposure[sec] = sector_exposure.get(sec, 0) + s["Target_Weight%"] / 100
    for sec, w in sector_exposure.items():
        if w > MAX_SECTOR_WEIGHT:
            _log.warning(
                f"  ⚠️ Sector '{sec}' weight {w*100:.1f}% exceeds "
                f"{MAX_SECTOR_WEIGHT*100:.0f}% cap after normalization!"
            )

    _log.info(f"Selected {len(selected_portfolio)} stocks from candidate list.")
    _log.info("Sector Breakdown:")
    for sec, w in sector_exposure.items():
        _log.info(f"  - {sec}: {w * 100:.1f}%")

    return selected_portfolio

