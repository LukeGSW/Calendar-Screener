"""
calendar_engine.py - Motore quantitativo del Kriterion Quant CALENDAR Screener.

Seleziona candidati per LONG CALENDAR (long 50DTE / short 30DTE) su mega-cap liquide,
usando SOLO dati EOD OHLCV (nessun dato di opzioni / IV richiesto).

EDGE VALIDATO (OptionOmega, 554 trade su 5 mega-cap): l'Expansion Tier predice il calendar
AL CONTRARIO dello straddle. INSUFFICIENT (rv_52w_max/rv_current < 1.5) reso +9.5%,
HIGH (>= 3.0) reso -1.5%. Il calendar e' corto-gamma: vuole bassa espansione attesa.

ATTENZIONE: non antifragile (income corto-gamma). Earnings NON filtrati -> check manuale.
"""

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Parametri
RV_WINDOW: int            = 14
RV_SHORT_WINDOW: int      = 5
PERCENTILE_LOOKBACK: int  = 252
RV_52W_WINDOW: int        = 252
ANNUALIZATION: float      = np.sqrt(252)

MIN_DOLLAR_VOLUME: float  = 50_000_000.0
EXPANSION_EXCLUDE_GTE: float = 3.0          # escludi tier HIGH
VOL_EXTREME_PERCENTILE: float = 90.0        # esclude decile piu' volatile
VOL_EXTREME_ABS_CAP: float    = 0.65        # ...o cap assoluto 65%
TOP_N: int = 9
STALE_MAX_DAYS: int = 5   # scarta ticker con ultimo EOD troppo vecchio (delisted/acquisiti)

TIER_INSUFFICIENT = 1.5
TIER_LOW          = 2.0
TIER_HIGH         = 3.0
MIN_VALID_RV_VALUES: int = PERCENTILE_LOOKBACK

# Esclusione ETF/ETN (solo single-name). Rete di sicurezza tier-indipendente.
ETF_BLOCKLIST = {
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "IVV", "MDY", "RSP",
    "XLF", "XLE", "XLK", "XLV", "XLU", "XLP", "XLY", "XLI", "XLB", "XLRE", "XLC",
    "SMH", "SOXX", "XBI", "IBB", "KRE", "KBE", "XOP", "OIH", "XME", "XRT", "XHB",
    "ITB", "XTL", "IYR", "VNQ", "GLD", "SLV", "GDX", "GDXJ", "USO", "UNG", "DBC",
    "DBA", "SLX", "TLT", "IEF", "SHY", "HYG", "LQD", "AGG", "BND", "TIP", "EMB",
    "MUB", "BKLN", "EEM", "EFA", "FXI", "EWZ", "EWJ", "EWW", "EWT", "EWY", "INDA",
    "RSX", "VEA", "VWO", "IEMG", "ASHR", "KWEB", "MCHI", "ARKK", "ARKG", "ARKW",
    "ARKF", "ARKQ", "VXX", "UVXY", "SVXY", "VIXY", "SQQQ", "TQQQ", "SPXL", "SPXU",
    "SOXL", "SOXS", "TNA", "TZA", "LABU", "LABD", "FAS", "FAZ", "UPRO", "SDOW",
    "UDOW", "JETS", "TAN", "ICLN", "LIT", "BOTZ", "FINX", "HACK", "SKYY", "JNK",
    "PFF", "SCHD", "DVY", "VIG", "VYM", "USMV", "MTUM", "QUAL", "SPLV",
    "GBTC", "BITO", "ETHE", "IBIT", "FBTC", "BITX",
}


def is_etf(ticker: str) -> bool:
    """True se il ticker e' nella blocklist ETF/ETN."""
    base = ticker.replace(".US", "").replace("-", "").upper()
    return base in ETF_BLOCKLIST


def compute_log_returns(close: pd.Series) -> pd.Series:
    return np.log(close / close.shift(1))


def realized_volatility(returns: pd.Series, window: int) -> pd.Series:
    return returns.rolling(window=window, min_periods=window).std() * ANNUALIZATION


def rolling_percentile(series: pd.Series, lookback: int) -> pd.Series:
    def _pct(arr):
        cur, hist = arr[-1], arr[:-1]
        hist = hist[~np.isnan(hist)]
        if np.isnan(cur) or len(hist) == 0:
            return np.nan
        return float((hist < cur).sum() / len(hist) * 100.0)
    return series.rolling(window=lookback + 1, min_periods=lookback + 1).apply(_pct, raw=True)


def classify_tier(ratio: float) -> str:
    if pd.isna(ratio):
        return "N/A"
    if ratio < TIER_INSUFFICIENT:
        return "INSUFFICIENT"
    if ratio < TIER_LOW:
        return "LOW"
    if ratio < TIER_HIGH:
        return "MEDIUM"
    return "HIGH"


def analyze_ticker(ticker: str, ohlcv: pd.DataFrame) -> Optional[dict]:
    """Metriche per un singolo ticker. None se non passa i gate liquidita'/storia."""
    if ohlcv is None or ohlcv.empty:
        return None
    if not {"adjusted_close", "volume"}.issubset(ohlcv.columns):
        return None

    df = ohlcv.sort_index().dropna(subset=["adjusted_close"])
    if len(df) < RV_52W_WINDOW + RV_WINDOW + 30:
        return None

    close = df["adjusted_close"]
    volume = df["volume"].fillna(0)
    last_close = float(close.iloc[-1])

    dv_30 = float(volume.rolling(30, min_periods=30).mean().iloc[-1]) * last_close
    dv_90 = float(volume.rolling(90, min_periods=90).mean().iloc[-1]) * last_close
    if np.isnan(dv_30) or np.isnan(dv_90) or dv_30 < MIN_DOLLAR_VOLUME or dv_90 < MIN_DOLLAR_VOLUME:
        return None

    logret = compute_log_returns(close)
    rv_long = realized_volatility(logret, RV_WINDOW)
    rv_short = realized_volatility(logret, RV_SHORT_WINDOW)
    if int(rv_long.notna().sum()) < MIN_VALID_RV_VALUES:
        return None

    rv_pctl_series = rolling_percentile(rv_long, PERCENTILE_LOOKBACK)
    rv_current = float(rv_long.iloc[-1])
    rv_pctl = float(rv_pctl_series.iloc[-1]) if pd.notna(rv_pctl_series.iloc[-1]) else np.nan
    if np.isnan(rv_current) or rv_current <= 0:
        return None

    rv_52w = rv_long.iloc[-RV_52W_WINDOW:]
    rv_52w_max = float(rv_52w.max())
    expansion_ratio = rv_52w_max / rv_current if rv_current > 0 else np.nan
    tier = classify_tier(expansion_ratio)

    rv_short_curr = float(rv_short.iloc[-1]) if pd.notna(rv_short.iloc[-1]) else np.nan
    term_structure = (rv_short_curr / rv_current) if (rv_current > 0 and not np.isnan(rv_short_curr)) else np.nan

    return {
        "ticker": ticker.replace(".US", ""),
        "ticker_eodhd": ticker,
        "close": round(last_close, 2),
        "rv_current": round(rv_current * 100, 2),
        "rv_percentile": round(rv_pctl, 1) if not np.isnan(rv_pctl) else None,
        "rv_52w_max": round(rv_52w_max * 100, 2),
        "expansion_ratio": round(expansion_ratio, 2) if not np.isnan(expansion_ratio) else None,
        "tier": tier,
        "rv_short": round(rv_short_curr * 100, 2) if not np.isnan(rv_short_curr) else None,
        "term_structure": round(term_structure, 3) if not np.isnan(term_structure) else None,
        "dollar_volume_30d": round(dv_30),
        "last_date": df.index[-1].date().isoformat(),
        "_rv_current_dec": rv_current,
        "_expansion_ratio": expansion_ratio if not np.isnan(expansion_ratio) else 999.0,
    }


def run_analysis(ohlcv_data: Dict[str, pd.DataFrame], top_n: int = TOP_N) -> pd.DataFrame:
    """Analisi batch + gate + Borda ranking + top-N. Ritorna tutti i qualificati ordinati."""
    rows = []
    for ticker, df in ohlcv_data.items():
        if is_etf(ticker):          # safety net: niente ETF tra i candidati
            continue
        try:
            r = analyze_ticker(ticker, df)
            if r is not None:
                rows.append(r)
        except Exception as e:
            logger.debug(f"{ticker}: errore analisi - {e}")

    if not rows:
        logger.warning("Nessun ticker ha superato i gate liquidita'/storia.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    n_input = len(df)

    # Gate freschezza per-ticker: scarta delisted/acquisiti con ultimo EOD stantio (es. JNPR)
    _ld = pd.to_datetime(df["last_date"], errors="coerce")
    _maxld = _ld.max()
    if pd.notna(_maxld):
        df = df[(_maxld - _ld).dt.days <= STALE_MAX_DAYS].copy()
    n_after_fresh = len(df)

    df = df[df["_expansion_ratio"] < EXPANSION_EXCLUDE_GTE].copy()
    n_after_tier = len(df)

    if len(df):
        vol_cut = np.percentile(df["_rv_current_dec"], VOL_EXTREME_PERCENTILE)
        cut = min(vol_cut, VOL_EXTREME_ABS_CAP)
        df = df[df["_rv_current_dec"] <= cut].copy()
    n_after_vol = len(df)

    if df.empty:
        logger.warning("Nessun candidato dopo i gate edge/vol.")
        return df

    df["rank_expansion"] = df["_expansion_ratio"].rank(method="min", ascending=True)
    median_rv = df["_rv_current_dec"].median()
    df["_vol_distance"] = (df["_rv_current_dec"] - median_rv).abs()
    df["rank_vol_band"] = df["_vol_distance"].rank(method="min", ascending=True)
    df["borda_score"] = df["rank_expansion"] + 0.5 * df["rank_vol_band"]
    df = df.sort_values(["borda_score", "rank_expansion"], ascending=[True, True]).reset_index(drop=True)
    df["borda_rank"] = np.arange(1, len(df) + 1)
    df["is_candidate"] = df["borda_rank"] <= top_n

    logger.info(f"Universo: {n_input} qual -> {n_after_fresh} freschi -> {n_after_tier} no-HIGH -> {n_after_vol} no-vol-estrema -> top {top_n}.")
    return df.drop(columns=["_rv_current_dec", "_expansion_ratio", "_vol_distance"], errors="ignore")
