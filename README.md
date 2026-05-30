# Kriterion Quant — Calendar Screener

Screener giornaliero per **long calendar** (compra ~50 DTE / vende ~30 DTE, hold ~14 giorni di trading)
su un universo di ~291 mega-cap USA a opzioni liquide. Gira di notte via GitHub Action (mercato USA chiuso)
e produce una shortlist pronta per la mattina seguente. Una dashboard Streamlit visualizza i candidati.

> **Solo dati EOD OHLCV (EODHD).** Nessun dato di opzioni/IV richiesto → funziona anche con tier EODHD ridotti.

---

## Perché questa strategia (edge validato)

Su **554 trade reali** (OptionOmega, 5 mega-cap) il long calendar ha mostrato un edge legato all'**Expansion
Tier**, ma **invertito** rispetto allo straddle:

| Expansion Tier (`rv_52w_max / rv_current`) | ROI medio reale |
|---|---|
| INSUFFICIENT (< 1.5) — poca espansione attesa | **+9.5%** |
| LOW (1.5–2.0) | +1.2% |
| MEDIUM (2.0–3.0) | +5.7% |
| HIGH (≥ 3.0) — molta espansione attesa | **−1.5%** |

Il calendar è **corto gamma**: vuole stabilità, teme il movimento. Quindi si selezionano i nomi a **bassa
espansione attesa** e si escludono quelli ad alta. È l'unico filtro validato; il resto è igiene di rischio.

> ⚠️ **Non è una strategia antifragile.** È income corto-gamma: vince spesso, ma soffre i movimenti estremi
> e correla con un book azionario long. Dimensiona di conseguenza.

---

## Filtri

1. **Liquidità** — dollar volume 30/90gg ≥ $50M.
2. **Gate edge** — escluso tier HIGH (expansion ratio ≥ 3).
3. **Gate vol estrema** — escluso il decile più volatile dell'universo (o RV > 65%): il "problema TSLA".
4. **Ranking Borda** — expansion ratio ascendente (primario) + vicinanza alla mediana RV cross-section (tiebreak).
5. **Top-N** — shortlist dei migliori candidati (default 9, in `src/calendar_engine.py → TOP_N`).

❌ **Earnings NON filtrati**: controllo **manuale** obbligatorio prima dell'ingresso.

---

## Struttura

```
kriterion-calendar-screener/
├── app/streamlit_app.py            # Dashboard (legge i risultati committati)
├── src/
│   ├── data_fetcher.py             # Fetch EOD EODHD (solo requests)
│   ├── calendar_engine.py          # RV, expansion ratio, gate, Borda, top-N
│   ├── charts.py                   # Dot plot dark-theme
│   └── pipeline.py                 # Orchestrazione (eseguita dalla Action)
├── data/
│   ├── universe.txt                # 291 ticker (uno per riga, formato EODHD)
│   ├── screener_results.csv        # OUTPUT giornaliero (committato)
│   ├── run_metadata.json           # metadati run (committato)
│   └── history.csv                 # storico run (committato)
├── .github/workflows/daily_calendar_screener.yml
├── .streamlit/config.toml
└── requirements.txt
```

---

## Setup

### 1. GitHub
1. Crea un repo e carica questi file.
2. **Settings → Secrets and variables → Actions → New repository secret**: `EODHD_API_KEY` = tua chiave.
3. La Action gira automaticamente alle **06:00 UTC** nei giorni feriali. Avvio manuale: tab **Actions → Daily Calendar Screener → Run workflow**.

### 2. Esecuzione locale (test)
```bash
pip install -r requirements.txt
export EODHD_API_KEY="la-tua-chiave"
python -m src.pipeline          # genera data/screener_results.csv
```

### 3. Dashboard Streamlit Cloud
1. [streamlit.io/cloud](https://streamlit.io/cloud) → New app → seleziona il repo.
2. **Main file path**: `app/streamlit_app.py`.
3. Nessun secret necessario per la dashboard (legge i CSV committati).
4. Deploy → l'app si aggiorna a ogni commit della Action.

---

## Parametri (in `src/calendar_engine.py`)

| Parametro | Default | Significato |
|---|---|---|
| `TOP_N` | 9 | candidati emessi al giorno |
| `MIN_DOLLAR_VOLUME` | 50M | soglia liquidità |
| `EXPANSION_EXCLUDE_GTE` | 3.0 | esclude tier HIGH |
| `VOL_EXTREME_PERCENTILE` / `_ABS_CAP` | 90 / 0.65 | esclusione vol estrema |
| `RV_WINDOW` / `PERCENTILE_LOOKBACK` | 14 / 252 | finestre RV |

---

## Avvertenze

- **Solo RV/prezzo**: l'IV reale va verificata al broker prima dell'ingresso.
- **Earnings**: filtro manuale.
- **Edge su 5 nomi**: conferma su universo più ampio quando hai i dati opzioni.
- **Income fragile**, non antifragile.
