"""
pipeline.py - Orchestrazione dello screener calendar (eseguito dalla GitHub Action notturna).

1) legge l'universo (esclusi ETF)  2) scarica EOD da EODHD  3) calcola + rank
4) marca i NUOVI candidati  5) scrive data/screener_results.csv, run_metadata.json, history.csv

Uso:  python -m src.pipeline   (env: EODHD_API_KEY)
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from src.data_fetcher import fetch_universe
from src.calendar_engine import run_analysis, TOP_N, is_etf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("pipeline")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY_YEARS = 4


def _expected_last_session() -> str:
    """Ultima sessione di borsa USA attesa (giorno feriale precedente, UTC)."""
    d = datetime.now(timezone.utc).date() - timedelta(days=1)
    while d.weekday() >= 5:
        d = d - timedelta(days=1)
    return d.isoformat()


def load_universe() -> list:
    path = DATA / "universe.txt"
    raw = [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]
    tickers = [t for t in raw if not is_etf(t)]
    logger.info(f"Universo: {len(tickers)} ticker ({len(raw) - len(tickers)} ETF esclusi)")
    return tickers


def _previous_candidate_history(hist_path):
    """Lista ordinata (vecchio->recente) dei set di candidati delle run passate."""
    if not hist_path.exists():
        return []
    try:
        h = pd.read_csv(hist_path)
    except Exception:
        return []
    out = []
    for _, row in h.iterrows():
        c = str(row.get("candidates", "") or "")
        out.append(set(t for t in c.split(",") if t))
    return out


def _days_as_candidate(ticker, history_sets) -> int:
    """Run consecutive (a ritroso) in cui il ticker era candidato, +1 per oggi."""
    days = 1
    for s in reversed(history_sets):
        if ticker in s:
            days += 1
        else:
            break
    return days


def main() -> int:
    api_key = os.environ.get("EODHD_API_KEY")
    if not api_key:
        logger.error("EODHD_API_KEY mancante nell'ambiente.")
        return 1

    DATA.mkdir(exist_ok=True)
    tickers = load_universe()

    end = datetime.now(timezone.utc).date().isoformat()
    start = (datetime.now(timezone.utc).date() - timedelta(days=365 * HISTORY_YEARS)).isoformat()

    logger.info(f"Fetch EOD {start} -> {end} ...")
    data = fetch_universe(tickers, start, end, api_key)
    if not data:
        logger.error("Nessun dato scaricato. Interrompo senza sovrascrivere i risultati.")
        return 1

    results = run_analysis(data, top_n=TOP_N)
    if results.empty:
        logger.warning("Nessun candidato prodotto.")

    # Tracking NUOVI candidati (rispetto alle run precedenti)
    hist_path = DATA / "history.csv"
    history_sets = _previous_candidate_history(hist_path)
    prev_candidates = history_sets[-1] if history_sets else set()
    new_candidates = []
    if not results.empty:
        results["is_new"] = False
        results["days_as_candidate"] = 0
        for idx in results[results["is_candidate"]].index:
            tk = results.at[idx, "ticker"]
            is_new = tk not in prev_candidates
            results.at[idx, "is_new"] = bool(is_new)
            results.at[idx, "days_as_candidate"] = _days_as_candidate(tk, history_sets)
            if is_new:
                new_candidates.append(tk)

    # Freshness
    last_dates = [df.index[-1].date().isoformat() for df in data.values()]
    most_recent = max(last_dates) if last_dates else None
    expected = _expected_last_session()
    fresh = (most_recent is not None) and (most_recent >= expected)
    if not fresh:
        logger.warning(f"DATI STANTII? ultimo EOD={most_recent}, atteso>={expected} (festivita USA?).")

    # Output
    results.to_csv(DATA / "screener_results.csv", index=False)
    candidates = results[results["is_candidate"]] if not results.empty else results
    meta = {
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "last_eod_date": most_recent,
        "expected_session": expected,
        "data_fresh": bool(fresh),
        "universe_size": len(tickers),
        "fetched_ok": len(data),
        "qualified": int(len(results)),
        "n_candidates": int(candidates.shape[0]) if not results.empty else 0,
        "candidates": candidates["ticker"].tolist() if not results.empty else [],
        "n_new": len(new_candidates),
        "new_candidates": new_candidates,
        "top_n": TOP_N,
    }
    (DATA / "run_metadata.json").write_text(json.dumps(meta, indent=2))
    logger.info(f"Candidati: {meta['n_candidates']} | nuovi: {meta['n_new']} {new_candidates} | fresh={fresh}")

    # Storico (una riga per run)
    hist_row = pd.DataFrame([{
        "run_utc": meta["run_utc"],
        "last_eod_date": most_recent,
        "data_fresh": fresh,
        "qualified": meta["qualified"],
        "n_candidates": meta["n_candidates"],
        "n_new": meta["n_new"],
        "candidates": ",".join(meta["candidates"]),
        "new_candidates": ",".join(new_candidates),
    }])
    if hist_path.exists():
        hist_row.to_csv(hist_path, mode="a", header=False, index=False)
    else:
        hist_row.to_csv(hist_path, index=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
