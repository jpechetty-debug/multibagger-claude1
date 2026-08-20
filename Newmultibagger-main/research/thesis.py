import os
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional, List

from db.engine import get_session
from db.models import InvestmentThesis as DBInvestmentThesis
from core.observability.logger import get_logger

_log = get_logger("research.thesis")

# The root directory for markdown artifacts
ARTIFACTS_DIR = Path("artifacts/research_memos")


class InvestmentThesis(BaseModel):
    ticker: str
    thesis_summary: str
    expected_cagr: float
    horizon_years: float
    health_score: Optional[float] = None


class ThesisManager:
    """
    Manages Investment Theses using hybrid storage (SQLite + Markdown).
    """

    @staticmethod
    def create_thesis(thesis: InvestmentThesis, full_markdown_content: str) -> bool:
        """
        Creates a new thesis record in SQLite and saves the full markdown content to disk.
        """
        # 1. SQLite Storage
        try:
            with next(get_session()) as session:
                db_thesis = DBInvestmentThesis(
                    ticker=thesis.ticker,
                    thesis_summary=thesis.thesis_summary,
                    expected_cagr=thesis.expected_cagr,
                    horizon_years=thesis.horizon_years,
                    health_score=thesis.health_score,
                )
                session.add(db_thesis)
                session.commit()
                _log.info(f"Saved structured thesis for {thesis.ticker} to SQLite.")
        except Exception as e:
            _log.error(f"Failed to save thesis to DB for {thesis.ticker}: {e}")
            return False

        # 2. Markdown Storage
        try:
            ticker_dir = ARTIFACTS_DIR / thesis.ticker
            ticker_dir.mkdir(parents=True, exist_ok=True)
            file_path = ticker_dir / "thesis.md"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(full_markdown_content)
            _log.info(f"Saved full markdown thesis for {thesis.ticker} to {file_path}")
        except Exception as e:
            _log.error(f"Failed to save thesis markdown for {thesis.ticker}: {e}")
            return False

        return True

    @staticmethod
    def get_thesis(ticker: str) -> Optional[dict]:
        """
        Retrieves the structured thesis from SQLite and the markdown content if available.
        """
        result = {}
        try:
            with next(get_session()) as session:
                db_thesis = session.query(DBInvestmentThesis).filter_by(ticker=ticker).order_by(DBInvestmentThesis.created_at.desc()).first()
                if db_thesis:
                    result["structured"] = {
                        "ticker": db_thesis.ticker,
                        "thesis_summary": db_thesis.thesis_summary,
                        "expected_cagr": db_thesis.expected_cagr,
                        "horizon_years": db_thesis.horizon_years,
                        "health_score": db_thesis.health_score,
                        "created_at": db_thesis.created_at.isoformat() if db_thesis.created_at else None,
                        "updated_at": db_thesis.updated_at.isoformat() if db_thesis.updated_at else None,
                    }
        except Exception as e:
            _log.error(f"Failed to retrieve thesis from DB for {ticker}: {e}")

        # Attempt to load markdown
        file_path = ARTIFACTS_DIR / ticker / "thesis.md"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    result["markdown"] = f.read()
            except Exception as e:
                _log.warning(f"Could not read markdown for {ticker}: {e}")
        else:
            result["markdown"] = None

        return result if result else None
