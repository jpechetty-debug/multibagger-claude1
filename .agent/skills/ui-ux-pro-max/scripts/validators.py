"""
UI/UX Pro Max — CSV row validators (Pydantic v2).
Called once on CSV load; not in the hot BM25 search path.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, field_validator, model_validator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex(v: str) -> str:
    """Validate hex color; allow empty strings for optional palettes."""
    if v and not v.startswith("#"):
        raise ValueError(f"Expected hex color starting with '#', got: {v!r}")
    return v


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

class ColorRow(BaseModel):
    product_type: str
    primary: str
    secondary: str = ""
    accent: str = ""
    background: str = ""
    foreground: str = ""
    on_primary: str = ""
    muted: str = ""
    border: str = ""
    destructive: str = ""
    ring: str = ""
    notes: str = ""

    _val_hex = field_validator(
        "primary", "secondary", "accent", "background",
        "foreground", "on_primary", "muted", "border",
        "destructive", "ring", mode="before"
    )(_hex)

    @model_validator(mode="before")
    @classmethod
    def normalise_keys(cls, data: dict) -> dict:
        """Map CSV header names (with spaces/special chars) to field names."""
        mapping = {
            "Product Type": "product_type",
            "Primary": "primary",
            "Secondary": "secondary",
            "Accent": "accent",
            "Background": "background",
            "Foreground": "foreground",
            "On Primary": "on_primary",
            "Muted": "muted",
            "Border": "border",
            "Destructive": "destructive",
            "Ring": "ring",
            "Notes": "notes",
        }
        return {mapping.get(k, k): v for k, v in data.items()}


class StyleRow(BaseModel):
    style_category: str
    type_: str = ""
    keywords: str = ""
    best_for: str = ""
    complexity: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalise_keys(cls, data: dict) -> dict:
        mapping = {
            "Style Category": "style_category",
            "Type": "type_",
            "Keywords": "keywords",
            "Best For": "best_for",
            "Complexity": "complexity",
        }
        return {mapping.get(k, k): v for k, v in data.items()}


class TypographyRow(BaseModel):
    font_pairing_name: str
    category: str = ""
    heading_font: str = ""
    body_font: str = ""
    google_fonts_url: str = ""
    mood_keywords: str = ""
    best_for: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalise_keys(cls, data: dict) -> dict:
        mapping = {
            "Font Pairing Name": "font_pairing_name",
            "Category": "category",
            "Heading Font": "heading_font",
            "Body Font": "body_font",
            "Google Fonts URL": "google_fonts_url",
            "Mood/Style Keywords": "mood_keywords",
            "Best For": "best_for",
            # Merged google-fonts columns (may be absent — use defaults)
            "Family": "font_pairing_name",
            "Popularity Rank": "best_for",
        }
        return {mapping.get(k, k): v for k, v in data.items()}


class UXGuidelineRow(BaseModel):
    category: str
    issue: str
    platform: str = ""
    severity: str = "MEDIUM"
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalise_keys(cls, data: dict) -> dict:
        mapping = {
            "Category": "category",
            "Issue": "issue",
            "Platform": "platform",
            "Severity": "severity",
            "Description": "description",
        }
        return {mapping.get(k, k): v for k, v in data.items()}


class ChartRow(BaseModel):
    data_type: str
    best_chart_type: str = ""
    keywords: str = ""
    accessibility_grade: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalise_keys(cls, data: dict) -> dict:
        mapping = {
            "Data Type": "data_type",
            "Best Chart Type": "best_chart_type",
            "Keywords": "keywords",
            "Accessibility Grade": "accessibility_grade",
        }
        return {mapping.get(k, k): v for k, v in data.items()}


# ---------------------------------------------------------------------------
# Domain → model registry
# ---------------------------------------------------------------------------

DOMAIN_VALIDATORS: dict[str, type[BaseModel]] = {
    "color":      ColorRow,
    "style":      StyleRow,
    "typography": TypographyRow,
    "ux":         UXGuidelineRow,
    "chart":      ChartRow,
}


def validate_rows(domain: str, rows: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Validate all rows for a domain.

    Returns:
        (valid_rows, error_messages)
    Only rows that fail validation are excluded; errors are non-fatal.
    """
    model = DOMAIN_VALIDATORS.get(domain)
    if model is None:
        return rows, []  # No validator for this domain — pass through

    valid, errors = [], []
    for i, row in enumerate(rows):
        try:
            model.model_validate(row)
            valid.append(row)
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")

    return valid, errors
