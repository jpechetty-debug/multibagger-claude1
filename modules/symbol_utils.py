# modules/symbol_utils.py
"""
Sovereign AI — Symbol Canonicalization

Single source of truth for transforming raw symbol strings into the
canonical forms used by Yahoo Finance APIs and the runtime database.
"""

from __future__ import annotations

# Suffixes that map to a known exchange
_EXCHANGE_SUFFIX_MAP = {
    ".NS": ".NS",
    ".NSE": ".NS",
    ".BO": ".BO",
    ".BSE": ".BO",
    ".N": ".NS",
}

# Suffixes to strip before re-applying the canonical one
_KNOWN_SUFFIXES = tuple(_EXCHANGE_SUFFIX_MAP.keys())


def canonical_symbol(raw: str, *, default_exchange: str = ".NS") -> str:
    """Normalize a raw symbol into its canonical Yahoo Finance form.

    Examples:
        canonical_symbol("reliance")       -> "RELIANCE.NS"
        canonical_symbol("RELIANCE.N")     -> "RELIANCE.NS"
        canonical_symbol("RELIANCE.NSE")   -> "RELIANCE.NS"
        canonical_symbol("SBIN.BO")        -> "SBIN.BO"
        canonical_symbol("  tcs  ")        -> "TCS.NS"
    """
    if not raw:
        return ""

    symbol = raw.strip().upper()

    # Detect and resolve known exchange suffixes
    for suffix, canonical_suffix in _EXCHANGE_SUFFIX_MAP.items():
        if symbol.endswith(suffix.upper()):
            base = symbol[: -len(suffix)]
            return f"{base}{canonical_suffix}" if base else ""

    # No recognized suffix — apply the default exchange
    if "." not in symbol:
        return f"{symbol}{default_exchange}"

    return symbol


def db_symbol(raw: str) -> str:
    """Strip the exchange suffix for use as a database key.

    Examples:
        db_symbol("RELIANCE.NS") -> "RELIANCE"
        db_symbol("SBIN.BO")     -> "SBIN"
        db_symbol("TCS")         -> "TCS"
    """
    symbol = raw.strip().upper()
    for suffix in _KNOWN_SUFFIXES:
        if symbol.endswith(suffix.upper()):
            return symbol[: -len(suffix)]
    return symbol


def normalize_symbol(symbol: str) -> str:
    """Legacy alias — delegates to canonical_symbol()."""
    return canonical_symbol(symbol)

