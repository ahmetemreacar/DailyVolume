"""Saatlik acilis hacmi: ilk N bar kumulatif."""
from __future__ import annotations

import numpy as np
import pandas as pd


def gunluk_kum(df: pd.DataFrame, n_bar: int = 2) -> pd.DataFrame:
    """Ilk n_bar saatlik bar hacmini topla (varsayilan 09+10)."""
    g = df.sort_index().copy()
    g["_t"] = g.index.date
    rows = []
    for t, gun in g.groupby("_t"):
        gun = gun.sort_index()
        if len(gun) < n_bar:
            continue
        w = gun.iloc[:n_bar]
        rows.append({
            "_t": t,
            "Open": float(w.iloc[0]["Open"]),
            "High": float(gun["High"].max()),
            "Low": float(gun["Low"].min()),
            "Close": float(gun.iloc[-1]["Close"]),
            "ovol": float(w["Volume"].sum()),
            "ciro": float((w["Volume"] * w["Close"]).sum()),
        })
    out = pd.DataFrame(rows).set_index("_t")
    out.index.name = None
    return out


def tara_kum(hourly, baseline_gun=20, hafta52=252, dip_esik=0.20, n_bar=2):
    d = gunluk_kum(hourly, n_bar)
    if len(d) < baseline_gun + 2:
        return None
    baseline = d["ovol"].rolling(baseline_gun, min_periods=baseline_gun).mean().shift(1)
    hi52 = d["High"].rolling(hafta52, min_periods=hafta52 // 2).max().shift(1)
    lo52 = d["Low"].rolling(hafta52, min_periods=hafta52 // 2).min().shift(1)
    dun_kapanis = d["Close"].shift(1)
    t = d.index[-1]
    bl = baseline.iloc[-1]
    if pd.isna(bl) or bl <= 0:
        return None
    ov = float(d["ovol"].iloc[-1])
    op = float(d["Open"].iloc[-1])
    kat = ov / bl
    H = float(hi52.iloc[-1]) if not pd.isna(hi52.iloc[-1]) else np.nan
    L = float(lo52.iloc[-1]) if not pd.isna(lo52.iloc[-1]) else np.nan
    pos52 = (op - L) / (H - L) if (not np.isnan(H) and H > L) else np.nan
    dk = float(dun_kapanis.iloc[-1]) if not pd.isna(dun_kapanis.iloc[-1]) else np.nan
    bugun_yuksek = float(d["High"].iloc[-1])
    taze_kirilim = (not np.isnan(H)) and (dk < H) and (bugun_yuksek >= H)
    dip = (not np.isnan(pos52)) and pos52 <= dip_esik
    if np.isnan(pos52):
        grup = "?"
    elif dip:
        grup = "DIP"
    elif taze_kirilim:
        grup = "KIRILIM"
    elif pos52 >= 0.8:
        grup = "tepe(eski)"
    else:
        grup = "orta"
    return {
        "tarih": str(t), "kat": round(kat, 1), "grup": grup,
        "pos52": round(pos52, 2) if not np.isnan(pos52) else None,
        "acilis": round(op, 3),
        "acilis_ciro_TL": int(op * ov),
        "kum_bar": n_bar,
        "ovol_kum": int(ov),
    }
