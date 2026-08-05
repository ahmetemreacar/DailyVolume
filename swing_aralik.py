from __future__ import annotations
import argparse
import sys
import numpy as np
import pandas as pd

from veri import cek_saatlik
from sinyal import sinyal_uret
from evren import evren_yukle

KOVALAR = [("dip 0-20", 0.0, 0.2), ("alt 20-40", 0.2, 0.4), ("orta 40-60", 0.4, 0.6),
           ("ust 60-80", 0.6, 0.8), ("tepe 80-100", 0.8, 1.0001)]


def gunluk(df):
    g = df.copy()
    g["_t"] = g.index.date
    d = g.groupby("_t").agg(Open=("Open", "first"), High=("High", "max"),
                            Low=("Low", "min"), Close=("Close", "last"))
    d.index = pd.to_datetime(d.index)
    return d.sort_index()


def tut(daily, basla, entry, hedef, stop, max_gun, maliyet):
    ust, alt = entry * (1 + hedef), entry * (1 - stop)
    son = min(len(daily), basla + max_gun)
    for j in range(basla, son):
        o, h, l = (float(daily.iloc[j]["Open"]), float(daily.iloc[j]["High"]),
                   float(daily.iloc[j]["Low"]))
        if j > basla:
            if o <= alt:
                return "stop", o / entry - 1 - maliyet, j - basla
            if o >= ust:
                return "hedef", o / entry - 1 - maliyet, j - basla
        if l <= alt:
            return "stop", -stop - maliyet, j - basla
        if h >= ust:
            return "hedef", hedef - maliyet, j - basla
    return "acik", np.nan, son - basla


def hisse_isle(df, baseline_gun, min_kat, min_ciro_tl, hedef, stop, max_gun,
               komisyon, slippage):
    sig = sinyal_uret(df, baseline_gun, 3.0, min_ciro_tl)
    if len(sig) == 0:
        return []
    d = gunluk(df)
    d["tmax"] = d["High"].cummax().shift(1)
    d["tmin"] = d["Low"].cummin().shift(1)
    maliyet = (komisyon + slippage) * 2
    sec = sig[sig["sinyal"] & (sig["kat_gerceklesen"] >= min_kat)]
    out = []
    idx_map = {ts.date(): i for i, ts in enumerate(d.index)}
    for tarih, satir in sec.iterrows():
        i = idx_map.get(tarih)
        if i is None or i + 1 >= len(d):
            continue
        row = d.iloc[i]
        entry = float(row["Open"])
        tmax, tmin = row["tmax"], row["tmin"]
        if entry <= 0 or pd.isna(tmax) or pd.isna(tmin) or tmax <= tmin:
            continue
        pos = (entry - tmin) / (tmax - tmin)
        sonuc, net, gun = tut(d, i, entry, hedef, stop, max_gun, maliyet)
        out.append({"tarih": tarih, "kat": satir["kat_gerceklesen"], "aralik_pos": round(pos, 3),
                    "sonuc": sonuc, "getiri_net": net, "gun": gun})
    return out


def metrik(df):
    r = df["getiri_net"].dropna()
    if len(r) == 0:
        return {"n": len(df), "cozulen": 0}
    kaz, kay = r[r > 0], r[r < 0]
    pf = kaz.sum() / abs(kay.sum()) if len(kay) and kay.sum() != 0 else np.inf
    return {"n": len(df), "cozulen": len(r), "win_%": round((r > 0).mean() * 100, 1),
            "EV_%": round(r.mean() * 100, 3), "PF": round(pf, 2) if np.isfinite(pf) else 99.0,
            "ort_gun": round(df["gun"].mean(), 1)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    p.add_argument("--min_kat", type=float, default=8.0)
    p.add_argument("--baseline", type=int, default=10)
    p.add_argument("--min_ciro", type=float, default=200_000)
    p.add_argument("--hedef", type=float, default=0.05)
    p.add_argument("--stop", type=float, default=0.03)
    p.add_argument("--max_gun", type=int, default=30)
    p.add_argument("--komisyon", type=float, default=0.0005)
    p.add_argument("--slippage", type=float, default=0.003)
    p.add_argument("--csv", default="swing_aralik.csv")
    a = p.parse_args()

    hisseler = evren_yukle(a.evren)
    hepsi = []
    for i, h in enumerate(hisseler, 1):
        try:
            df = cek_saatlik(h, tv_user=a.tv_user, tv_pass=a.tv_pass, sessiz=True)
            for k in hisse_isle(df, a.baseline, a.min_kat, a.min_ciro, a.hedef, a.stop,
                                a.max_gun, a.komisyon, a.slippage):
                k["hisse"] = h
                hepsi.append(k)
            print(f"  [{i}/{len(hisseler)}] {h}: ok", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)

    if not hepsi:
        print("Sinyal yok.")
        return
    res = pd.DataFrame(hepsi)
    res.to_csv(a.csv, index=False)
    print("=" * 70)
    print(f"SWING + ARALIK | giris=eslesme | hedef=%{a.hedef*100:.0f} stop=%{a.stop*100:.0f} "
          f"| max_tut={a.max_gun}g | min_kat>={a.min_kat}")
    print("=" * 70)
    print("TUM:", metrik(res))
    print("-" * 70)
    print("503-gun ARALIGINDAKI KONUMA gore (0=dip, 1=tepe):")
    sat = {ad: metrik(res[(res["aralik_pos"] >= lo) & (res["aralik_pos"] < hi)]) for ad, lo, hi in KOVALAR}
    print(pd.DataFrame(sat).T.to_string())
    print("-" * 70)
    print(f"'acik' kalan (sure doldu): {(res['sonuc']=='acik').sum()}/{len(res)}")
    print(f"-> {a.csv} kaydedildi.")
    print("NOT: cok gunlu tutus = overnight gap riski + sermaye kilitleme. Yatirim tavsiyesi degildir.")


if __name__ == "__main__":
    main()
