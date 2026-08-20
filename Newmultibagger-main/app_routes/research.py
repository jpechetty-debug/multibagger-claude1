from fastapi import APIRouter, HTTPException
from typing import List, Optional
from datetime import date
from pydantic import BaseModel

from research.thesis import ThesisManager, InvestmentThesis
from research.journal import JournalManager, JournalEntry
from research.knowledge_base import KnowledgeBaseManager, KnowledgeEntry
from research.decision_log import DecisionLogManager, DecisionEntry
from research.review_engine import ReviewEngine
from portfolio.watchlist_manager import WatchlistManager
from intelligence.memo_generator import MemoGenerator

router = APIRouter(prefix="/research", tags=["Research (Month 5)"])


# --- Thesis ---
class ThesisPayload(BaseModel):
    ticker: str
    thesis_summary: str
    expected_cagr: float
    horizon_years: float
    full_markdown: str


@router.post("/thesis")
def create_thesis(payload: ThesisPayload):
    thesis = InvestmentThesis(
        ticker=payload.ticker,
        thesis_summary=payload.thesis_summary,
        expected_cagr=payload.expected_cagr,
        horizon_years=payload.horizon_years
    )
    success = ThesisManager.create_thesis(thesis, payload.full_markdown)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save thesis.")
    return {"status": "success"}


@router.get("/thesis/{ticker}")
def get_thesis(ticker: str):
    data = ThesisManager.get_thesis(ticker)
    if not data:
        raise HTTPException(status_code=404, detail="Thesis not found.")
    return data


# --- Journal ---
@router.post("/journal")
def add_journal(entry: JournalEntry):
    success = JournalManager.add_entry(entry)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save journal entry.")
    return {"status": "success"}


@router.get("/journal/{ticker}")
def get_journal(ticker: str):
    return JournalManager.get_entries(ticker)


# --- Decision Log ---
@router.post("/decisions")
def add_decision(entry: DecisionEntry):
    success = DecisionLogManager.add_decision(entry)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save decision.")
    return {"status": "success"}


@router.get("/decisions/{ticker}")
def get_decisions(ticker: str):
    return DecisionLogManager.get_decisions(ticker)


# --- Knowledge Base ---
class KnowledgePayload(BaseModel):
    ticker: str
    source_type: str
    source_date: date
    summary: str
    tags: Optional[str] = None
    full_markdown: str


@router.post("/knowledge")
def add_knowledge(payload: KnowledgePayload):
    entry = KnowledgeEntry(
        ticker=payload.ticker,
        source_type=payload.source_type,
        source_date=payload.source_date,
        summary=payload.summary,
        tags=payload.tags
    )
    success = KnowledgeBaseManager.add_entry(entry, payload.full_markdown)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save knowledge entry.")
    return {"status": "success"}


@router.get("/knowledge/{ticker}")
def get_knowledge(ticker: str):
    return KnowledgeBaseManager.get_entries(ticker)


# --- Review Engine ---
@router.post("/review/{ticker}")
def run_review(ticker: str):
    res = ReviewEngine.run_review(ticker)
    if not res:
        raise HTTPException(status_code=500, detail="Failed to run review.")
    return res


# --- Watchlist ---
class WatchlistUpdate(BaseModel):
    state: str
    notes: Optional[str] = None

@router.put("/watchlist/{ticker}")
def update_watchlist(ticker: str, payload: WatchlistUpdate):
    success = WatchlistManager.update_state(ticker, payload.state, payload.notes)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update watchlist.")
    return {"status": "success"}


@router.get("/portfolio")
def get_portfolio():
    return WatchlistManager.get_portfolio()


# --- Memo Generator ---
@router.get("/memo/{ticker}")
def generate_memo(ticker: str, template: str = "Compounder", use_llm: bool = False):
    memo = MemoGenerator.generate_memo(ticker, template, use_llm)
    return {"memo": memo}


# --- Trust Score ---
from research.trust_score import compute_trust_score

@router.get("/trust-score")
def get_trust_score():
    return compute_trust_score()
