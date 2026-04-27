from __future__ import annotations

from typing import Any


class NewsGate:
    """Governance news gate for blocking allocation on severe red flags."""

    RED_FLAG_TERMS = (
        "auditor resign",
        "auditor quits",
        "qualified opinion",
        "forensic audit",
        "sebi bars",
        "sebi ban",
        "insider trading",
        "cbi raid",
        "ed raid",
        "fraud",
        "accounting irregular",
        "pledge invocation",
        "wilful default",
        "defaulted",
        "bankruptcy",
        "insolvency",
        "nclt",
    )

    def _extract_text(self, item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            parts = []
            for key in ("title", "summary", "description", "content", "publisher"):
                value = item.get(key)
                if isinstance(value, str):
                    parts.append(value)
            return " ".join(parts)
        return str(item or "")

    def validate_news(self, symbol: str, news_items: list[Any] | None) -> tuple[bool, str]:
        if not news_items:
            return True, "No adverse news found"

        combined = " ".join(self._extract_text(item) for item in news_items).lower()
        for term in self.RED_FLAG_TERMS:
            if term in combined:
                return False, f"Governance red flag for {symbol}: {term}"

        return True, "No adverse news found"

