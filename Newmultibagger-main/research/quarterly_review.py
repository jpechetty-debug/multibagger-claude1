from core.observability.logger import get_logger
from db.engine import get_session
from db.models import InvestmentThesis
from research.review_engine import ReviewEngine

_log = get_logger("research.quarterly_review")

def run_all_reviews():
    """
    Runs the quarterly review for all tickers that have an Investment Thesis.
    """
    _log.info("Starting Quarterly Review for all active theses...")
    results = {}
    try:
        with next(get_session()) as session:
            theses = session.query(InvestmentThesis).all()
            for t in theses:
                res = ReviewEngine.run_review(t.ticker)
                if res:
                    results[t.ticker] = res
                    
        _log.info(f"Quarterly Review complete. Processed {len(results)} theses.")
        return results
    except Exception as e:
        _log.error(f"Quarterly review failed: {e}")
        return {}

if __name__ == "__main__":
    import json
    data = run_all_reviews()
    print(json.dumps(data, indent=2))
