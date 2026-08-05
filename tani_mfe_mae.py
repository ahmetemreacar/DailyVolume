from __future__ import annotations
import argparse
import sys
import numpy as np
import pandas as pd

from veri import cek_saatlik
from sinyal import sinyal_uret
from evren import evren_yukle


def gun_excursion(df: pd.DataFrame) -> pd.DataFrame:
    g = df.copy()
    g["_t"] = g.index.date
    rows = []
    for t, gun in g.groupby("_t"):
        gun = gun.sort_index()
        if len(gun) < 1:
            continue
        acilis = float(gun.iloc[0]["Open"])
        if not np.isfinite(acilis) or acilis <= 0:
            continue
        rows.append({
            "tarih": t,
            "mfe": float(gun["High"].max()) / acilis - 1,   # acilis -> gun-ici EN YUKSEK
            "mae": float(gun["Low"].min()) / acilis - 1,    # acilis -> gun-ici EN DUSUK
        })
    return pd.DataFrame(rows).set_index("tarih") if rows else pd.DataFrame()


def hisse_tani(df, baseline_gun=10, kat=3.0, min_ciro_tl=200_000) -> pd.DataFrame:
    sig = sinyal_uret(df, baseline_gun, kat, min_ciro_tl)
    ex = gun_excursion(df)
    if len(sig) == 0 or len(ex) == 0:
        return pd.DataFrame()
    return ex.join(sig[["sinyal", "kat_gerceklesen"]], how="inner").dropna(subset=["sinyal"])


def ozet(g: pd.DataFrame) -> pd.Series:
    if len(g) == 0:
        return pd.Series({"n": 0})
    return pd.Series({
        "n": len(g),
        "mfe_ort_%": round(g["mfe"].mean() * 100, 2),
        "mae_ort_%": round(g["mae"].mean() * 100, 2),
        "mfe>=1%_%": round((g["mfe"] >= 0.01).mean() * 100, 1),
        "mfe>=3%_%": round((g["mfe"] >= 0.03).mean() * 100, 1),
        "mfe>=5%_%": round((g["mfe"] >= 0.05).mean() * 100, 1),
        "mae<=-2%_%": round((g["mae"] <= -0.02).mean() * 100, 1),
    })


def rapor(tum: pd.DataFrame):
    s = tum[tum["sinyal"]]
    d = tum[~tum["sinyal"]]
    print("=" * 66)
    print("MFE/MAE TANISI  (acilis fiyatina gore gun-ici en yuksek / en dusuk)")
    print("=" * 66)
    print(pd.DataFrame({"SINYAL": ozet(s), "DIGER": ozet(d)}).to_string())
    print("-" * 66)
    print("Sinyal gunleri KAT buyukluk kovalarina gore:")
    kovalar = [("3-5x", 3, 5), ("5-8x", 5, 8), ("8x+", 8, 1e9)]
    sat = {}
    for ad, lo, hi in kovalar:
        alt = s[(s["kat_gerceklesen"] >= lo) & (s["kat_gerceklesen"] < hi)]
        sat[ad] = ozet(alt)
    print(pd.DataFrame(sat).to_string())
    print("-" * 66)
    print("YORUM ANAHTARI:")
    print(" - Hedef ancak gun-ici EN YUKSEK ona deginca tutar (sira ayri konu).")
    print(" - Sinyal gununde 'mfe>=3%_%' diger gunlerden BELIRGIN yuksek + mae")
    print("   sinirli ise edge var demektir. Ozellikle 8x+ kovasina bak.")
    print(" - Bu MFE/MAE bir on-eleme; hedef/stop SIRASINI backtest.py cozer.")
    print("NOT: Analiz aracidir, yatirim tavsiyesi degildir.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="test_evren.csv")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    p.add_argument("--kat", type=float, default=3.0)
    p.add_argument("--baseline", type=int, default=10)
    p.add_argument("--min_ciro", type=float, default=200_000)
    a = p.parse_args()

    hisseler = evren_yukle(a.evren)
    tum = []
    for i, h in enumerate(hisseler, 1):
        try:
            df = cek_saatlik(h, tv_user=a.tv_user, tv_pass=a.tv_pass, sessiz=True)
            t = hisse_tani(df, a.baseline, a.kat, a.min_ciro)
            if len(t):
                tum.append(t.assign(hisse=h))
            print(f"  [{i}/{len(hisseler)}] {h}: {len(t)} gun", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)
    if not tum:
        print("Veri yok.")
        return
    birlesik = pd.concat(tum, ignore_index=True)
    rapor(birlesik)
    birlesik.to_csv("tani_mfe_mae.csv", index=False)
    print("\n-> tani_mfe_mae.csv kaydedildi.")


if __name__ == "__main__":
    main()
