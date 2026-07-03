import os
from datetime import datetime, timedelta

import joblib
import numpy as np
import pandas as pd
import yfinance as yf
from hmmlearn.hmm import GaussianHMM
from core.observability.logger import get_logger
_log = get_logger("modules.risk.regime_hmm")

MODEL_PATH = os.path.join("runtime", "models", "market_regime_hmm.pkl")


class RegimeHMM:
    """
    Identifies market regimes (Bullish, Bearish, Volatile) using a Hidden Markov Model.
    """

    def __init__(self, model_path=MODEL_PATH):
        self.model_path = model_path
        self.model = None
        self._cached_regime = None
        self._cached_regime_date = None
        self._load_model()

    def _load_model(self):
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
            except Exception as e:
                _log.error(f"Error loading HMM model: {e}")

    def fetch_index_data(self, ticker="^NSEI", years=5):
        """Fetches historical returns for an index."""
        start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
        data = yf.download(ticker, start=start, progress=False)
        if data.empty:
            return pd.Series()

        # Calculate daily log returns
        close = data["Close", ticker] if isinstance(data.columns, pd.MultiIndex) else data["Close"]

        returns = np.log(close / close.shift(1)).dropna()
        return returns

    def train(self, ticker="^NSEI", n_components=3):
        """Trains the Gaussian HMM on index returns."""
        returns = self.fetch_index_data(ticker)
        if len(returns) < 500:
            _log.info("Insufficient data for HMM training.")
            return False

        # Reshape for hmmlearn
        X = returns.values.reshape(-1, 1)

        _log.info(f"Training HMM with {n_components} states on {ticker}...")
        self.model = GaussianHMM(
            n_components=n_components, covariance_type="full", n_iter=1000, random_state=42
        )
        self.model.fit(X)

        # Save model
        joblib.dump(self.model, self.model_path)
        _log.info(f"HMM Model saved to {self.model_path}")
        return True

    def predict_regime(self, ticker="^NSEI", target_date=None):
        """
        Predicts the current regime for the index at a specific target_date.
        If target_date is None, uses datetime.now().
        Returns: String (BULLISH, BEARISH, VOLATILE)
        """
        if not self.model:
            # Try to train if model missing
            if not self.train(ticker):
                return "VOLATILE"  # Default fallback

        # Determine the time window
        target_dt = datetime.now() if target_date is None else pd.to_datetime(target_date)

        # Check cache
        if self._cached_regime and self._cached_regime_date:
            if (target_dt - self._cached_regime_date).days == 0:
                return self._cached_regime

        # Fetch trailing 90 days to get state sequence
        start_dt = target_dt - timedelta(days=90)
        try:
            data = yf.download(
                ticker,
                start=start_dt.strftime("%Y-%m-%d"),
                end=target_dt.strftime("%Y-%m-%d"),
                progress=False,
            )
        except Exception as e:
            _log.error(f"Error fetching data for HMM prediction: {e}")
            return "VOLATILE"

        if data.empty:
            _log.warning("HMM prediction: No data retrieved, returning VOLATILE")
            return "VOLATILE"

        close = data["Close", ticker] if isinstance(data.columns, pd.MultiIndex) else data["Close"]

        returns = np.log(close / close.shift(1)).dropna()
        if len(returns) < 10:
            _log.warning("HMM prediction: Insufficient returns data, returning VOLATILE")
            return "VOLATILE"

        X = returns.values.reshape(-1, 1)

        try:
            # Predict hidden states for the sequence
            hidden_states = self.model.predict(X)  # type: ignore
            current_state = hidden_states[-1]
            
            regime = self._map_state_to_regime(current_state)
            self._cached_regime = regime
            self._cached_regime_date = target_dt
            return regime
        except Exception as e:
            _log.error(f"Error during HMM prediction: {e}")
            return "VOLATILE"

    def _map_state_to_regime(self, state_idx):
        """
        Maps a hidden state index to a regime label.
        Regimes:
        - Bullish: High mean, Low variance
        - Bearish: Low (negative) mean, High variance
        - Volatile/Sideways: Near-zero mean, High variance
        """
        means = self.model.means_.flatten()  # type: ignore
        covars = self.model.covars_.flatten()  # type: ignore

        means[state_idx]
        covars[state_idx]

        # Sorting states by mean to identify Bull/Bear
        sorted_indices = np.argsort(means)

        if state_idx == sorted_indices[-1]:
            return "BULLISH"
        elif state_idx == sorted_indices[0]:
            return "BEARISH"
        else:
            return "VOLATILE"


if __name__ == "__main__":
    hmm = RegimeHMM()
    regime = hmm.predict_regime()
    _log.info(f"Current Market Regime (HMM): {regime}")
