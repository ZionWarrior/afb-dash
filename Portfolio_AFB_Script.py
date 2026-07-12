# -*- coding: utf-8 -*-
"""
Portfolio-Dashboard
Holt aktuelle Kurse via yfinance und erzeugt dashboard.html im selben Ordner.

Aufruf:  python Portfolio_AFB_Script.py
Danach:  dashboard.html im Browser oeffnen (macht die Start-Verknuepfung automatisch).

Neue Position hinzufuegen: unten in POSITIONS einen der freien Slots ausfuellen.
"""

import json
import sys
from datetime import date, datetime
from pathlib import Path

# ============================================================================
# KONFIGURATION - hier Positionen pflegen
# ============================================================================
# Jede Position:
#   name      Anzeigename
#   ticker    Yahoo-Finance-Ticker (z.B. "AAPL", "WLD.PA", "BTC-USD", "3SIL.L")
#   currency  Handelswaehrung der Position ("EUR", "USD", "GBP", "GBp")
#   trades    Liste von Kaeufen: (Datum "JJJJ-MM-TT", Stueckzahl, Kurs, Gebuehr)
#             Mehrere Kaeufe werden automatisch zu EINER Position zusammengefasst
#             (Durchschnittskurs), der Chartverlauf beruecksichtigt die Tranchen exakt.

POSITIONS = [
    {
        "name": "Bitcoin",
        "ticker": "BTC-USD",
        "currency": "USD",
        "trades": [("2025-06-23", 0.02098877, 104000.00, 0.00)],
    },
    {
        "name": "Amundi MSCI World",
        "ticker": "WLD.PA",
        "currency": "EUR",
        "trades": [("2025-06-17", 6, 338.68, 3.00)],
    },
    {
        "name": "Vanguard S&P 500",
        "ticker": "VUSA.AS",
        "currency": "EUR",
        "trades": [("2025-07-08", 20, 100.61, 3.00)],
    },
    {
        "name": "Gold Royalty",
        "ticker": "GROY",
        "currency": "USD",
        "trades": [
            ("2025-06-23", 500, 2.38, 2.17),
            ("2026-07-07", 17, 2.76, 0.48),
        ],
    },
    # ------- freie Slots fuer kommende Investments -------
    # {
    #     "name": "",
    #     "ticker": "",
    #     "currency": "USD",
    #     "trades": [("JJJJ-MM-TT", 0, 0.00, 0.00)],
    # },
    # {
    #     "name": "",
    #     "ticker": "",
    #     "currency": "EUR",
    #     "trades": [("JJJJ-MM-TT", 0, 0.00, 0.00)],
    # },
    # {
    #     "name": "",
    #     "ticker": "",
    #     "currency": "USD",
    #     "trades": [("JJJJ-MM-TT", 0, 0.00, 0.00)],
    # },
]

BENCHMARKS = [
    {"name": "S&P 500", "ticker": "^GSPC", "unit": "Pkt."},
    {"name": "Nasdaq Composite", "ticker": "^IXIC", "unit": "Pkt."},
    {"name": "DAX", "ticker": "^GDAXI", "unit": "Pkt."},
    {"name": "Bitcoin", "ticker": "BTC-USD", "unit": "$"},
]

# Markante wirtschaftliche/geopolitische Ereignisse, optional als vertikale
# Linien im Chart einblendbar. Datum muss innerhalb des Chartzeitraums liegen.
EVENTS = [
    {"date": "2025-06-22", "label": "US-Angriff auf iran. Atomanlagen"},
    {"date": "2025-09-17", "label": "Fed-Zinssenkung"},
    {"date": "2025-11-01", "label": "Bitcoin-Korrektur"},
    {"date": "2026-02-28", "label": "Iran-Krieg beginnt"},
    {"date": "2026-04-24", "label": "Iran: Öl-Eskalation"},
    {"date": "2026-06-01", "label": "KI-Bewertungsdebatte"},
    {"date": "2026-07-01", "label": "Iran: Waffenruhe bricht"},
]

FREE_SLOTS = 3          # Ghost-Zeilen in der Tabelle fuer kuenftige Positionen
OUTPUT = "Portfolio_AFB.html"

# ============================================================================
# Datenbeschaffung
# ============================================================================

def fetch_history(tickers, start):
    """Holt Tagesschlusskurse fuer alle Ticker ab 'start'. -> DataFrame (Datum x Ticker)."""
    import time

    import pandas as pd
    import yfinance as yf

    last_err = None
    for attempt in range(3):
        try:
            data = yf.download(
                tickers=" ".join(tickers),
                start=start,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            close = data["Close"]
            if not hasattr(close, "columns"):  # nur ein Ticker
                close = close.to_frame(name=tickers[0])
            # Pruefen, ob alle Ticker tatsaechlich Daten geliefert haben
            missing = [t for t in tickers if t not in close.columns or close[t].dropna().empty]
            if missing and attempt < 2:
                print(f"  Erneuter Versuch fuer: {', '.join(missing)} ...")
                time.sleep(2)
                continue
            close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
            # Kalendertage vereinheitlichen (BTC handelt 24/7, Aktien nicht) und Luecken fuellen
            idx = pd.date_range(close.index.min(), close.index.max(), freq="D")
            close = close.reindex(idx).ffill()
            return close
        except Exception as e:
            last_err = e
            time.sleep(2)
    raise RuntimeError(f"Kursabruf fehlgeschlagen nach 3 Versuchen: {last_err}")


# ============================================================================
# Berechnung
# ============================================================================

def to_eur_factor(currency, eurusd, eurgbp):
    """Umrechnungsfaktor Serie: 1 Einheit Fremdwaehrung -> EUR."""
    if currency == "EUR":
        return 1.0
    if currency == "USD":
        return 1.0 / eurusd
    if currency == "GBP":
        return 1.0 / eurgbp
    if currency == "GBp":  # Pence
        return 1.0 / eurgbp / 100.0
    raise ValueError(f"Unbekannte Waehrung: {currency}")


def build_data():
    import pandas as pd

    first_trade = min(
        datetime.strptime(t[0], "%Y-%m-%d").date()
        for p in POSITIONS for t in p["trades"]
    )
    start = (first_trade - pd.Timedelta(days=7)).strftime("%Y-%m-%d")

    tickers = [p["ticker"] for p in POSITIONS]
    bench_tickers = [b["ticker"] for b in BENCHMARKS]
    fx_tickers = ["EURUSD=X", "EURGBP=X"]
    close = fetch_history(sorted(set(tickers + bench_tickers + fx_tickers)), start)

    eurusd = close["EURUSD=X"]
    eurgbp = close["EURGBP=X"]

    chart_start = pd.Timestamp(first_trade)
    dates = close.loc[chart_start:].index

    # --- Positionswerte je Tag (EUR, tatsaechliche gestaffelte Kaeufe) ---
    # und "Lump-Sum"-Werte (EUR, alle Positionen mit Endmenge ab Starttag) ---
    total_value_eur = pd.Series(0.0, index=dates)
    total_invested_eur = pd.Series(0.0, index=dates)
    lumpsum_eur = pd.Series(0.0, index=dates)
    position_series = {}  # Name -> Lump-Sum-Serie (EUR) je Einzelposition
    rows = []

    for p in POSITIONS:
        px = close[p["ticker"]]
        fx = to_eur_factor(p["currency"], eurusd, eurgbp)
        fx_ser = fx if hasattr(fx, "index") else pd.Series(fx, index=close.index)

        qty = pd.Series(0.0, index=dates)
        cost_nat = 0.0
        cost_eur_ser = pd.Series(0.0, index=dates)
        for d, q, price, fee in p["trades"]:
            td = pd.Timestamp(d)
            trade_cost_nat = q * price + fee
            cost_nat += trade_cost_nat
            fx_at = fx_ser.asof(td) if hasattr(fx, "index") else fx
            qty.loc[qty.index >= td] += q
            cost_eur_ser.loc[cost_eur_ser.index >= td] += trade_cost_nat * fx_at

        value_eur = qty * px.loc[dates] * fx_ser.loc[dates]
        total_value_eur += value_eur.fillna(0.0)
        total_invested_eur += cost_eur_ser

        # Lump-Sum: Endmenge ueber den GESAMTEN Chartzeitraum bewertet -
        # ergibt eine glatte Vergleichskurve ohne Spruenge durch spaetere Kaeufe.
        q_final_full = qty.iloc[-1]
        pos_lumpsum = (q_final_full * px.loc[dates] * fx_ser.loc[dates]).fillna(0.0)
        lumpsum_eur += pos_lumpsum
        position_series[p["name"]] = pos_lumpsum.round(2)

        # --- Kennzahlen (letzter Stand) ---
        q_now = qty.iloc[-1]
        last = float(px.dropna().iloc[-1])
        prev = float(px.dropna().iloc[-2])
        fx_now = float(fx_ser.dropna().iloc[-1])
        avg_entry = cost_nat / q_now
        val_nat = q_now * last
        val_eur = val_nat * fx_now
        cost_eur = float(cost_eur_ser.iloc[-1])
        rows.append({
            "name": p["name"],
            "ticker": p["ticker"].replace("-USD", ""),
            "currency": "EUR" if p["currency"] == "EUR" else p["currency"],
            "qty": q_now,
            "avg_entry": avg_entry,
            "invest_nat": cost_nat,
            "last": last,
            "day_pct": (last / prev - 1) * 100,
            "value_nat": val_nat,
            "value_eur": val_eur,
            "cost_nat": cost_nat,
            "cost_eur": cost_eur,
            "pnl_eur": val_eur - cost_eur,
            "pnl_pct": (val_nat / cost_nat - 1) * 100,
        })

    # --- Chart-Portfolio: Lump-Sum-Kurve (glatt, keine Kapitalzufluss-Spruenge) ---
    port_eur = lumpsum_eur.round(2)

    # --- Benchmarks: "was waere aus der investierten Summe geworden, haette man
    # sie am Starttag komplett in den Index gesteckt" - gleiche Logik wie oben,
    # damit Portfolio- und Benchmark-Kurven 1:1 vergleichbar sind. ---
    ti_final = float(total_invested_eur.iloc[-1])
    bench_series = {}
    bench_raw = {}
    bench_raw_eur = {}
    for b in BENCHMARKS:
        s = close[b["ticker"]].loc[dates]
        idx = s / s.dropna().iloc[0] * 100
        eur = (idx / 100 * ti_final).round(2)
        bench_series[b["name"]] = [None if pd.isna(v) else float(v) for v in eur]
        bench_raw[b["name"]] = [None if pd.isna(v) else round(float(v), 2) for v in s]
        if b["unit"] == "$":
            s_eur = (s / eurusd.loc[dates]).round(2)
            bench_raw_eur[b["name"]] = [None if pd.isna(v) else float(v) for v in s_eur]

    # --- Kopf-Kennzahlen (echte, gestaffelte Werte) ---
    tv = float(total_value_eur.iloc[-1])
    ti = ti_final
    tv_prev = float(total_value_eur.iloc[-2])
    summary = {
        "total_eur": tv,
        "invested_eur": ti,
        "pnl_eur": tv - ti,
        "pnl_pct": (tv / ti - 1) * 100,
        "day_eur": tv - tv_prev,
        "day_pct": (tv / tv_prev - 1) * 100,
        "eurusd": float(eurusd.dropna().iloc[-1]),
        "updated": datetime.now().strftime("%d.%m.%Y, %H:%M"),
    }

    chart = {
        "dates": [d.strftime("%Y-%m-%d") for d in dates],
        "portfolio": [None if pd.isna(v) else float(v) for v in port_eur],
        "positions": {
            name: [None if pd.isna(v) else float(v) for v in s]
            for name, s in position_series.items()
        },
        "benchmarks": bench_series,
        "benchmarks_raw": bench_raw,
        "benchmarks_raw_eur": bench_raw_eur,
        "benchmark_units": {b["name"]: b["unit"] for b in BENCHMARKS},
        "invested_eur": round(ti_final, 2),
        "events": EVENTS,
    }
    return summary, rows, chart


# ============================================================================
# HTML
# ============================================================================

def fmt(v, dec=2):
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def sign_cls(v):
    return "up" if v >= 0 else "down"


def sign_fmt(v, dec=2, suffix=""):
    minus = "\u2212"
    sign = "+" if v >= 0 else minus
    return f"{sign}{fmt(abs(v), dec)}{suffix}"


def cur_sym(c):
    return {"EUR": "\u20ac", "USD": "$", "GBP": "\u00a3", "GBp": "p"}.get(c, c)


def qty_fmt(q):
    if q == int(q):
        return fmt(q, 0)
    return f"{q:.8f}".rstrip("0").replace(".", ",")


MONTH_ABBR = ["Jan", "Feb", "M\u00e4r", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def build_static_svg(chart):
    """Reines SVG-Liniendiagramm ohne JavaScript - Fallback fuer Vorschauen
    (z.B. iOS Dateien-App), die kein Skript ausfuehren."""
    dates = chart["dates"]
    values = chart["portfolio"]
    pts = [(i, v) for i, v in enumerate(values) if v is not None]
    if not pts:
        return '<div class="chart-note">Keine Chartdaten verf&uuml;gbar.</div>'

    W, H = 1100, 720
    pad_l, pad_r, pad_t, pad_b = 64, 24, 24, 40
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    y_lo, y_hi = min(ys), max(ys)
    y_pad = (y_hi - y_lo) * 0.12 or 5
    y_min, y_max = y_lo - y_pad, y_hi + y_pad
    n = len(values)

    def xmap(i):
        return pad_l + (i / max(n - 1, 1)) * (W - pad_l - pad_r)

    def ymap(v):
        return H - pad_b - (v - y_min) / (y_max - y_min) * (H - pad_t - pad_b)

    poly = " ".join(f"{xmap(i):.1f},{ymap(v):.1f}" for i, v in pts)

    grid = ""
    for k in range(5):
        val = y_min + (y_max - y_min) * k / 4
        y = ymap(val)
        grid += (
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{W-pad_r}" y2="{y:.1f}" '
            f'stroke="#141518" stroke-width="1"/>'
            f'<text x="{pad_l-10}" y="{y+4:.1f}" text-anchor="end" '
            f'font-size="12" fill="#8b8d94" font-family="monospace">'
            f'{fmt(val, 0)}&#8201;&#8364;</text>'
        )

    xlabels = ""
    step = max(n // 6, 1)
    for i in range(0, n, step):
        d = datetime.strptime(dates[i], "%Y-%m-%d")
        label = f"{MONTH_ABBR[d.month-1]} {str(d.year)[2:]}"
        x = xmap(i)
        xlabels += (
            f'<text x="{x:.1f}" y="{H-14}" text-anchor="middle" '
            f'font-size="11" fill="#8b8d94" font-family="monospace">{label}</text>'
        )

    return f"""
    <svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet"
         style="width:100%; height:auto; display:block;">
      {grid}
      {xlabels}
      <polyline points="{poly}" fill="none" stroke="#f5e642"
                stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    <div class="chart-note" style="margin-top:4px;">Statische Vorschau (Portfolio-Verlauf). F&uuml;r Tooltips, Benchmarks und Positions-Auswahl die Datei in Safari/Chrome &ouml;ffnen statt in der Dateivorschau.</div>
    """


def build_html(summary, rows, chart):
    pos_rows = ""
    for r in rows:
        sym = cur_sym(r["currency"])
        entry_dec = 0 if r["avg_entry"] >= 1000 else 2
        is_eur = r["currency"] == "EUR"
        wert_eur_cell = (
            '<span class="muted-dash">&mdash;</span>'
            if is_eur else f"{fmt(r['value_eur'])}&thinsp;\u20ac"
        )
        pos_rows += f"""
        <tr>
          <td class="pos-name"><span class="tick">{r['ticker']}</span>{r['name']}</td>
          <td class="num">{qty_fmt(r['qty'])}</td>
          <td class="num">{fmt(r['avg_entry'], entry_dec)}&thinsp;{sym}</td>
          <td class="num">{fmt(r['invest_nat'], 2)}&thinsp;{sym}</td>
          <td class="num">{fmt(r['last'], entry_dec)}&thinsp;{sym}</td>
          <td class="num {sign_cls(r['day_pct'])}">{sign_fmt(r['day_pct'], 2, '&thinsp;%')}</td>
          <td class="num">{fmt(r['value_nat'])}&thinsp;{sym}</td>
          <td class="num">{wert_eur_cell}</td>
          <td class="num {sign_cls(r['pnl_pct'])}">{sign_fmt(r['pnl_pct'], 1, '&thinsp;%')}</td>
          <td class="num {sign_cls(r['pnl_eur'])}">{sign_fmt(r['pnl_eur'], 2, '&thinsp;€')}</td>
        </tr>"""

    for i in range(FREE_SLOTS):
        pos_rows += f"""
        <tr class="ghost">
          <td class="pos-name"><span class="tick">&mdash;</span>Freier Slot {i+1}</td>
          <td class="num">&middot;</td><td class="num">&middot;</td><td class="num">&middot;</td>
          <td class="num">&middot;</td><td class="num">&middot;</td><td class="num">&middot;</td>
          <td class="num">&middot;</td><td class="num">&middot;</td><td class="num">&middot;</td>
        </tr>"""

    s = summary
    chart_json = json.dumps(chart)

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Portfolio</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,340;0,9..144,560;1,9..144,340&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #000000;
    --panel: #0d0e10;
    --line: #1e2024;
    --text: #ece9e1;
    --muted: #8b8d94;
    --gold: #d3b16a;
    --up: #46c98c;
    --down: #e8604c;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: "IBM Plex Sans", system-ui, sans-serif;
    font-size: 15px;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 1760px; margin: 0 auto; padding: 10px 28px 64px; }}

  header {{ display: flex; align-items: baseline; justify-content: space-between;
            border-bottom: 1px solid var(--line); padding-bottom: 22px; flex-wrap: wrap; gap: 8px; }}
  h1 {{ font-family: "Fraunces", serif; font-weight: 340; font-size: 30px; letter-spacing: .01em; }}
  h1 em {{ font-style: italic; color: var(--gold); }}
  .updated {{ color: var(--muted); font-size: 13px; font-family: "IBM Plex Mono", monospace; }}

  .kpis {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px;
           background: var(--line); border: 1px solid var(--line); margin-top: 0; }}
  .kpi {{ background: var(--panel); padding: 10px 16px 9px; }}
  .kpi .label {{ color: var(--muted); font-size: 10px; text-transform: uppercase;
                 letter-spacing: .13em; margin-bottom: 4px; }}
  .kpi .value {{ font-family: "IBM Plex Mono", monospace; font-size: 19px; font-weight: 500;
                 font-variant-numeric: tabular-nums; }}
  .kpi .value.stand-value {{ font-size: 13px; line-height: 1.4; font-weight: 400; }}
  .kpi .sub {{ font-family: "IBM Plex Mono", monospace; font-size: 11px; color: var(--muted); margin-top: 2px; }}
  .kpi.hero .value {{ color: var(--gold); }}
  .up {{ color: var(--up); }}
  .down {{ color: var(--down); }}

  section {{ margin-top: 22px; }}
  .sec-head {{ display: flex; align-items: baseline; justify-content: space-between;
               margin-bottom: 16px; flex-wrap: wrap; gap: 10px; }}
  h2 {{ font-family: "Fraunces", serif; font-weight: 340; font-size: 20px; }}

  .chips {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .chip {{
    font-family: "IBM Plex Mono", monospace; font-size: 12px;
    padding: 6px 14px; border: 1px solid var(--line); border-radius: 999px;
    background: transparent; color: var(--muted); cursor: pointer;
    transition: color .15s, border-color .15s;
  }}
  .chip:hover {{ color: var(--text); }}
  .chip:focus-visible {{ outline: 2px solid var(--gold); outline-offset: 2px; }}
  .chip.on {{ color: var(--bg); background: var(--chipc, var(--gold)); border-color: var(--chipc, var(--gold)); }}
  .chip.fixed {{ cursor: default; }}
  .chips-merged {{ flex-wrap: wrap; }}
  .chips-right {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .chips-label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .1em; }}
  .chip.off {{ text-decoration: line-through; opacity: .45; }}

  .chart-panel {{ background: var(--panel); border: 1px solid var(--line); padding: 22px 18px 12px; }}
  .chart-box {{ position: relative; height: 608px; }}
  .chart-box canvas {{ position: absolute; inset: 0; }}
  #chartTooltip {{
    position: absolute; pointer-events: none; opacity: 0; z-index: 20;
    background: #16171a; border: 1px solid #2a2c31; border-radius: 6px;
    padding: 8px 12px; font-family: "IBM Plex Mono", monospace; font-size: 12.5px;
    color: var(--text); white-space: nowrap; transition: opacity .1s ease;
    transform: translate(-50%, -100%);
  }}
  #chartTooltip .tt-title {{ color: var(--muted); font-size: 11px; margin-bottom: 5px; }}
  #chartTooltip .tt-line {{ line-height: 1.6; }}
  #staticChart {{ padding-top: 4px; }}
  .chart-note {{ color: var(--muted); font-size: 12px; padding: 10px 6px 6px; }}

  .table-panel {{ border: 1px solid var(--line); overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; min-width: 900px; }}
  th {{ text-align: right; color: var(--muted); font-size: 11px; text-transform: uppercase;
        letter-spacing: .12em; font-weight: 500; padding: 14px 16px; background: var(--panel);
        border-bottom: 1px solid var(--line); white-space: nowrap; }}
  th:first-child {{ text-align: left; }}
  td {{ padding: 15px 16px; border-bottom: 1px solid var(--line); white-space: nowrap; }}
  tr:last-child td {{ border-bottom: none; }}
  td.num {{ text-align: right; font-family: "IBM Plex Mono", monospace;
            font-variant-numeric: tabular-nums; font-size: 14px; }}
  .pos-name {{ font-weight: 500; }}
  .tick {{ display: inline-block; font-family: "IBM Plex Mono", monospace; font-size: 11px;
           color: var(--gold); border: 1px solid var(--line); border-radius: 4px;
           padding: 2px 7px; margin-right: 12px; min-width: 44px; text-align: center; }}
  tr.ghost td {{ color: #3a3c42; }}
  tr.ghost .tick {{ color: #3a3c42; }}
  .muted-dash {{ color: #4a4c52; }}
  tr.ghost .pos-name {{ font-weight: 400; font-style: italic; }}

  footer {{ margin-top: 40px; color: var(--muted); font-size: 12px; line-height: 1.7; }}

  @media (max-width: 760px) {{
    .kpis {{ grid-template-columns: repeat(2, 1fr); }}
    .wrap {{ padding: 32px 16px 48px; }}
    .chart-box {{ height: 448px; }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ transition: none !important; }}
  }}
</style>
</head>
<body>
<div class="wrap">

  <div class="kpis">
    <div class="kpi hero">
      <div class="label">Gesamtwert</div>
      <div class="value">{fmt(s['total_eur'])}&thinsp;\u20ac</div>
      <div class="sub">investiert {fmt(s['invested_eur'])}&thinsp;\u20ac</div>
    </div>
    <div class="kpi">
      <div class="label">Gewinn / Verlust</div>
      <div class="value {sign_cls(s['pnl_eur'])}">{sign_fmt(s['pnl_eur'], 2, '&thinsp;€')}</div>
      <div class="sub {sign_cls(s['pnl_pct'])}">{sign_fmt(s['pnl_pct'], 1, '&thinsp;%')}</div>
    </div>
    <div class="kpi">
      <div class="label">Heute</div>
      <div class="value {sign_cls(s['day_eur'])}">{sign_fmt(s['day_eur'], 2, '&thinsp;€')}</div>
      <div class="sub {sign_cls(s['day_pct'])}">{sign_fmt(s['day_pct'], 2, '&thinsp;%')}</div>
    </div>
    <div class="kpi">
      <div class="label">Positionen</div>
      <div class="value">{len(rows)}</div>
      <div class="sub">{FREE_SLOTS} Slots frei</div>
    </div>
    <div class="kpi">
      <div class="label">Stand</div>
      <div class="value stand-value">{s['updated'].replace(', ', ' &middot; ')}</div>
      <div class="sub">EUR/USD {fmt(s['eurusd'], 4)}</div>
    </div>
  </div>

  <section>
    <div class="sec-head chips-merged">
      <div class="chips" id="chips">
        <button class="chip fixed on" style="--chipc: var(--gold)">Portfolio</button>
      </div>
      <div class="chips-right">
        <span class="chips-label">Im Portfolio ber&uuml;cksichtigt</span>
        <div class="chips" id="posChips"></div>
      </div>
    </div>
    <div class="chart-panel">
      <div class="chart-box" id="chartBox">
        <canvas id="chart" style="display:none;"></canvas>
        <div id="staticChart">{build_static_svg(chart)}</div>
        <div id="chartTooltip"></div>
      </div>
      <div class="chart-note">Portfolio &amp; Benchmarks: alle aktuellen Positionen bzw. die investierte Summe ({fmt(chart['invested_eur'], 0)}&thinsp;&euro;) so bewertet, als w&auml;ren sie komplett am Starttag gekauft worden &ndash; glatte Vergleichskurve ohne Spr&uuml;nge durch sp&auml;tere Kapitalzufl&uuml;sse. Echte Kaufzeitpunkte, -betr&auml;ge und G&amp;V siehe Tabelle. Tooltip zeigt die echten Indexst&auml;nde/Kurse zum jeweiligen Zeitpunkt. Einzelne Positionen lassen sich unten aus der Portfolio-Linie herausnehmen.</div>
    </div>
  </section>

  <section>
    <div class="sec-head"><h2>Positionen</h2></div>
    <div class="table-panel">
      <table>
        <thead>
          <tr>
            <th>Position</th><th>Menge</th><th>Einstieg &Oslash;</th><th>Einstiegsinvest</th><th>Kurs</th>
            <th>Tag</th><th>Wert</th><th>Wert &euro;</th><th>G&amp;V %</th><th>G&amp;V &euro;</th>
          </tr>
        </thead>
        <tbody>{pos_rows}
        </tbody>
      </table>
    </div>
  </section>

  <footer>
    Kursdaten: Yahoo Finance (verz&ouml;gert). Einstiege und G&amp;V inklusive Ordergeb&uuml;hren.
    USD-Positionen zum jeweiligen Tageskurs in EUR umgerechnet.
    Aktualisierung: Doppelklick auf die Start-Verkn&uuml;pfung.
  </footer>

</div>

<script>
const DATA = {chart_json};
const COLORS = {{
  "Portfolio": "#f5e642",
  "S&P 500": "#39ff8f",
  "Nasdaq Composite": "#1e5fd9",
  "DAX": "#ff2ec4",
  "Bitcoin": "#ff8a00"
}};

const datasets = [{{
  label: "Portfolio",
  data: DATA.portfolio,
  raw: DATA.portfolio,
  unit: "\u20ac",
  borderColor: COLORS["Portfolio"],
  borderWidth: 2.4,
  borderCapStyle: "round",
  borderJoinStyle: "round",
  pointRadius: 0,
  pointHoverRadius: 5,
  pointHoverBackgroundColor: "#000",
  pointHoverBorderWidth: 2,
  tension: 0.25,
  hidden: false
}}];

for (const [name, series] of Object.entries(DATA.benchmarks)) {{
  datasets.push({{
    label: name, data: series,
    raw: DATA.benchmarks_raw[name],
    rawEur: DATA.benchmarks_raw_eur[name] || null,
    unit: DATA.benchmark_units[name],
    borderColor: COLORS[name] || "#888",
    borderWidth: 1.8, borderCapStyle: "round", borderJoinStyle: "round",
    pointRadius: 0, pointHoverRadius: 4, pointHoverBackgroundColor: "#000",
    pointHoverBorderWidth: 2, tension: 0.25,
    hidden: true
  }});
}}

// Welche Einzelpositionen aktuell in der Portfolio-Linie mitgerechnet werden
const activePositions = new Set(Object.keys(DATA.positions));

function recomputePortfolioLine() {{
  const n = DATA.dates.length;
  const sum = new Array(n).fill(0);
  activePositions.forEach(name => {{
    const s = DATA.positions[name];
    for (let i = 0; i < n; i++) sum[i] += (s[i] ?? 0);
  }});
  const portfolioDs = chart.data.datasets[0];
  portfolioDs.data = sum;
  portfolioDs.raw = sum;
}}

const tooltipEl = document.getElementById("chartTooltip");
const chartBoxEl = document.getElementById("chartBox");

function externalTooltip(context) {{
  const tt = context.tooltip;
  if (tt.opacity === 0) {{
    tooltipEl.style.opacity = 0;
    return;
  }}

  const dateStr = tt.dataPoints && tt.dataPoints[0] ? tt.dataPoints[0].label : "";
  let html = `<div class="tt-title">${{dateStr}}</div>`;

  tt.dataPoints.forEach(dp => {{
    const ds = dp.dataset;
    const rv = ds.raw ? ds.raw[dp.dataIndex] : null;
    const dv = ds.data[dp.dataIndex];
    const base = ds.data.find(v => v !== null && v !== undefined);
    let pctHtml = "";
    if (base && dv !== null && dv !== undefined) {{
      const pct = (dv / base - 1) * 100;
      const color = pct >= 0 ? "#46c98c" : "#e8604c";
      const sign = pct >= 0 ? "+" : "\u2212";
      pctHtml = ` <span style="color:${{color}}">(${{sign}}${{Math.abs(pct).toFixed(1)}}\u2009%)</span>`;
    }}
    if (rv === null || rv === undefined) {{
      html += `<div class="tt-line">${{ds.label}}: \u2013</div>`;
    }} else {{
      const val = rv.toLocaleString("de-DE", {{ maximumFractionDigits: rv < 10 ? 4 : 2 }});
      let eurHtml = "";
      const rve = ds.rawEur ? ds.rawEur[dp.dataIndex] : null;
      if (rve !== null && rve !== undefined) {{
        const valEur = rve.toLocaleString("de-DE", {{ maximumFractionDigits: 2 }});
        eurHtml = ` <span style="color:#8b8d94">/ ${{valEur}} \u20ac</span>`;
      }}
      html += `<div class="tt-line">${{ds.label}}: ${{val}} ${{ds.unit}}${{eurHtml}}${{pctHtml}}</div>`;
    }}
  }});

  tooltipEl.innerHTML = html;
  const boxRect = chartBoxEl.getBoundingClientRect();
  tooltipEl.style.opacity = 1;
  tooltipEl.style.left = tt.caretX + "px";
  tooltipEl.style.top = (tt.caretY - 10) + "px";
}}

const ctx = document.getElementById("chart");

function yRange() {{
  const vals = [];
  chart.data.datasets.forEach(ds => {{
    if (ds.hidden) return;
    ds.data.forEach(v => {{ if (v !== null && v !== undefined) vals.push(v); }});
  }});
  if (!vals.length) return {{ min: 0, max: 100 }};
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.12 || 5;
  return {{ min: Math.floor(lo - pad), max: Math.ceil(hi + pad) }};
}}

let eventsVisible = false;

function athIndices(arr) {{
  let max = -Infinity, maxIdx = -1;
  arr.forEach((v, i) => {{
    if (v === null || v === undefined) return;
    if (v > max) {{ max = v; maxIdx = i; }}
  }});
  return maxIdx === -1 ? [] : [maxIdx];
}}

const athPlugin = {{
  id: "athMarkers",
  afterDatasetsDraw(chart) {{
    const {{ ctx, scales, chartArea }} = chart;
    if (!chartArea) return;
    chart.data.datasets.forEach(ds => {{
      if (ds.hidden) return;
      athIndices(ds.data).forEach(idx => {{
        const x = scales.x.getPixelForValue(idx);
        const y = scales.y.getPixelForValue(ds.data[idx]);
        if (x < chartArea.left || x > chartArea.right) return;
        ctx.save();
        ctx.fillStyle = ds.borderColor;
        ctx.beginPath();
        ctx.arc(x, y, 4.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = "#000";
        ctx.stroke();
        ctx.font = "bold 11px 'IBM Plex Mono', monospace";
        ctx.textAlign = "center";
        ctx.lineWidth = 3;
        ctx.strokeStyle = "#000";
        ctx.strokeText("ATH", x, y - 10);
        ctx.fillText("ATH", x, y - 10);
        ctx.restore();
      }});
    }});
  }}
}};

const eventMarkerPlugin = {{
  id: "eventMarkers",
  afterDraw(chart) {{
    if (!eventsVisible) return;
    const {{ ctx, chartArea, scales }} = chart;
    if (!chartArea) return;
    ctx.save();
    (DATA.events || []).forEach(ev => {{
      const idx = DATA.dates.indexOf(ev.date);
      if (idx === -1) return;
      const x = scales.x.getPixelForValue(idx);
      if (x < chartArea.left || x > chartArea.right) return;
      ctx.strokeStyle = "rgba(255,255,255,0.18)";
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x, chartArea.top);
      ctx.lineTo(x, chartArea.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.save();
      ctx.translate(x + 4, chartArea.bottom - 6);
      ctx.rotate(-Math.PI / 2);
      ctx.font = "11px 'IBM Plex Mono', monospace";
      ctx.fillStyle = "#b97b73";
      ctx.textBaseline = "middle";
      ctx.fillText(ev.label, 0, 0);
      ctx.restore();
    }});
    ctx.restore();
  }}
}};

const chart = new Chart(ctx, {{
  type: "line",
  data: {{ labels: DATA.dates, datasets }},
  plugins: [eventMarkerPlugin, athPlugin],
  options: {{
    responsive: true, maintainAspectRatio: false,
    animation: {{ duration: 500, easing: "easeOutCubic" }},
    interaction: {{ mode: "index", intersect: false }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        enabled: false,
        external: externalTooltip
      }}
    }},
    scales: {{
      x: {{
        grid: {{ color: "#141518" }},
        ticks: {{
          color: "#8b8d94", maxTicksLimit: 9,
          font: {{ family: "IBM Plex Mono", size: 11 }},
          callback: function(v) {{
            const d = this.getLabelForValue(v);
            const [y, m] = d.split("-");
            return ["Jan","Feb","M\u00e4r","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"][+m-1] + " " + y.slice(2);
          }}
        }}
      }},
      y: {{
        grid: {{ color: "#141518" }},
        ticks: {{
          color: "#8b8d94", font: {{ family: "IBM Plex Mono", size: 11 }},
          callback: v => v.toLocaleString("de-DE", {{ maximumFractionDigits: 0 }}) + " \u20ac"
        }}
      }}
    }}
  }}
}});

const r0 = yRange();
chart.options.scales.y.min = r0.min;
chart.options.scales.y.max = r0.max;
chart.update();

// Benchmark-Chips
const chipBox = document.getElementById("chips");
Object.keys(DATA.benchmarks).forEach(name => {{
  const b = document.createElement("button");
  b.className = "chip";
  b.textContent = name;
  b.style.setProperty("--chipc", COLORS[name]);
  b.addEventListener("click", () => {{
    const ds = chart.data.datasets.find(d => d.label === name);
    ds.hidden = !ds.hidden;
    b.classList.toggle("on", !ds.hidden);
    const r = yRange();
    chart.options.scales.y.min = r.min;
    chart.options.scales.y.max = r.max;
    chart.update();
  }});
  chipBox.appendChild(b);
}});

// Ereignisse-Chip: direkt hinter den Benchmarks in derselben Zeile
const eventsChip = document.createElement("button");
eventsChip.className = "chip";
eventsChip.id = "eventsChip";
eventsChip.textContent = "Ereignisse";
eventsChip.style.borderColor = "#e8604c";
eventsChip.addEventListener("click", () => {{
  eventsVisible = !eventsVisible;
  eventsChip.classList.toggle("on", eventsVisible);
  eventsChip.style.setProperty("--chipc", "#e8604c");
  chart.update();
}});
chipBox.appendChild(eventsChip);
// Positions-Chips: Einzelpositionen aus der Portfolio-Linie heraus-/hineinnehmen
const posChipBox = document.getElementById("posChips");
Object.keys(DATA.positions).forEach(name => {{
  const b = document.createElement("button");
  b.className = "chip on";
  b.textContent = name;
  b.addEventListener("click", () => {{
    if (activePositions.has(name)) {{
      if (activePositions.size === 1) return; // mindestens eine Position aktiv lassen
      activePositions.delete(name);
      b.classList.remove("on"); b.classList.add("off");
    }} else {{
      activePositions.add(name);
      b.classList.add("on"); b.classList.remove("off");
    }}
    recomputePortfolioLine();
    const r = yRange();
    chart.options.scales.y.min = r.min;
    chart.options.scales.y.max = r.max;
    chart.update();
  }});
  posChipBox.appendChild(b);
}});

// JS lief erfolgreich durch -> interaktiven Chart zeigen, statisches SVG ausblenden
document.getElementById("chart").style.display = "block";
document.getElementById("staticChart").style.display = "none";
</script>
</body>
</html>
"""


def ensure_dependencies():
    """Installiert fehlende Pakete automatisch, damit eine einzelne .py-Datei genuegt."""
    import importlib.util
    import subprocess

    required = {"yfinance": "yfinance", "pandas": "pandas"}
    missing = [pkg for mod, pkg in required.items() if importlib.util.find_spec(mod) is None]
    if not missing:
        return
    print(f"Installiere fehlende Pakete: {', '.join(missing)} ...")
    for pkg in missing:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--break-system-packages", "-q", pkg]
            )
        except subprocess.CalledProcessError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])
    print("Pakete installiert.")


def main():
    ensure_dependencies()

    try:
        summary, rows, chart = build_data()
    except Exception as e:
        print(f"\nFEHLER beim Kursabruf: {e}")
        print("Internetverbindung pruefen bzw. spaeter erneut versuchen.")
        input("Enter zum Schliessen...")
        sys.exit(1)

    out = Path(__file__).resolve().parent / OUTPUT
    out.write_text(build_html(summary, rows, chart), encoding="utf-8")
    print(f"OK - {out} aktualisiert ({summary['updated']})")

    import webbrowser
    webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
