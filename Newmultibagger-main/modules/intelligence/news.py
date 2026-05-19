import asyncio
from datetime import datetime

import yfinance as yf

from modules.retry_utils import run_with_exponential_backoff


async def get_stock_news(symbol):
    """
    Fetch latest news for a stock symbol using yfinance.
    """
    try:
        ticker = yf.Ticker(symbol)

        # Fetch Yahoo news
        raw_news = await run_with_exponential_backoff(
            lambda: asyncio.to_thread(lambda: ticker.news),
            context=f"yfinance news for {symbol}",
        )

        if not raw_news:
            return []

        processed_news = []
        for item in raw_news[:10]:
            content = item.get("content", item)
            title = content.get("title", "No Title")

            provider_data = content.get("provider", {})
            if isinstance(provider_data, dict):
                publisher = provider_data.get("displayName", "News")
            else:
                publisher = str(provider_data)

            link = (
                content.get("clickThroughUrl", {}).get("url")
                or content.get("canonicalUrl", {}).get("url")
                or content.get("link")
            )

            try:
                pub_date = content.get("pubDate")
                if pub_date:
                    dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    published_at = dt.strftime("%Y-%m-%d %H:%M")
                else:
                    ts = content.get("providerPublishTime", 0)
                    if ts > 0:
                        published_at = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                    else:
                        published_at = "Recent"
            except Exception:
                published_at = "Recent"

            related_tickers = content.get("relatedTickers") or item.get("relatedTickers") or []

            processed_news.append(
                {
                    "id": item.get("id"),
                    "title": title,
                    "publisher": publisher,
                    "link": link,
                    "published": published_at,
                    "related_tickers": related_tickers,
                    "sentiment_score": None,
                    "sentiment_label": "N/A",
                }
            )

        return processed_news
    except Exception as exc:
        print(f"Error fetching news for {symbol}: {exc}")
        return []
