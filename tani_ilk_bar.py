from __future__ import annotations
import argparse
import sys
import numpy as np
import pandas as pd

from veri import cek_saatlik
from sinyal import sinyal_uret
from evren import evren_yukle


def ilk_bar_ozellik(df: pd.DataFrame) -> pd.DataFrame:
    g = df.copy()
    g["_t"] = g.index.date
    rows = []
    for t, gun in g.groupby("_t"):
        gun = gun.sort_index()
        if len(gun) < 2:
            continue
        b1, b2, kap = gun.iloc[0], gun.iloc[1], gun.iloc[-1]
        o = float(b1["Open"])
        if not np.isfinite(o) or o <= 0:
            continue
        rows.append({
            "tarih": t,
            "ilk_bar_tepe": float(b1["High"]) / o - 1,
            "ilk_bar_dip": float(b1["Low"]) / o - 1,
            "ilk_bar_kapanis": float(b1["Close"]) / o - 1,
            "ilk_saat_hareket": float(b2["Open"]) / o - 1,
            "gun_sonu": float(kap["Close"]) / o - 1,
        })
    return pd.DataFrame(rows).set_index("tarih") if rows else pd.DataFrame()


def hisse_tani(df: pd.DataFrame, baseline_gun=10, kat=3.0, min_ciro_tl=200_000) -> pd.DataFrame:
    sig = sinyal_uret(df, baseline_gun, kat, min_ciro_tl)
    feat = ilk_bar_ozellik(df)
    if len(sig) == 0 or len(feat) == 0:
        return pd.DataFrame()
    return feat.join(sig["sinyal"], how="inner").dropna(subset=["sinyal"])


def _ozet(g: pd.DataFrame) -> pd.Series:
    return pd.Series({
        "n": len(g),
        "ilk_saat_ort_%": round(g["ilk_saat_hareket"].mean() * 100, 2),
        "ilk_saat_medyan_%": round(g["ilk_saat_hareket"].median() * 100, 2),
        "ilk_saat_pozitif_%": round((g["ilk_saat_hareket"] > 0).mean() * 100, 1),
        "ilk_bar_tepe_ort_%": round(g["ilk_bar_tepe"].mean() * 100, 2),
        "ilk_bar_kapanis_ort_%": round(g["ilk_bar_kapanis"].mean() * 100, 2),
        "gun_sonu_ort_%": round(g["gun_sonu"].mean() * 100, 2),
    })


def rapor(tum: pd.DataFrame):
    sinyal = tum[tum["sinyal"]]
    diger = tum[~tum["sinyal"]]
    tablo = pd.DataFrame({"SINYAL gunu": _ozet(sinyal), "Diger gunler": _ozet(diger)})
    print("=" * 64)
    print("ILK BAR MOMENTUM TANISI  (acilis fiyatina gore hareket)")
    print("=" * 64)
    print(tablo.to_string())
    print("-" * 64)
    if len(sinyal):
        fark = sinyal["ilk_saat_hareket"].mean() - diger["ilk_saat_hareket"].mean()
        print(f"Sinyal gunu ilk-saat hareketi, diger gunlerden {fark*100:+.2f} puan farkli.")
        print("ilk_saat_hareket = acilis -> 2.bar acilisi: su an KACIRDIGIMIZ kisim.")
    print("\nNOT: Islenebilir backtest degil; hareketin nerede oldugunu olcer.")


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
    birlesik.to_csv("tani_ilk_bar.csv", index=False)
    print("\n-> tani_ilk_bar.csv kaydedildi.")


if __name__ == "__main__":
    main()
