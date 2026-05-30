"""
charts.py — Grafici Plotly dark-theme per la dashboard calendar.
Ogni funzione ritorna un go.Figure pronto per st.plotly_chart().
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

COLORS = {
    "primary": "#2196F3", "secondary": "#FF9800", "positive": "#4CAF50",
    "negative": "#F44336", "neutral": "#9E9E9E", "background": "#1E1E2E",
    "surface": "#2A2A3E", "text": "#E0E0E0", "accent": "#AB47BC",
}


def _layout(title, x="", y=""):
    return dict(
        title=dict(text=title, font=dict(size=16, color=COLORS["text"])),
        paper_bgcolor=COLORS["background"], plot_bgcolor=COLORS["surface"],
        font=dict(color=COLORS["text"], family="Inter, Arial, sans-serif"),
        xaxis=dict(title=x, showgrid=True, gridcolor="#333355", zeroline=False, color=COLORS["text"]),
        yaxis=dict(title=y, showgrid=True, gridcolor="#333355", zeroline=False, color=COLORS["text"]),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#444466"),
        margin=dict(l=60, r=20, t=60, b=60), height=480,
    )


def dot_plot_expansion_vs_rv(df: pd.DataFrame) -> go.Figure:
    """
    Dot plot principale: Expansion Ratio (x) vs RV corrente (y).
    Universo qualificato in grigio, candidati evidenziati. Più a SINISTRA = edge migliore
    (bassa espansione attesa). La banda della mediana RV è ombreggiata.
    """
    fig = go.Figure()
    base = df[~df["is_candidate"]]
    cand = df[df["is_candidate"]]

    # banda vol target (mediana cross-section) ombreggiata
    if len(df):
        med = df["rv_current"].median()
        q1, q3 = df["rv_current"].quantile(0.25), df["rv_current"].quantile(0.75)
        fig.add_hrect(y0=q1, y1=q3, fillcolor=COLORS["primary"], opacity=0.06, line_width=0)
        fig.add_hline(y=med, line_color=COLORS["neutral"], line_dash="dot",
                      annotation_text="mediana RV", annotation_font_color=COLORS["text"])

    fig.add_trace(go.Scatter(
        x=base["expansion_ratio"], y=base["rv_current"], mode="markers",
        name="universo qualificato",
        marker=dict(size=8, color=COLORS["neutral"], opacity=0.45),
        text=base["ticker"], hovertemplate="%{text}<br>exp=%{x:.2f}<br>RV=%{y:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=cand["expansion_ratio"], y=cand["rv_current"], mode="markers+text",
        name="CANDIDATI", text=cand["ticker"], textposition="top center",
        textfont=dict(color=COLORS["text"], size=11),
        marker=dict(size=14, color=COLORS["positive"], line=dict(width=1.5, color="#ffffff")),
        hovertemplate="%{text}<br>exp=%{x:.2f}<br>RV=%{y:.1f}%<extra></extra>",
    ))
    # confine HIGH escluso (riferimento)
    fig.add_vline(x=3.0, line_color=COLORS["negative"], line_dash="dash",
                  annotation_text="HIGH escluso (≥3)", annotation_font_color=COLORS["negative"])
    fig.update_layout(**_layout(
        "Selezione Calendar — Expansion Ratio vs RV corrente",
        x="Expansion Ratio (rv_52w_max / rv_current) — più basso = meglio",
        y="RV corrente (%)"))
    return fig


def bar_candidates_score(df: pd.DataFrame) -> go.Figure:
    """Bar dei candidati per Borda rank (1 = migliore)."""
    cand = df[df["is_candidate"]].sort_values("borda_rank")
    fig = go.Figure(go.Bar(
        x=cand["ticker"], y=cand["expansion_ratio"],
        marker_color=COLORS["primary"],
        text=cand["tier"], textposition="outside",
        hovertemplate="%{x}<br>exp=%{y:.2f}<br>%{text}<extra></extra>",
    ))
    fig.update_layout(**_layout("Candidati per Expansion Ratio (più basso = priorità)",
                                x="Ticker (ordinati per Borda rank)", y="Expansion Ratio"))
    return fig


def history_line(hist: pd.DataFrame) -> go.Figure:
    """Numero di candidati e qualificati nel tempo."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist["run_utc"], y=hist["n_candidates"], mode="lines+markers",
                             name="candidati", line=dict(color=COLORS["positive"])))
    fig.add_trace(go.Scatter(x=hist["run_utc"], y=hist["qualified"], mode="lines",
                             name="qualificati", line=dict(color=COLORS["neutral"], dash="dot")))
    fig.update_layout(**_layout("Storico run", x="Run", y="N. ticker"))
    return fig
