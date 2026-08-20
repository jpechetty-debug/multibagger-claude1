import json
from datetime import date
from typing import Dict, Any
from pydantic import BaseModel

from db.engine import get_session
from db.models import QuarterlyReview as DBQuarterlyReview
from db.models import InvestmentThesis as DBInvestmentThesis
from db.models import Multibagger
from core.observability.logger import get_logger

_log = get_logger("research.review_engine")

class ReviewMetrics(BaseModel):
    business_health: float
    management_health: float
    valuation_health: float
    thesis_health: float


class ReviewEngine:
    """
    Calculates the THESIS HEALTH SCORE based on Business, Management, Valuation, and Thesis metrics.
    """

    @staticmethod
    def calculate_health_score(metrics: ReviewMetrics) -> float:
        """
        Weights:
        Business      40%
        Management    20%
        Valuation     20%
        Thesis        20%
        """
        score = (
            (metrics.business_health * 0.40) +
            (metrics.management_health * 0.20) +
            (metrics.valuation_health * 0.20) +
            (metrics.thesis_health * 0.20)
        )
        return min(max(score, 0.0), 100.0)

    @staticmethod
    def _evaluate_business_health(stock: Multibagger) -> float:
        # Mock evaluation: normally would compare trailing metrics against historical
        score = 50.0
        if getattr(stock, 'sales_growth', 0) > 15: score += 15
        if getattr(stock, 'roe', 0) > 15: score += 15
        if getattr(stock, 'cfo_pat_ratio', 0) > 0.8: score += 10
        if getattr(stock, 'debt_equity', 1) < 0.5: score += 10
        return min(score, 100.0)

    @staticmethod
    def _evaluate_management_health(stock: Multibagger) -> float:
        score = 50.0
        if getattr(stock, 'promoter_holding', 0) > 50: score += 20
        if getattr(stock, 'inst_holding', 0) > 15: score += 10
        # Add pledge data check if available
        return min(score, 100.0)

    @staticmethod
    def _evaluate_valuation_health(stock: Multibagger, expected_cagr: float) -> float:
        score = 50.0
        pe = getattr(stock, 'pe_ratio', 0)
        if pe > 0 and pe < expected_cagr:
            score += 30
        elif pe > expected_cagr * 2:
            score -= 20
        return min(max(score, 0.0), 100.0)

    @staticmethod
    def _evaluate_thesis_health(original_thesis: DBInvestmentThesis) -> float:
        # Without an LLM to read the triggers, we rely on user-updated health_score 
        # or a default of 75 if it's currently intact.
        if original_thesis and original_thesis.health_score is not None:
            return original_thesis.health_score
        return 75.0

    @staticmethod
    def run_review(ticker: str) -> Optional[dict]:
        """
        Runs a comprehensive review comparing original thesis against current reality.
        """
        try:
            with next(get_session()) as session:
                stock = session.query(Multibagger).filter_by(symbol=ticker).first()
                thesis = session.query(DBInvestmentThesis).filter_by(ticker=ticker).order_by(DBInvestmentThesis.created_at.desc()).first()

                if not stock or not thesis:
                    _log.warning(f"Cannot run review for {ticker}: missing stock or thesis.")
                    return None

                # Calculate components
                b_health = ReviewEngine._evaluate_business_health(stock)
                m_health = ReviewEngine._evaluate_management_health(stock)
                v_health = ReviewEngine._evaluate_valuation_health(stock, thesis.expected_cagr)
                t_health = ReviewEngine._evaluate_thesis_health(thesis)

                metrics = ReviewMetrics(
                    business_health=b_health,
                    management_health=m_health,
                    valuation_health=v_health,
                    thesis_health=t_health
                )

                final_score = ReviewEngine.calculate_health_score(metrics)

                # Determine status
                if final_score >= 80:
                    status = "Strong"
                elif final_score >= 60:
                    status = "Monitor"
                elif final_score >= 40:
                    status = "Review"
                else:
                    status = "Exit Candidate"

                # Update thesis health score
                thesis.health_score = final_score
                
                # Save review
                review = DBQuarterlyReview(
                    ticker=ticker,
                    review_date=date.today(),
                    original_assumptions=json.dumps({"expected_cagr": thesis.expected_cagr}),
                    current_reality=json.dumps({
                        "business": b_health,
                        "management": m_health,
                        "valuation": v_health,
                        "thesis": t_health
                    }),
                    health_status=status,
                    health_score=final_score
                )
                session.add(review)
                session.commit()

                _log.info(f"Review completed for {ticker}: Score {final_score:.1f} ({status})")
                return {
                    "health_score": final_score,
                    "status": status,
                    "components": metrics.model_dump()
                }

        except Exception as e:
            _log.error(f"Review engine failed for {ticker}: {e}")
            return None
