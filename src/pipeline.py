"""
pipeline.py — Orchestrazione dello screener calendar.

Eseguito ogni notte dalla GitHub Action (mercato USA chiuso):
    1) legge l'universo da data/universe.txt
    2) scarica gli EOD da EODHD
    3) calcola metriche + ranking (calendar_engine)
    4) scrive data/screener_results.csv, data/run_metadata.json, accoda data/history.csv

Uso:  python -m src.pipeline      (env: EODHD_API_KEY)
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from src.data_fetcher import fetch_universe
from src.calendar_engine import run_analysis, TOP_N

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("pipeline")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY_YEARS = 4   # storia sufficiente per RV 252 + 52w max + margine


def _expected_last_session() -> str:
    """Ultima sessione di borsa USA attesa (giorno feriale precedente, UTC)."""
    d = datetime.now(timezone.utc).date()
    # se gira di notte EU, l'ultima sessione USA è ieri (o venerdì nel weekend)
    d = d - timedelta(days=1)
    while d.weekday() >= 5:  # 5=sab, 6=dom
        d = d - timedelta(days=1)
    return d.isoformat()


def load_universe() -> list:
    path = DATA / "universe.txt"
    tickers = [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]
    logger.info(f"Universo: {len(tickers)} ticker da {path.name}")
    return tickers


def main() -> int:
    api_key = os.environ.get("EODHD_API_KEY")
    if not api_key:
        logger.error("EODHD_API_KEY mancante nell'ambiente.")
        return 1

    DATA.mkdir(exist_ok=True)
    tickers = load_universe()

    end = datetime.now(timezone.utc).date().isoformat()
    start = (datetime.now(timezone.utc).date() - timedelta(days=365 * HISTORY_YEARS)).isoformat()

    logger.info(f"Fetch EOD {start} → {end} ...")
    data = fetch_universe(tickers, start, end, api_key)
    if not data:
        logger.error("Nessun dato scaricato. Interrompo senza sovrascrivere i risultati.")
        return 1

    results = run_analysis(data, top_n=TOP_N)
    if results.empty:
        logger.warning("Nessun candidato prodotto.")

    # ── Freshness: i dati riflettono l'ultima sessione attesa? ────────────────
    last_dates = [df.index[-1].date().isoformat() for df in data.values()]
    most_recent = max(last_dates) if last_dates else None
    expected = _expected_last_session()
    fresh = (most_recent is not None) and (most_recent >= expected)
    if not fresh:
        logger.warning(f"DATI POTENZIALMENTE STANTII: ultimo EOD={most_recent}, atteso>={expected} "
                       f"(probabile festività USA).")

    # ── Output principale ─────────────────────────────────────────────────────
    out_csv = DATA / "screener_results.csv"
    results.to_csv(out_csv, index=False)
    logger.info(f"Scritto {out_csv} ({len(results)} righe).")

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
        "top_n": TOP_N,
    }
    (DATA / "run_metadata.json").write_text(json.dumps(meta, indent=2))
    logger.info(f"Metadata: {meta['n_candidates']} candidati | fresh={fresh} | {meta['candidates']}")

    # ── Storico (una riga per run) ────────────────────────────────────────────
    hist_path = DATA / "history.csv"
    hist_row = pd.DataFrame([{
        "run_utc": meta["run_utc"],
        "last_eod_date": most_recent,
        "data_fresh": fresh,
        "qualified": meta["qualified"],
        "n_candidates": meta["n_candidates"],
        "candidates": ",".join(meta["candidates"]),
    }])
    if hist_path.exists():
        hist_row.to_csv(hist_path, mode="a", header=False, index=False)
    else:
        hist_row.to_csv(hist_path, index=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
