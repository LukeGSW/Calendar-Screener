"""
data_fetcher.py — Fetch dati EOD da EODHD.

Una sola dipendenza esterna: `requests`. Nessun import di streamlit qui, così il modulo
gira identico sia nella GitHub Action (headless) sia nella dashboard. Usa SOLO l'endpoint
EOD historical → compatibile anche con tier EODHD ridotti.
"""

import time
import logging
from typing import Optional

import requests
import pandas as pd

logger = logging.getLogger(__name__)

EOD_URL = "https://eodhd.com/api/eod/{ticker}"


def fetch_ohlc(ticker: str, start: str, end: str, api_key: str,
               retries: int = 3, backoff: float = 1.5) -> Optional[pd.DataFrame]:
    """
    Scarica OHLC adjusted da EODHD per un ticker.

    Args:
        ticker:  simbolo EODHD (es. 'AAPL.US', 'BRK-B.US')
        start:   data inizio YYYY-MM-DD
        end:     data fine   YYYY-MM-DD
        api_key: chiave EODHD
        retries: tentativi su errore di rete
        backoff: secondi base per il backoff lineare

    Returns:
        DataFrame [high, low, close, adjusted_close, volume] indicizzato per data,
        oppure None se non disponibile.
    """
    url = EOD_URL.format(ticker=ticker)
    params = {"from": start, "to": end, "period": "d", "api_token": api_key, "fmt": "json"}
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                return None
            df = pd.DataFrame(data)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            needed = ["high", "low", "close", "adjusted_close", "volume"]
            if not all(c in df.columns for c in needed):
                return None
            return df[needed].astype(float)
        except Exception as e:
            logger.debug(f"{ticker}: tentativo {attempt + 1}/{retries} fallito ({e})")
            time.sleep(backoff * (attempt + 1))
    logger.warning(f"{ticker}: fetch fallito dopo {retries} tentativi.")
    return None


def fetch_universe(tickers, start: str, end: str, api_key: str,
                   sleep: float = 0.12, min_rows: int = 320) -> dict:
    """
    Scarica l'intero universo. Salta i ticker senza dati o con storia insufficiente.

    Returns: dict {ticker: DataFrame}
    """
    data = {}
    n = len(tickers)
    for i, tk in enumerate(tickers):
        df = fetch_ohlc(tk, start, end, api_key)
        if df is not None and len(df) >= min_rows:
            data[tk] = df
        if (i + 1) % 25 == 0:
            logger.info(f"Fetch {i + 1}/{n} — validi: {len(data)}")
        time.sleep(sleep)
    logger.info(f"Fetch completato: {len(data)}/{n} ticker con storia sufficiente.")
    return data
