"""Erken saat kumulatif hacim: normal gunluk hacmin 4x/5x'ine ulasan gunlerde max/min."""
from __future__ import annotations
import argparse
import sys
import numpy as np
import pandas as pd

from evren import evren_yukle
from veri_cache import cek_saatlik

STD = ["Open", "High", "Low", "Close", "Volume"]


def _bar_ciro(bar) -> float:
    p = float(bar["Close"]) if bar["Close"] > 0 else float(bar["Open"])
    return float(bar["Volume"]) * p


def gunluk_tl(hourly: pd.DataFrame) -> pd.Series:
    g = hourly.sort_index().copy()
    g["_d"] = g.index.date
    g["_ciro"] = g.apply(_bar_ciro, axis=1)
    return g.groupby("_d")["_ciro"].sum()


def hisse_sinyaller(hourly: pd.DataFrame, baseline_gun: int, min_kat: float,
                    erken_bar: int, min_ciro_tl: float) -> list[dict]:
    if len(hourly) == 0:
        return []
    gh = hourly.sort_index().copy()
    gh["_d"] = gh.index.date
    gunluk = gunluk_tl(gh)
    baseline = gunluk.rolling(baseline_gun, min_periods=baseline_gun).mean().shift(1)

    gunler = {d: g.sort_index() for d, g in gh.groupby("_d")}
    tarihler = sorted(gunler.keys())
    out = []

    for i, t in enumerate(tarihler):
        if t not in baseline.index or pd.isna(baseline[t]) or baseline[t] <= 0:
            continue
        bl = float(baseline[t])
        gun = gunler[t]
        if len(gun) < 2:
            continue

        kum = 0.0
        tetik_idx = None
        tetik_kat = None
        for j in range(min(erken_bar, len(gun))):
            kum += _bar_ciro(gun.iloc[j])
            kat = kum / bl
            if kat >= min_kat and kum >= min_ciro_tl:
                tetik_idx = j
                tetik_kat = kat
                break
        if tetik_idx is None:
            continue

        bar = gun.iloc[tetik_idx]
        giris = float(bar["Close"])
        if giris <= 0:
            giris = float(bar["Open"])
        if giris <= 0:
            continue

        kalan = gun.iloc[tetik_idx:]
        mfe_gun = float(kalan["High"].max()) / giris - 1
        mae_gun = float(kalan["Low"].min()) / giris - 1
        kapanis_gun = float(gun.iloc[-1]["Close"]) / giris - 1

        fwd = {}
        for off in (1, 2, 3, 5):
            if i + off >= len(tarihler):
                break
            gt = gunler[tarihler[i + off]]
            fwd[f"mfe_t{off}"] = float(gt["High"].max()) / giris - 1
            fwd[f"mae_t{off}"] = float(gt["Low"].min()) / giris - 1
            fwd[f"kapanis_t{off}"] = float(gt.iloc[-1]["Close"]) / giris - 1

        cum_mfe = mfe_gun
        cum_mae = mae_gun
        for off in range(1, 6):
            if i + off >= len(tarihler):
                break
            gt = gunler[tarihler[i + off]]
            cum_mfe = max(cum_mfe, float(gt["High"].max()) / giris - 1)
            cum_mae = min(cum_mae, float(gt["Low"].min()) / giris - 1)

        out.append({
            "tarih": t,
            "hisse": None,
            "kat": round(tetik_kat, 2),
            "baseline_tl": round(bl, 0),
            "kum_ciro_tl": round(kum, 0),
            "tetik_bar": int(tetik_idx),
            "tetik_saat": str(bar.name)[:16] if hasattr(bar.name, "__str__") else "",
            "giris": round(giris, 4),
            "mfe_gun_kalan_%": round(mfe_gun * 100, 2),
            "mae_gun_kalan_%": round(mae_gun * 100, 2),
            "kapanis_gun_%": round(kapanis_gun * 100, 2),
            "mfe_5g_%": round(cum_mfe * 100, 2),
            "mae_5g_%": round(cum_mae * 100, 2),
            **{k: round(v * 100, 2) for k, v in fwd.items()},
        })
    return out


def ozet(df: pd.DataFrame) -> pd.Series:
    if len(df) == 0:
        return pd.Series({"n": 0})
    s = {"n": len(df),
         "mfe_gun_ort_%": round(df["mfe_gun_kalan_%"].mean(), 2),
         "mae_gun_ort_%": round(df["mae_gun_kalan_%"].mean(), 2),
         "kapanis_gun_ort_%": round(df["kapanis_gun_%"].mean(), 2)}
    for c in df.columns:
        if c.startswith("mfe_t") or c.startswith("mae_t") or c.startswith("kapanis_t"):
            s[f"{c}_ort"] = round(df[c].mean(), 2)
    if "mfe_5g_%" in df.columns:
        s["mfe_5g_ort_%"] = round(df["mfe_5g_%"].mean(), 2)
        s["mae_5g_ort_%"] = round(df["mae_5g_%"].mean(), 2)
        s["mfe5g>=3_%"] = round((df["mfe_5g_%"] >= 3).mean() * 100, 1)
        s["mae5g<=-3_%"] = round((df["mae_5g_%"] <= -3).mean() * 100, 1)
    return pd.Series(s)


def rapor(res: pd.DataFrame, min_kat: float, baseline_gun: int, erken_bar: int):
    print("=" * 70)
    print(f"ERKEN KUMULATIF HACIM | baseline={baseline_gun}g gunluk TL | erken={erken_bar} bar")
    print(f"Esik: kumulatif ciro >= {min_kat}x normal gunluk hacim")
    print("=" * 70)
    print(f"Toplam sinyal: {len(res)} | {res['tarih'].min()} -> {res['tarih'].max()}")
    print(ozet(res).to_string())
    print("-" * 70)
    print("Tetik bar dagilimi (0=09:00, 1=10:00, ...):")
    print(res["tetik_bar"].value_counts().sort_index().to_string())
    print("-" * 70)
    kovalar = [(f"{min_kat}-{min_kat+1}x", min_kat, min_kat + 1),
               (f"{min_kat+1}-{min_kat+3}x", min_kat + 1, min_kat + 3),
               (f"{min_kat+3}x+", min_kat + 3, 1e9)]
    for ad, lo, hi in kovalar:
        alt = res[(res["kat"] >= lo) & (res["kat"] < hi)]
        if len(alt):
            print(f"  {ad} (n={len(alt)}): mfe_gun={alt['mfe_gun_kalan_%'].mean():.2f}% "
                  f"mae_gun={alt['mae_gun_kalan_%'].mean():.2f}% "
                  f"mfe_5g={alt['mfe_5g_%'].mean():.2f}% mae_5g={alt['mae_5g_%'].mean():.2f}%")
    print("NOT: giris = tetik saatindeki kapanis; analiz aracidir.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    p.add_argument("--baseline", type=int, default=20)
    p.add_argument("--min_kat", type=float, default=4.0)
    p.add_argument("--erken_bar", type=int, default=4,
                     help="Erken saat: ilk N saatlik bar (4=12:00'a kadar)")
    p.add_argument("--min_ciro", type=float, default=200_000)
    p.add_argument("--csv", default=None)
    a = p.parse_args()

    hisseler = evren_yukle(a.evren)
    hepsi = []
    for i, h in enumerate(hisseler, 1):
        try:
            hourly = cek_saatlik(h, tv_user=a.tv_user, tv_pass=a.tv_pass, sessiz=True)
            for k in hisse_sinyaller(hourly, a.baseline, a.min_kat, a.erken_bar, a.min_ciro):
                k["hisse"] = h
                hepsi.append(k)
            print(f"  [{i}/{len(hisseler)}] {h}: {sum(1 for x in hepsi if x['hisse']==h)}", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)

    if not hepsi:
        print("Sinyal yok.")
        return
    res = pd.DataFrame(hepsi)
    csv = a.csv or f"erken_kumulatif_{int(a.min_kat)}x.csv"
    res.to_csv(csv, index=False)
    rapor(res, a.min_kat, a.baseline, a.erken_bar)
    print(f"\n-> {csv}")


if __name__ == "__main__":
    main()
