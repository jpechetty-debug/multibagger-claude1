from modules.sector_mapping import get_refined_sector


def test_cable_maker_is_not_a_utility():
    assert get_refined_sector("VMARCIND.NS", "V-Marc India", "Industrials", "Cables - Electricals") == "Industrials"


def test_power_utility_still_maps():
    assert get_refined_sector("X.NS", "X Ltd", "Utilities", "Power Generation") == "Energy & Utilities"


def test_group_name_does_not_inherit_flagship_sector():
    assert get_refined_sector("RPOWER.NS", "Reliance Power Ltd", "Utilities", "Utilities - Renewable") != "Energy / O2C"


def test_exact_symbol_override_kept():
    assert get_refined_sector("RELIANCE.NS", "Reliance Industries", "Energy", "Oil & Gas") == "Energy / O2C"


def test_telecom_uses_single_label():
    assert get_refined_sector("X.NS", "X", "Communication Services", "Telecom Services") == "Communication Services"
