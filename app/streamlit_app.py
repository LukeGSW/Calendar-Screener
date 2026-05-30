"""
streamlit_app.py — Dashboard Kriterion Quant — Calendar Screener.

Legge i risultati committati dalla GitHub Action (data/screener_results.csv +
run_metadata.json): la dashboard NON chiama API, quindi è istantanea e gira anche
con un tier EODHD ridotto. Mostra la shortlist di candidati long-calendar del giorno.
"""

import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.charts import dot_plot_expansion_vs_rv, bar_candidates_score, history_line  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

st.set_page_config(page_title="Calendar Screener | Kriterion Quant",
                   page_icon="🗓️", layout="wide", initial_sidebar_state="expanded")


# ── Caricamento dati committati ───────────────────────────────────────────────
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

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🗓️ Calendar Screener")
    st.caption("Kriterion Quant")
    st.divider()
    if meta:
        st.metric("Candidati oggi", meta.get("n_candidates", 0))
        st.caption(f"Ultimo EOD: **{meta.get('last_eod_date', 'n/d')}**")
        st.caption(f"Run: {meta.get('run_utc', 'n/d')}")
        if not meta.get("data_fresh", True):
            st.warning("⚠️ Dati potenzialmente stantii (festività USA?)")
    st.divider()
    show_universe = st.checkbox("Mostra intero universo qualificato", value=False)
    st.caption("📡 Dati: EODHD EOD · aggiornati dalla GitHub Action notturna")

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🗓️ Long Calendar Screener — Mega Cap")
st.markdown("""
Shortlist giornaliera di candidati per **long calendar** (compra 50 DTE / vendi 30 DTE, hold ~14 giorni)
su mega-cap liquide. La selezione si basa sull'**unico filtro validato a prezzi reali**: l'**Expansion Tier
invertito** (preferire bassa espansione di volatilità attesa, escludere quella alta).
""")

st.error("⚠️ **CONTROLLO EARNINGS MANUALE OBBLIGATORIO** — lo screener NON filtra i bilanci. "
         "Per ogni candidato, verifica a mano l'assenza di earnings entro la vita della gamba corta (~30 giorni) "
         "PRIMA di mettere a mercato. Un calendar tenuto sull'evento è ad alto rischio.")

st.info("ℹ️ Questa è una strategia **income corto-gamma**: vince spesso ma soffre i movimenti estremi. "
        "**Non è una copertura antifragile** — correla con un book azionario long. Dimensiona di conseguenza.")

if df.empty:
    st.warning("Nessun risultato disponibile. Attendi la prima esecuzione della GitHub Action "
               "(o lancia `python -m src.pipeline` in locale con EODHD_API_KEY).")
    st.stop()

# ── KPI ───────────────────────────────────────────────────────────────────────
cand = df[df["is_candidate"]].sort_values("borda_rank")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Candidati", len(cand))
c2.metric("Universo qualificato", len(df))
c3.metric("Expansion ratio mediano (candidati)", f"{cand['expansion_ratio'].median():.2f}")
c4.metric("RV mediana (candidati)", f"{cand['rv_current'].median():.1f}%")
st.divider()

# ── Tabella candidati ─────────────────────────────────────────────────────────
st.subheader("📋 Candidati del giorno")
st.markdown("Ordinati per **Borda rank** (1 = priorità). `expansion_ratio` basso = edge migliore. "
            "Colonna ⚠️ = ricorda il check earnings manuale.")

table = cand.copy()
table["⚠️ earnings"] = "verifica manuale"
view_cols = ["borda_rank", "ticker", "close", "rv_current", "rv_percentile",
             "expansion_ratio", "tier", "dollar_volume_30d", "last_date", "⚠️ earnings"]
view_cols = [c for c in view_cols if c in table.columns]
st.dataframe(
    table[view_cols].rename(columns={
        "borda_rank": "Rank", "ticker": "Ticker", "close": "Prezzo",
        "rv_current": "RV %", "rv_percentile": "RV pctl",
        "expansion_ratio": "Exp.ratio", "tier": "Tier",
        "dollar_volume_30d": "$Vol 30d", "last_date": "EOD"}),
    use_container_width=True, hide_index=True)

# ── Dot plot principale ───────────────────────────────────────────────────────
st.subheader("🎯 Mappa di selezione")
st.markdown("Ogni punto è un ticker qualificato. **Verdi = candidati.** Più a sinistra (bassa espansione attesa) "
            "= edge migliore per il calendar; la fascia ombreggiata è la banda di RV centrale dell'universo.")
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

# ── Universo completo opzionale ───────────────────────────────────────────────
if show_universe:
    st.subheader("🌐 Universo qualificato completo")
    st.dataframe(df.sort_values("borda_rank"), use_container_width=True, hide_index=True)

# ── Metodologia ───────────────────────────────────────────────────────────────
with st.expander("ℹ️ Metodologia e avvertenze (leggere)"):
    st.markdown("""
**Strategia.** Long calendar: compra opzioni ~50 DTE, vende ~30 DTE (stesso strike, double calendar
call+put), hold ~14 giorni di trading. Profilo: corto gamma a breve, lungo vega.

**Edge validato.** Su 554 trade reali (OptionOmega, 5 mega-cap) l'Expansion Tier risulta predittivo
**al contrario** rispetto allo straddle: tier INSUFFICIENT (`rv_52w_max/rv_current` < 1.5) reso +9.5%,
tier HIGH (≥3) reso −1.5%. Meccanica coerente: bassa espansione attesa = niente movimento che fa
esplodere il corto-gamma.

**Filtri.**
- *Gate liquidità*: dollar volume 30/90gg ≥ $50M.
- *Gate edge*: escluso tier HIGH (expansion ratio ≥ 3).
- *Gate vol estrema*: escluso il decile più volatile dell'universo (o RV > 65%) — il "problema TSLA".
- *Ranking*: Borda = expansion ratio ascendente (primario) + vicinanza alla mediana RV (tiebreak oggettivo).
- *Selezione*: top-N candidati.

**Limiti (onestà intellettuale).**
- Solo RV/prezzo: **nessun dato di IV**. L'IV reale va verificata al broker prima dell'ingresso.
- **Earnings non filtrati**: check manuale obbligatorio.
- **Non antifragile**: income corto-gamma, fragile ai movimenti estremi, correlato col book long.
- Edge validato su 5 nomi: conferma su universo più ampio quando possibile.
""")

st.caption(f"Dashboard generata {datetime.now().strftime('%d/%m/%Y %H:%M')} · dati EODHD via GitHub Action.")
