from modules.thesis_monitor import check_thesis

def check_exit_conditions(stock_data):
    """
    Phase 34: Thesis Break Monitor (Exit Engine).
    Integrates threshold-based severity scoring and thesis monitoring.
    Replaces brittle binary exit rules with severity scoring.

    Returns:
        exit_triggered (bool): True if stock should be sold/avoided.
        reason (str): The specific rule violated.
    """
    symbol = stock_data.get("Symbol", "Unknown")
    
    # 1. Check Personal Thesis Monitor First
    if symbol != "Unknown":
        thesis_status = check_thesis(symbol)
        if thesis_status.status == "THESIS_BREAK":
            reasons = "; ".join([b["message"] for b in thesis_status.breaks])
            return True, f"Thesis Broken: {reasons}"
            
    # 2. General Threshold-Based Severity Scoring
    severity_score = 0
    reasons = []
    
    price = stock_data.get("Price", 0)
    dma_200 = stock_data.get("200_DMA", 0)
    f_score = stock_data.get("F_Score", 0)
    peg = stock_data.get("PEG_Ratio", 0)
    sales_growth = stock_data.get("Sales_Growth_TTM%", 0)
    score = stock_data.get("Score", 0)
    
    # Trend Break (+3 Severity)
    if price > 0 and dma_200 > 0 and price < dma_200:
        severity_score += 3
        reasons.append("Price < 200 DMA (+3)")
        
    # Quality Collapse (+4 Severity)
    if f_score > 0 and f_score < 4:
        severity_score += 4
        reasons.append("F-Score < 4 (+4)")
        
    # Extreme Valuation (+3 Severity)
    if peg > 5.0:
        severity_score += 3
        reasons.append("PEG > 5 (+3)")
        
    # Growth Stagnation (+4 Severity)
    if sales_growth < 0:
        severity_score += 4
        reasons.append("Negative Sales Growth (+4)")
        
    # Model Score Deterioration (+5 Severity)
    if score > 0 and score < 40:
        severity_score += 5
        reasons.append("Score < 40 (+5)")
        
    # Trigger exit if severity crosses threshold (e.g., >= 5)
    if severity_score >= 5:
        return True, f"High Severity ({severity_score}/10): " + "; ".join(reasons)
        
    if severity_score > 0:
        return False, f"Warning ({severity_score}/10): " + "; ".join(reasons)

    return False, "Safe"
