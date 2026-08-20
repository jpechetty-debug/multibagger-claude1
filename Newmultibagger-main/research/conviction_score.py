from typing import Optional
from pydantic import BaseModel
from db.engine import get_session
from db.models import Multibagger, InvestmentThesis
from core.observability.logger import get_logger

_log = get_logger("research.conviction_score")

class ConvictionScorecard(BaseModel):
    business_quality: float
    management_quality: float
    valuation: float
    thesis_health: float
    total_score: float
    label: str


class ConvictionEngine:
    """
    Calculates the holistic Conviction Score for a stock.
    It combines Business, Management, Valuation, and Thesis metrics.
    """

    @staticmethod
    def calculate(ticker: str) -> Optional[ConvictionScorecard]:
        try:
            with next(get_session()) as session:
                stock = session.query(Multibagger).filter_by(symbol=ticker).first()
                if not stock:
                    return None

                thesis = session.query(InvestmentThesis).filter_by(ticker=ticker).order_by(InvestmentThesis.created_at.desc()).first()

                # Business Quality (Max 30)
                b_score = 0
                if getattr(stock, 'roe', 0) > 20: b_score += 10
                if getattr(stock, 'sales_growth', 0) > 15: b_score += 10
                if getattr(stock, 'cfo_pat_ratio', 0) > 0.8: b_score += 10

                # Management Quality (Max 20)
                m_score = 0
                if getattr(stock, 'promoter_holding', 0) > 50: m_score += 10
                if getattr(stock, 'inst_holding', 0) > 15: m_score += 10

                # Valuation (Max 20)
                v_score = 0
                pe = getattr(stock, 'pe_ratio', 0)
                cagr = thesis.expected_cagr if thesis else getattr(stock, 'sales_cagr_5y', 15)
                if pe > 0 and pe < cagr:
                    v_score = 20
                elif pe > 0 and pe < (cagr * 1.5):
                    v_score = 10

                # Thesis Health (Max 30)
                t_score = 15 # Default neutral
                if thesis and thesis.health_score:
                    t_score = (thesis.health_score / 100.0) * 30.0

                total = b_score + m_score + v_score + t_score

                if total >= 80:
                    label = "Very High"
                elif total >= 60:
                    label = "High"
                elif total >= 40:
                    label = "Medium"
                else:
                    label = "Low"

                return ConvictionScorecard(
                    business_quality=b_score,
                    management_quality=m_score,
                    valuation=v_score,
                    thesis_health=t_score,
                    total_score=total,
                    label=label
                )

        except Exception as e:
            _log.error(f"Failed to calculate conviction for {ticker}: {e}")
            return None
