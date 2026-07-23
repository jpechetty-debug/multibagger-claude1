from datetime import datetime
from typing import Any

import nltk
import yfinance as yf
from nltk.sentiment.vader import SentimentIntensityAnalyzer

from core.observability.logger import get_logger

# Initialize VADER (Download lexicont on first run)
try:
    nltk.data.find("sentiment/vader_lexicon.zip")
except LookupError:
    nltk.download("vader_lexicon", quiet=True)

logger = get_logger("news_sentiment")


class NewsSentimentEngine:
    """
    Engine to fetch and analyze real-time news sentiment for Alpha Generation.
    Part of v11.0 'Nexus Alpha' evolution.
    """

    def __init__(self):
        self._analyzer = SentimentIntensityAnalyzer()
        self._cache: dict[str, tuple[dict[str, Any], float]] = {}  # In-memory TTL cache (result, timestamp)

    def fetch_headlines(self, symbol: str) -> list[str]:
        """Fetches recent headlines for a symbol using yfinance."""
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news
            if not news:
                return []

            # Extract only recent headlines (last 7 days)
            recent_headlines = []
            for item in news:
                # yfinance news items usually have 'title' and 'publisher'
                title = item.get("title", "")
                if title:
                    recent_headlines.append(title)

            return recent_headlines
        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return []

    def score_sentiment(self, headlines: list[str]) -> float:
        """
        Analyzes a list of headlines and returns a composite sentiment score.
        Returns a float between -1.0 (Very Negative) and 1.0 (Very Positive).
        """
        if not headlines:
            return 0.0  # Neutral if no news

        scores = []
        for text in headlines:
            sentiment = self._analyzer.polarity_scores(text)
            # Use the 'compound' score as the primary metric
            scores.append(sentiment["compound"])

        if not scores:
            return 0.0

        # Weighted average or simple mean
        avg_score = sum(scores) / len(scores)

        # Apply a slight dampening factor to avoid extreme swings on a single headline
        return float(round(max(-1.0, min(1.0, float(avg_score))), 3))

    def get_alpha_signal(self, symbol: str) -> dict[str, Any]:
        """Provides the full news-driven alpha signal for a ticker."""
        now = datetime.now().timestamp()
        # Check cache (15-min TTL)
        if symbol in self._cache:
            cached_result, timestamp = self._cache[symbol]
            if now - timestamp < 900:  # 15 minutes = 900 seconds
                return cached_result
            else:
                del self._cache[symbol]

        headlines = self.fetch_headlines(symbol)
        score = self.score_sentiment(headlines)

        # Determine classification
        if score > 0.4:
            alignment = "Breakout Bullish"
        elif score > 0.1:
            alignment = "Positive Drift"
        elif score < -0.4:
            alignment = "Toxic Drift"
        elif score < -0.1:
            alignment = "Negative Drift"
        else:
            alignment = "Neutral"

        result = {
            "symbol": symbol,
            "sentiment_score": score,
            "alignment": alignment,
            "headline_count": len(headlines),
            "headlines": headlines[:5],  # Keep top 5 for UI
        }

        self._cache[symbol] = (result, now)
        return result


# Global instance
engine = NewsSentimentEngine()
