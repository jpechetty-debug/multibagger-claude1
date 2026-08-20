import json
from db.engine import get_session
from db.models import Multibagger
from intelligence.llm_provider import get_llm_provider
from research.thesis_templates import get_template
from core.observability.logger import get_logger

_log = get_logger("intelligence.memo_generator")


class MemoGenerator:
    """
    Generates Investment Memos based on Phase 1 (Deterministic Facts) 
    and Phase 2 (LLM Narrative).
    """

    @staticmethod
    def _gather_facts(ticker: str) -> dict:
        try:
            with next(get_session()) as session:
                stock = session.query(Multibagger).filter_by(symbol=ticker).first()
                if not stock:
                    return {}

                return {
                    "ticker": stock.symbol,
                    "business_quality": {
                        "roe": getattr(stock, 'roe', None),
                        "avg_roe_5y": getattr(stock, 'avg_roe_5y', None),
                        "cfo_pat_ratio": getattr(stock, 'cfo_pat_ratio', None),
                    },
                    "growth": {
                        "sales_growth": getattr(stock, 'sales_growth', None),
                        "sales_cagr_5y": getattr(stock, 'sales_cagr_5y', None),
                    },
                    "risk": {
                        "debt_equity": getattr(stock, 'debt_equity', None),
                        "f_score": getattr(stock, 'f_score', None),
                    },
                    "valuation": {
                        "pe_ratio": getattr(stock, 'pe_ratio', None),
                        "peg_ratio": getattr(stock, 'peg_ratio', None),
                    },
                }
        except Exception as e:
            _log.error(f"Failed to gather facts for {ticker}: {e}")
            return {}

    @staticmethod
    def generate_memo(ticker: str, template_type: str = "Compounder", use_llm: bool = False) -> str:
        """
        Generates a memo. If use_llm is False, returns Phase 1 (deterministic facts).
        If use_llm is True, calls the configured LLM provider to format it.
        """
        facts = MemoGenerator._gather_facts(ticker)
        if not facts:
            return f"No data available to generate memo for {ticker}."

        template = get_template(template_type)

        if not use_llm:
            # Phase 1: Deterministic
            memo = f"# {ticker} Investment Memo - Phase 1 (Deterministic)\n\n"
            memo += "## Facts\n```json\n" + json.dumps(facts, indent=2) + "\n```\n\n"
            memo += "## Structure\n" + template
            return memo

        # Phase 2: LLM Narrative
        llm = get_llm_provider("mock") # Defaulting to mock for now
        system_prompt = "You are a hedge fund analyst. Write a highly institutional investment memo based on these facts and the provided template."
        user_prompt = f"Facts: {json.dumps(facts)}\n\nTemplate: {template}"
        
        narrative = llm.generate(system_prompt, user_prompt)
        return narrative
