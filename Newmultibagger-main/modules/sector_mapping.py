"""
Sovereign AI Trading Engine - Indian Sector Mapping Layer
Maps broad yfinance sectors to specific Indian market classifications.
"""

# Industry mapping based on keywords in company name or yfinance industry
INDIAN_SECTOR_MAP = {
    "SPORTKING": "Textiles (Spinning)",
    "RELIANCE": "Energy / O2C",
    "TCS": "IT Services",
    "INFY": "IT Services",
    "HDFCBANK": "Banking (PVT)",
    "ICICIBANK": "Banking (PVT)",
    "SBIN": "Banking (PSU)",
    "MARUTI": "Automobile",
    "TATAMOTORS": "Automobile",
    "JINDALSTEL": "Steel",
    "TATASTEEL": "Steel",
    "ADANIENT": "Conglomerate",
}

INDUSTRY_KEYWORDS = {
    "Textile": "Textiles",
    "Spinning": "Textiles",
    "Garment": "Textiles",
    "Bank": "Financial Services",
    "Finance": "Financial Services",
    "Software": "IT Services",
    "Information Technology": "IT Services",
    "Steel": "Metals & Mining",
    "Aluminum": "Metals & Mining",
    "Metals": "Metals & Mining",
    "Pharma": "Healthcare",
    "Drug": "Healthcare",
    "Hospital": "Healthcare",
    "Construction": "Industrials",
    "Engineering": "Industrials",
    # Utility-specific phrases only: a bare "Electric" also matched cable and
    # electrical-equipment makers ("Cables - Electricals") and filed them as utilities.
    "Power Generation": "Energy & Utilities",
    "Power Distribution": "Energy & Utilities",
    "Electric Utilities": "Energy & Utilities",
    "Utilities": "Energy & Utilities",
    "Telecom": "Communication Services",
}


def get_refined_sector(symbol: str, long_name: str, yf_sector: str, yf_industry: str) -> str:
    """
    Refines the broad yfinance sector into a more accurate Indian market classification.
    """
    # 1. Exact Symbol/LongName Match
    clean_sym = symbol.replace(".NS", "").replace(".BO", "").upper()
    if clean_sym in INDIAN_SECTOR_MAP:
        return INDIAN_SECTOR_MAP[clean_sym]

    # No company-name substring match: "RELIANCE" filed Reliance Power and
    # Reliance Infrastructure under "Energy / O2C".

    # 2. Industry Keyword Match
    industry_text = (yf_industry or "").title()
    for kw, mapping in INDUSTRY_KEYWORDS.items():
        if kw in industry_text:
            return mapping

    # 3. Fallback to yf_sector if it's not "Unknown"
    if yf_sector and yf_sector != "Unknown":
        return yf_sector

    return "Unknown"
