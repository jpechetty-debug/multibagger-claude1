import logging
from datetime import datetime, date
import aiohttp
from typing import Any

logger = logging.getLogger(__name__)

# Default NSE Headers to bypass basic blocks
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

class NSEScraper:
    def __init__(self):
        self.base_url = "https://www.nseindia.com"
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=NSE_HEADERS)
        # Hit the homepage first to get necessary cookies
        try:
            async with self.session.get(self.base_url, timeout=10) as resp:
                await resp.read()
        except Exception as e:
            logger.warning(f"Failed to fetch NSE homepage cookies: {e}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_sast_data(self) -> list[dict[str, Any]]:
        """Fetch Substantial Acquisition of Shares and Takeovers (SAST) data."""
        if not self.session:
            raise RuntimeError("Session not initialized. Use async with context manager.")

        url = f"{self.base_url}/api/corporate-sast"
        try:
            async with self.session.get(url, headers=NSE_HEADERS, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", [])
                else:
                    logger.error(f"Failed to fetch SAST data. Status: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching SAST data: {e}")
            return []

    async def fetch_block_deals(self) -> list[dict[str, Any]]:
        """Fetch Block Deals data."""
        if not self.session:
            raise RuntimeError("Session not initialized. Use async with context manager.")

        url = f"{self.base_url}/api/block-deal"
        try:
            async with self.session.get(url, headers=NSE_HEADERS, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", [])
                else:
                    logger.error(f"Failed to fetch Block Deals data. Status: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching Block Deals data: {e}")
            return []

def parse_nse_date(date_str: str) -> date:
    """Parse common NSE date formats."""
    formats = ["%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return datetime.now().date()
