"""
streamlit_app.py - Dashboard Kriterion Quant - Calendar Screener.

Legge i risultati committati dalla GitHub Action (data/screener_results.csv +
run_metadata.json). La dashboard NON chiama API: istantanea e tier-EODHD-indipendente.
"""

import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.charts import dot_plot_expansion_vs_rv, bar_candidates_score, history_line  # noqa: E402
from src.calendar_engine import is_etf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

st.set_page_config(page_title="Calendar Screener | Kriterion Quant",
                   page_icon="C", layout="wide", initial_sidebar_state="expanded")


@st.cache_data(ttl=900)
def load_results():
    csv = DATA / "screener_results.csv"
    meta = DATA / "run_metadata.json"
    df = pd.read_csv(csv) if csv.exists() else pd.DataFrame()
    m = json.loads(meta.read_text()) if meta.exists() else {}
    return df, m


@st.cache_data(ttl=900)
def load_history():
    h = DATA / "history.csv"
    return pd.read_csv(h) if h.exists() else pd.DataFrame()


df, meta = load_results()
# Rete di sicurezza: rimuovi eventuali ETF rimasti in un CSV generato da una versione precedente
if not df.empty:
    _tk_col = "ticker_eodhd" if "ticker_eodhd" in df.columns else "ticker"
    df = df[~df[_tk_col].astype(str).apply(is_etf)].copy()

# Sidebar
with st.sidebar:
    st.title("Calendar Screener")
    st.caption("Kriterion Quant")
    st.divider()
    if meta:
        st.metric("Candidati oggi", meta.get("n_candidates", 0))
        st.metric("Nuovi oggi", meta.get("n_new", 0))
        st.caption(f"Ultimo EOD: {meta.get('last_eod_date', 'n/d')}")
        st.caption(f"Run: {meta.get('run_utc', 'n/d')}")
        if not meta.get("data_fresh", True):
            st.warning("Dati potenzialmente stantii (festivita USA?)")
    st.divider()
    show_universe = st.checkbox("Mostra intero universo qualificato", value=False)
    if st.button("Forza aggiornamento dati"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Dati: EODHD EOD - aggiornati dalla GitHub Action notturna")

# Header
st.title("Long Calendar Screener - Mega Cap")
st.markdown("""
Shortlist giornaliera di candidati per **long calendar** (compra 50 DTE / vendi 30 DTE, hold ~14 barre)
su mega-cap liquide. Selezione sull'**unico filtro validato a prezzi reali**: l'**Expansion Tier invertito**
(preferire bassa espansione di volatilita attesa, escludere quella alta).
""")

st.error("**CONTROLLO EARNINGS MANUALE OBBLIGATORIO** - lo screener NON filtra i bilanci. "
         "Per ogni candidato verifica a mano l'assenza di earnings entro la vita della gamba corta (~30 giorni) "
         "PRIMA di mettere a mercato.")

st.info("Strategia **income corto-gamma**: vince spesso ma soffre i movimenti estremi. "
        "**Non e una copertura antifragile** - correla con un book azionario long. Dimensiona di conseguenza.")

# Riquadro strategia codificata
with st.container(border=True):
    st.markdown("#### Strategia codificata - Long Calendar Mega Cap")
    a, b, c, d = st.columns(4)
    a.markdown("**Gamba LUNGA**  \nBuy **50 DTE**  \nDelta circa **0.50** (ATM)")
    b.markdown("**Gamba CORTA**  \nSell **30 DTE**  \nDelta circa **0.50** (ATM)")
    c.markdown("**Uscita**  \nTime exit  \n**14 barre daily**")
    d.markdown("**Profilo**  \nDouble calendar (C+P)  \nCorto gamma, lungo vega")
    st.caption(
        "**Ingresso**: strike ATM via delta 0.50 su entrambe le gambe, stesso strike (double calendar call+put). "
        "**Gestione**: hold a tempo (14 barre); profit target +15-25% opzionale, alza il win rate a EV invariato. "
        "**Selezione**: Expansion Tier basso (escluso HIGH >=3), vol non estrema (anti-TSLA), liquidita >= 50M$, "
        "ranking Borda, top-N. **Earnings**: esclusione manuale prima dell'ingresso."
    )

# Banner demo
_last = str(meta.get("last_eod_date", ""))
if ("demo" in _last.lower()) or ("placeholder" in _last.lower()):
    st.warning("**Stai vedendo i dati DEMO** (placeholder sintetici). La prima esecuzione reale della "
               "GitHub Action li sovrascrive. Se l'hai gia lanciata e vedi ancora questo avviso, controlla i "
               "permessi di scrittura della Action e svuota la cache (pulsante nella sidebar).")

if df.empty:
    st.warning("Nessun risultato disponibile. Attendi la prima esecuzione della GitHub Action "
               "(o lancia `python -m src.pipeline` in locale con EODHD_API_KEY).")
    st.stop()

# KPI
cand = df[df["is_candidate"]].sort_values("borda_rank").copy()
if "is_new" not in cand.columns:
    cand["is_new"] = False
if "days_as_candidate" not in cand.columns:
    cand["days_as_candidate"] = 0
new_cand = cand[cand["is_new"]]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Candidati", len(cand))
c2.metric("Nuovi oggi", len(new_cand))
c3.metric("Universo qualificato", len(df))
c4.metric("Exp.ratio mediano", f"{cand['expansion_ratio'].median():.2f}")
c5.metric("RV mediana", f"{cand['rv_current'].median():.1f}%")
st.divider()

# Nuovi candidati = operazioni da aprire
st.subheader("Nuovi candidati oggi - operazioni da aprire")
if len(new_cand):
    st.success("Questi nomi NON erano candidati nella run precedente: sono i trade nuovi da valutare. "
               "I candidati gia presenti ieri sono probabilmente posizioni che hai gia aperto.")
    st.markdown("### " + "  ".join(f"`{t}`" for t in new_cand["ticker"]))
else:
    st.info("Nessun nuovo candidato rispetto alla run precedente: shortlist invariata. "
            "Controlla i giorni-in-lista per eventuali re-entry oltre i 14 giorni.")
st.divider()

# Tabella candidati
st.subheader("Candidati del giorno")
st.markdown("Ordinati per **Borda rank** (1 = priorita). `expansion_ratio` basso = edge migliore. "
            "Colonna Stato: NUOVO o giorni consecutivi in lista.")

table = cand.copy()
table["stato"] = table.apply(
    lambda r: "NUOVO" if r["is_new"] else f"{int(r['days_as_candidate'])}g in lista", axis=1)
table["earnings"] = "verifica manuale"
view_cols = ["borda_rank", "ticker", "stato", "close", "rv_current", "rv_percentile",
             "expansion_ratio", "tier", "dollar_volume_30d", "last_date", "earnings"]
view_cols = [c for c in view_cols if c in table.columns]
st.dataframe(
    table[view_cols].rename(columns={
        "borda_rank": "Rank", "ticker": "Ticker", "stato": "Stato", "close": "Prezzo",
        "rv_current": "RV %", "rv_percentile": "RV pctl", "expansion_ratio": "Exp.ratio",
        "tier": "Tier", "dollar_volume_30d": "$Vol 30d", "last_date": "EOD"}),
    use_container_width=True, hide_index=True)

# Dot plot
st.subheader("Mappa di selezione")
st.markdown("Ogni punto e un ticker qualificato. **Verdi = candidati.** Piu a sinistra (bassa espansione attesa) "
            "= edge migliore; la fascia ombreggiata e la banda di RV centrale dell'universo.")
st.plotly_chart(dot_plot_expansion_vs_rv(df), use_container_width=True)

col_a, col_b = st.columns(2)
with col_a:
    st.plotly_chart(bar_candidates_score(df), use_container_width=True)
with col_b:
    hist = load_history()
    if not hist.empty:
        st.plotly_chart(history_line(hist), use_container_width=True)
    else:
        st.caption("Storico non ancora disponibile (si popola dopo alcune run).")

# Universo completo opzionale
if show_universe:
    st.subheader("Universo qualificato completo")
    st.dataframe(df.sort_values("borda_rank"), use_container_width=True, hide_index=True)

# Metodologia
with st.expander("Metodologia e avvertenze (leggere)"):
    st.markdown("""
**Strategia.** Long calendar: compra ~50 DTE, vende ~30 DTE (stesso strike ATM, delta 0.50, double
calendar call+put), hold ~14 barre daily (time exit). Profilo: corto gamma a breve, lungo vega.

**Edge validato.** Su 554 trade reali (OptionOmega, 5 mega-cap) l'Expansion Tier predice **al contrario**
rispetto allo straddle: INSUFFICIENT (`rv_52w_max/rv_current` < 1.5) +9.5%, HIGH (>=3) -1.5%.

**Filtri.** Liquidita (dollar volume 30/90gg >= 50M$); escluso tier HIGH (ratio >= 3); esclusa vol estrema
(decile piu volatile o RV > 65%); ranking Borda (expansion asc + vicinanza mediana RV); top-N; **ETF esclusi**.

**Limiti.** Solo RV/prezzo, nessun dato IV (verifica al broker). Earnings non filtrati (check manuale).
Non antifragile (income corto-gamma). Edge validato su 5 nomi: conferma su universo piu ampio.
""")

st.caption(f"Dashboard generata {datetime.now().strftime('%d/%m/%Y %H:%M')} - dati EODHD via GitHub Action.")
