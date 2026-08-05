from __future__ import annotations
import argparse, sys, datetime as dt
import numpy as np
import pandas as pd

from veri import cek_saatlik
from evren import evren_yukle


def gunluk(df):
    g = df.sort_index().copy()
    g["_t"] = g.index.date
    return g.groupby("_t").agg(Open=("Open", "first"), High=("High", "max"),
                               Low=("Low", "min"), Close=("Close", "last"),
                               ovol=("Volume", "first"))


def tara(hourly, baseline_gun, hafta52, dip_esik):
    d = gunluk(hourly)
    if len(d) < baseline_gun + 2:
        return None
    baseline = d["ovol"].rolling(baseline_gun, min_periods=baseline_gun).mean().shift(1)
    hi52 = d["High"].rolling(hafta52, min_periods=hafta52 // 2).max().shift(1)
    lo52 = d["Low"].rolling(hafta52, min_periods=hafta52 // 2).min().shift(1)
    dun_kapanis = d["Close"].shift(1)
    t = d.index[-1]                      # son (bugun) gun
    bl = baseline.iloc[-1]
    if pd.isna(bl) or bl <= 0:
        return None
    ov = float(d["ovol"].iloc[-1]); op = float(d["Open"].iloc[-1])
    kat = ov / bl
    H, L = float(hi52.iloc[-1]) if not pd.isna(hi52.iloc[-1]) else np.nan, \
           float(lo52.iloc[-1]) if not pd.isna(lo52.iloc[-1]) else np.nan
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
    return {"tarih": str(t), "kat": round(kat, 1), "grup": grup,
            "pos52": round(pos52, 2) if not np.isnan(pos52) else None,
            "acilis": round(op, 3), "acilis_ciro_TL": int(op * ov),
            "secili": (kat >= 8 and (dip or taze_kirilim))}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    p.add_argument("--min_kat", type=float, default=5.0, help="listeye girmek icin asgari kat")
    p.add_argument("--baseline", type=int, default=20)
    p.add_argument("--hafta52", type=int, default=252)
    p.add_argument("--dip_esik", type=float, default=0.20)
    p.add_argument("--min_ciro", type=float, default=200_000)
    a = p.parse_args()

    hisseler = evren_yukle(a.evren)
    sonuc = []
    for i, h in enumerate(hisseler, 1):
        try:
            hourly = cek_saatlik(h, tv_user=a.tv_user, tv_pass=a.tv_pass, sessiz=True)
            r = tara(hourly, a.baseline, a.hafta52, a.dip_esik)
            if r and r["kat"] >= a.min_kat and r["acilis_ciro_TL"] >= a.min_ciro:
                r["hisse"] = h
                sonuc.append(r)
            print(f"  [{i}/{len(hisseler)}] {h}", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)

    if not sonuc:
        print("Bugun esige ulasan hisse yok."); return
    df = pd.DataFrame(sonuc).sort_values("kat", ascending=False)
    bugun = df["tarih"].mode()[0]
    df.to_csv(f"tarama_{bugun}.csv", index=False)
    kol = ["hisse", "kat", "grup", "pos52", "acilis", "acilis_ciro_TL", "secili"]
    print("=" * 64)
    print(f"ACILIS HACMI TARAMASI | tarih {bugun} | kat>={a.min_kat}")
    print("=" * 64)
    print("--- SENIN KRITERIN: 8x+ VE (dip veya taze kirilim) ---")
    sec = df[df["secili"]]
    print(sec[kol].to_string(index=False) if len(sec) else "  (bugun yok)")
    print("\n--- DIGER YUKSEK HACIMLILER (bilgi icin) ---")
    print(df[~df["secili"]][kol].head(20).to_string(index=False))
    print(f"\n-> tarama_{bugun}.csv kaydedildi. Brut takas/VBTS durumunu KAP'tan/aracindan manuel teyit et.")


if __name__ == "__main__":
    main()
