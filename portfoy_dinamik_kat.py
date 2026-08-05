"""Hacim Nx oldugu saatte giris | 5x ayri esik | DIP+KIRILIM | TP %3 SL %3."""
from __future__ import annotations
import datetime as dt
import sys

import numpy as np
import pandas as pd
from evren import evren_yukle
from veri_cache import cek_saatlik, cek_15dk
from portfoy_compound import gunluk
from portfoy_erken_dk_dipkir import simule_gecikmis

BASLANGIC = dt.date(2026, 1, 2)
TARGET = STOP = 0.03
RT = 2 * (0.00009 + 0.000075)
SERMAYE = 100_000
KATLAR = [2, 3, 4, 5, 8]
MAX_SAAT_BAR = 8


def baseline_kum_saat(hourly: pd.DataFrame, baseline_gun: int) -> dict[int, pd.Series]:
    """Her saat indeksi icin kumulatif hacim baseline (20g ort, shift 1)."""
    gh = hourly.sort_index().copy()
    gh["_d"] = gh.index.date
    gunler = sorted(gh["_d"].unique())
    kum_by_day = {}
    for d in gunler:
        g = gh[gh["_d"] == d]
        s = 0.0
        arr = []
        for j in range(min(len(g), MAX_SAAT_BAR)):
            s += float(g.iloc[j]["Volume"])
            arr.append(s)
        kum_by_day[d] = arr
    bl = {}
    for j in range(MAX_SAAT_BAR):
        ser = pd.Series({d: kum_by_day[d][j] for d in gunler if len(kum_by_day[d]) > j})
        ser = ser.sort_index()
        bl[j] = ser.rolling(baseline_gun, min_periods=baseline_gun).mean().shift(1)
    return bl


def tetik_bul(gun_h, bl_saat, min_kat: float):
    """Ilk saat bar indeksi Nx tetiklenince (bar kapanisi = giris zamani)."""
    gun_h = gun_h.sort_index()
    s = 0.0
    for i in range(min(len(gun_h), MAX_SAAT_BAR)):
        s += float(gun_h.iloc[i]["Volume"])
        if i not in bl_saat:
            continue
        # baseline serisi date index
        d = gun_h.index[i].date()
        if d not in bl_saat[i].index or pd.isna(bl_saat[i].loc[d]):
            continue
        bl = float(bl_saat[i].loc[d])
        if bl <= 0:
            continue
        if s / bl >= min_kat:
            kapanis = gun_h.index[i] + pd.Timedelta(hours=1)
            return i, s / bl, kapanis, s
    return None


def giris_15dk(gun_dk: pd.DataFrame, en_erken: pd.Timestamp):
    gun_dk = gun_dk.sort_index()
    for i in range(len(gun_dk)):
        if gun_dk.index[i] >= en_erken:
            return i, float(gun_dk.iloc[i]["Open"])
    return None, None


def topla_dinamik(hisseler, p, min_kat: float, bl_cache: dict):
    sinyaller = []
    bar_veri = {}
    for i, h in enumerate(hisseler, 1):
        try:
            if h not in bl_cache:
                hourly = cek_saatlik(h, tv_user=p.tv_user, tv_pass=p.tv_pass)
                if len(hourly) == 0:
                    bl_cache[h] = None
                    continue
                d = gunluk(hourly)
                if len(d) < p.hafta52 + 5:
                    bl_cache[h] = None
                    continue
                bl_cache[h] = {
                    "bl_saat": baseline_kum_saat(hourly, p.baseline),
                    "d": d,
                    "hi52": d["High"].rolling(p.hafta52, min_periods=p.hafta52 // 2).max().shift(1),
                    "lo52": d["Low"].rolling(p.hafta52, min_periods=p.hafta52 // 2).min().shift(1),
                    "dunk": d["Close"].shift(1),
                    "hourly_days": {t: g.sort_index() for t, g in hourly.groupby(hourly.index.date)},
                }
            meta = bl_cache[h]
            if meta is None:
                continue
            dk = cek_15dk(h, tv_user=p.tv_user, tv_pass=p.tv_pass)
            if len(dk) == 0:
                continue
            gm = dk.sort_index().copy()
            gm["_t"] = gm.index.date
            by_dk = {t: g.sort_index() for t, g in gm.groupby("_t")}
            h_sinyal = []
            for t in sorted(by_dk.keys()):
                if t < BASLANGIC:
                    continue
                if t not in meta["hourly_days"]:
                    continue
                gun_h = meta["hourly_days"][t]
                gun_dk = by_dk[t]
                tetik = tetik_bul(gun_h, meta["bl_saat"], min_kat)
                if tetik is None:
                    continue
                _, kat, kapanis, kum_vol = tetik
                entry_idx, giris = giris_15dk(gun_dk, kapanis)
                if entry_idx is None or giris <= 0:
                    continue
                if len(gun_dk) - entry_idx < 4:
                    continue
                if t not in meta["d"].index:
                    continue
                hi52, lo52, dunk = meta["hi52"], meta["lo52"], meta["dunk"]
                if pd.isna(hi52.loc[t]) or pd.isna(lo52.loc[t]):
                    continue
                H, L, dk_c = float(hi52.loc[t]), float(lo52.loc[t]), float(dunk.loc[t])
                if H <= L:
                    continue
                if giris * kum_vol < p.min_ciro:
                    continue
                tepe = float(gun_dk.iloc[: entry_idx + 1]["High"].max())
                pos52 = (giris - L) / (H - L)
                taze = (float(dunk.loc[t]) < H) and (tepe >= H)
                if pos52 <= p.dip_esik:
                    grup = "dip"
                elif taze:
                    grup = "kirilim"
                elif pos52 >= p.ust_esik:
                    continue
                else:
                    continue
                h_sinyal.append({
                    "tarih": str(t), "hisse": h, "grup": grup,
                    "kat": round(kat, 1), "pos52": round(pos52, 3), "giris": giris,
                    "acilis_gun": float(gun_dk.iloc[0]["Open"]),
                    "entry_idx": entry_idx,
                    "giris_saat": str(gun_dk.index[entry_idx])[:16],
                })
            if h_sinyal:
                sinyaller.extend(h_sinyal)
                ilk = min(s["tarih"] for s in h_sinyal)
                bd = {}
                for t, g in by_dk.items():
                    if str(t) >= ilk:
                        bd[str(t)] = (g["Low"].values.astype("float64"),
                                      g["High"].values.astype("float64"),
                                      g["Close"].values.astype("float64"),
                                      float(g.iloc[-1]["Close"]))
                bar_veri[h] = bd
        except Exception as e:
            print(f"  [{i}] {h} mk{min_kat}: {e}", file=sys.stderr)
    return sinyaller, bar_veri


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--evren", default="evren.csv")
    a = ap.parse_args()

    class Cfg:
        evren = a.evren
        tv_user = tv_pass = None
        baseline = 20
        hafta52 = 252
        dip_esik = 0.20
        ust_esik = 0.80
        min_ciro = 200_000

    hisseler = evren_yukle(Cfg.evren)
    bl_cache = {}
    ozet = []

    print("=" * 78)
    print("DINAMIK GIRIS | hacim Nx oldugu saat | DIP+KIRILIM | TP %3 SL %3 | compound")
    print(f"Evren: {Cfg.evren} ({len(hisseler)} hisse) | {BASLANGIC} ->")
    print("=" * 78)

    for mk in KATLAR:
        print(f"\n--- min_kat {mk}x taranıyor ---", file=sys.stderr)
        sinyal, bar_veri = topla_dinamik(hisseler, Cfg(), float(mk), bl_cache)
        dipkir = [s for s in sinyal if s["grup"] in ("dip", "kirilim")]
        kapali, son = simule_gecikmis(dipkir, bar_veri, TARGET, STOP, RT, SERMAYE)
        df = pd.DataFrame(kapali).sort_values(["giris_tarih", "hisse"]) if kapali else pd.DataFrame()
        tag = f"dinamik_{mk}x.csv"
        if len(df):
            df.to_csv(tag, index=False)
        win = (df["getiri_%"] > 0).mean() * 100 if len(df) else 0
        sb = df["sebep"].value_counts().to_dict() if len(df) else {}
        ozet.append({
            "min_kat": f"{mk}x",
            "sinyal": len(dipkir),
            "islem": len(df),
            "son_tl": round(son, 0),
            "getiri_%": round((son / SERMAYE - 1) * 100, 2),
            "win_%": round(win, 1),
            "hedef": sb.get("hedef", 0),
            "stop": sb.get("stop", 0),
        })
        print(f"{mk}x | sinyal={len(dipkir)} islem={len(df)} son={son:,.0f} "
              f"getiri={(son/SERMAYE-1)*100:.2f}% win={win:.1f}% sebep={sb}")

    odf = pd.DataFrame(ozet)
    odf.to_csv("dinamik_kat_ozet.csv", index=False)
    print("\n" + "=" * 78)
    print("OZET")
    print(odf.to_string(index=False))
    print("\n-> dinamik_kat_ozet.csv | dinamik_2x.csv ... dinamik_8x.csv")


if __name__ == "__main__":
    main()
