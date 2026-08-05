"""Haziran 2026: DIP+KIRILIM vs elenen (5x+ orta/tepe) | TP3 SL3 | MFE/MAE alarm sonrasi."""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time

import numpy as np
import pandas as pd
from collections import defaultdict

from evren import evren_yukle
from portfoy_compound import gunluk
from simule_intraday import simule_gun, seans_filtre
from tavan import tavan_acilis_mi
from veri_cache import cek_saatlik, cek_1dk, cek_15dk

HAZIRAN_BAS = dt.date(2026, 6, 1)
HAZIRAN_SON = dt.date(2026, 6, 30)
MIN_KAT = 5.0
TARGET = STOP = 0.03
RT = 2 * (0.00009 + 0.000075)
SERMAYE = 100_000
DIP_ESIK = 0.20
UST_ESIK = 0.80


def siniflendir(pos52, taze_kirilim):
    if pos52 <= DIP_ESIK:
        return "dip"
    if taze_kirilim:
        return "kirilim"
    if pos52 >= UST_ESIK:
        return "tepe"
    return "orta"


def _bars_by_day(df):
    if len(df) == 0:
        return {}
    gm = df.sort_index()
    gm["_t"] = gm.index.date
    return {t: g.sort_index() for t, g in gm.groupby("_t")}


def gun_bars(hisse, gun_dt, bar_cache, yenile=False):
    """1dk oncelikli; gun bazli cache."""
    if hisse not in bar_cache:
        bar_cache[hisse] = {}
    if gun_dt in bar_cache[hisse]:
        return bar_cache[hisse][gun_dt]
    d1 = cek_1dk(hisse, yenile=yenile)
    d15 = cek_15dk(hisse, yenile=yenile)
    by1, by15 = _bars_by_day(d1), _bars_by_day(d15)
    if gun_dt in by1:
        r = ("1dk", by1[gun_dt])
    elif gun_dt in by15:
        r = ("15dk", by15[gun_dt])
    else:
        r = (None, None)
    bar_cache[hisse][gun_dt] = r
    return r


def mfe_mae(gun, giris):
    g = seans_filtre(gun)
    if len(g) == 0:
        g = gun.sort_index()
    mh, ml = float(g["High"].max()), float(g["Low"].min())
    max_saat, min_saat = "", ""
    for i in range(len(g)):
        hi, lo = float(g.iloc[i].High), float(g.iloc[i].Low)
        ts = str(g.index[i])[11:16]
        if hi >= mh - 1e-9:
            max_saat = ts
        if lo <= ml + 1e-9:
            min_saat = ts
    return {
        "max_%": round((mh / giris - 1) * 100, 2),
        "min_%": round((ml / giris - 1) * 100, 2),
        "max_saat": max_saat,
        "min_saat": min_saat,
        "max_fiyat": round(mh, 4),
        "min_fiyat": round(ml, 4),
    }


def simule_gun_wrap(gun, giris):
    sebep, cikis, cikis_t = simule_gun(gun, giris, TARGET, STOP)
    return sebep, cikis, cikis_t


def hisse_performans(df: pd.DataFrame) -> pd.DataFrame:
    """Hisse x grup (dip/kirilim) ozet: kar/zarar, max/min."""
    if len(df) == 0:
        return pd.DataFrame()
    rows = []
    for (hisse, grup), g in df.groupby(["hisse", "grup"], sort=True):
        g = g.sort_values("tarih")
        rets = g["getiri_%"].values / 100
        compound = (np.prod(1 + rets) - 1) * 100 if len(rets) else 0
        toplam = float(g["getiri_%"].sum())
        win = int((g["getiri_%"] > 0).sum())
        loss = int((g["getiri_%"] <= 0).sum())
        sb = g["sebep"].value_counts().to_dict()
        rows.append({
            "hisse": hisse,
            "grup": grup.upper(),
            "olay": len(g),
            "hedef": sb.get("hedef", 0),
            "stop": sb.get("stop", 0),
            "gun_sonu": sb.get("gun_sonu", 0),
            "win": win,
            "loss": loss,
            "toplam_getiri_%": round(toplam, 2),
            "compound_%": round(compound, 2),
            "durum": "KAR" if compound > 0 else ("ZARAR" if compound < 0 else "BASABAS"),
            "ort_getiri_%": round(g["getiri_%"].mean(), 2),
            "ort_max_%": round(g["max_%"].mean(), 2),
            "ort_min_%": round(g["min_%"].mean(), 2),
            "en_yuksek_max_%": round(g["max_%"].max(), 2),
            "en_derin_min_%": round(g["min_%"].min(), 2),
            "tarihler": ", ".join(g["tarih"].str[-5:].tolist()),
        })
    out = pd.DataFrame(rows)
    out["_g"] = out["grup"].map({"DIP": 0, "KIRILIM": 1}).fillna(2)
    return out.sort_values(["_g", "compound_%"], ascending=[True, False]).drop(columns="_g")


def topla_haziran(hisseler, yenile=False, bekle=0.35):
    sinyaller = []
    bar_veri = {}
    bar_cache = {}

    for i, h in enumerate(hisseler, 1):
        try:
            hourly = cek_saatlik(h, yenile=yenile)
            if len(hourly) == 0:
                continue
            d = gunluk(hourly)
            if len(d) < 25:
                continue
            baseline = d["ovol"].rolling(20, min_periods=20).mean().shift(1)
            hi52 = d["High"].rolling(252, min_periods=126).max().shift(1)
            lo52 = d["Low"].rolling(252, min_periods=126).min().shift(1)
            dunk = d["Close"].shift(1)

            for t in d.index:
                if t < HAZIRAN_BAS or t > HAZIRAN_SON:
                    continue
                if pd.isna(baseline.loc[t]) or pd.isna(hi52.loc[t]) or pd.isna(lo52.loc[t]):
                    continue
                bl = float(baseline.loc[t])
                if bl <= 0:
                    continue
                ov = float(d.loc[t, "ovol"])
                op = float(d.loc[t, "Open"])
                kat = ov / bl
                if kat < MIN_KAT:
                    continue
                H, L = float(hi52.loc[t]), float(lo52.loc[t])
                if H <= L:
                    continue
                if op * ov < 200_000:
                    continue
                pos52 = (op - L) / (H - L)
                dk_c = float(dunk.loc[t]) if not pd.isna(dunk.loc[t]) else np.nan
                taze = (not np.isnan(dk_c)) and (dk_c < H) and (op >= H)
                grup = siniflendir(pos52, taze)

                tf, gun = gun_bars(h, t, bar_cache, yenile=yenile)
                if gun is None or len(gun) < 4:
                    continue
                giris = op  # saatlik acilis — intraday ilk bar degil
                if giris <= 0:
                    continue
                if not np.isnan(dk_c) and tavan_acilis_mi(giris, dk_c, float(d.loc[t, "High"])):
                    continue

                mm = mfe_mae(gun, giris)
                sebep, cikis, cikis_t = simule_gun_wrap(gun, giris)
                net = (cikis / giris - 1) - RT

                kova = "dipkir" if grup in ("dip", "kirilim") else "elenen"
                rec = {
                    "tarih": str(t), "hisse": h, "kova": kova, "grup": grup,
                    "kat": round(kat, 1), "pos52": round(pos52, 3), "giris": giris,
                    "tf": tf, "sebep": sebep, "cikis": round(cikis, 4), "cikis_saat": cikis_t,
                    "getiri_%": round(net * 100, 2), **mm,
                }
                sinyaller.append(rec)

                # bar_veri compound icin
                if h not in bar_veri:
                    bar_veri[h] = {}
                if str(t) not in bar_veri[h]:
                    gsim = seans_filtre(gun)
                    if len(gsim) == 0:
                        gsim = gun.sort_index()
                    bar_veri[h][str(t)] = (
                        gsim["Low"].values.astype("float64"),
                        gsim["High"].values.astype("float64"),
                        float(gsim.iloc[-1]["Close"]),
                    )
        except Exception as e:
            print(f"  [{i}] {h}: {e}", file=sys.stderr)
        if yenile and i < len(hisseler):
            time.sleep(bekle)
        if i % 50 == 0:
            print(f"  ... {i}/{len(hisseler)}", file=sys.stderr)

    return sinyaller, bar_veri


def compound_grup(sinyaller, _bar_veri=None):
    """Gunluk all-in compound — islem bazli yeni sim sonuclarindan."""
    if not sinyaller:
        return SERMAYE, pd.DataFrame()
    by_day = defaultdict(list)
    for s in sinyaller:
        by_day[s["tarih"]].append(s)
    cash = float(SERMAYE)
    kapali = []
    for d in sorted(by_day.keys()):
        todays = by_day[d]
        poz = cash / len(todays)
        gun_son = 0.0
        for s in todays:
            net = s["getiri_%"] / 100
            gun_son += poz * (1 + net)
            kapali.append({
                "tarih": d, "hisse": s["hisse"], "grup": s["grup"],
                "giris": s["giris"], "cikis": s["cikis"], "sebep": s["sebep"],
                "getiri_%": s["getiri_%"], "poz_tl": round(poz, 0),
                "tl_kar": round(poz * net, 0),
            })
        cash = gun_son
    return cash, pd.DataFrame(kapali)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--yenile", action="store_true", help="saatlik cache yenile")
    p.add_argument("--bekle", type=float, default=0.35)
    a = p.parse_args()

    hisseler = evren_yukle(a.evren)
    print(f"Haziran 2026 taranıyor ({len(hisseler)} hisse, yenile={a.yenile})...",
          file=sys.stderr)
    tum, bar_veri = topla_haziran(hisseler, yenile=a.yenile, bekle=a.bekle)

    dipkir = [s for s in tum if s["kova"] == "dipkir"]
    elenen = [s for s in tum if s["kova"] == "elenen"]

    df_all = pd.DataFrame(tum).sort_values(["kova", "tarih", "hisse"])
    df_dk = pd.DataFrame(dipkir).sort_values(["tarih", "hisse"])
    df_el = pd.DataFrame(elenen).sort_values(["tarih", "hisse"])
    df_hisse = hisse_performans(df_dk)

    son_dk, cmp_dk = compound_grup(dipkir, bar_veri)
    son_el, cmp_el = compound_grup(elenen, bar_veri)

    df_all.to_csv("haziran_2026_tum_olaylar.csv", index=False)
    df_dk.to_csv("haziran_2026_dipkir.csv", index=False)
    df_el.to_csv("haziran_2026_elenen.csv", index=False)
    if len(cmp_dk):
        cmp_dk.to_csv("haziran_2026_dipkir_compound.csv", index=False)
    if len(cmp_el):
        cmp_el.to_csv("haziran_2026_elenen_compound.csv", index=False)
    if len(df_hisse):
        df_hisse.to_csv("haziran_2026_dipkir_hisse.csv", index=False)

    def ozet(ad, rows, son):
        df = pd.DataFrame(rows)
        if len(df) == 0:
            return {"grup": ad, "olay": 0}
        win = (df["getiri_%"] > 0).mean() * 100
        sb = df["sebep"].value_counts().to_dict()
        return {
            "grup": ad,
            "olay": len(df),
            "gun": df["tarih"].nunique(),
            "son_tl": round(son, 0),
            "getiri_%": round((son / SERMAYE - 1) * 100, 2) if son else 0,
            "win_%": round(win, 1),
            "hedef": sb.get("hedef", 0),
            "stop": sb.get("stop", 0),
            "gun_sonu": sb.get("gun_sonu", 0),
            "ort_getiri_%": round(df["getiri_%"].mean(), 2),
            "ort_max_%": round(df["max_%"].mean(), 2),
            "ort_min_%": round(df["min_%"].mean(), 2),
            "medyan_max_%": round(df["max_%"].median(), 2),
            "medyan_min_%": round(df["min_%"].median(), 2),
        }

    oz = pd.DataFrame([ozet("DIP+KIRILIM", dipkir, son_dk),
                       ozet("ELENEN orta/tepe", elenen, son_el)])
    oz.to_csv("haziran_2026_ozet.csv", index=False)

    gunler = sorted(df_dk["tarih"].unique()) if len(df_dk) else []
    print("=" * 88)
    print(f"HAZIRAN 2026 | 5x+ | {HAZIRAN_BAS} -> {HAZIRAN_SON} | TP %3 SL %3 compound | {a.evren}")
    if gunler:
        print(f"Sinyal gunleri: {gunler[0]} .. {gunler[-1]} ({len(gunler)} gun)")
    print("=" * 88)
    print("\n## OZET")
    print(oz.to_string(index=False))

    if len(df_hisse):
        print("\n## DIP + KIRILIM — HISSE PERFORMANSI (kar/zarar, max/min)")
        cols_h = ["hisse", "grup", "olay", "hedef", "stop", "gun_sonu",
                  "durum", "compound_%", "toplam_getiri_%", "ort_getiri_%",
                  "ort_max_%", "ort_min_%", "en_yuksek_max_%", "en_derin_min_%", "tarihler"]
        print(df_hisse[cols_h].to_string(index=False))

    for ad, df in [("DIP+KIRILIM", df_dk), ("ELENEN", df_el)]:
        if len(df) == 0:
            continue
        print(f"\n## {ad} — TUM OLAYLAR (alarm sonrasi max/min dahil)")
        df = df.copy()
        df["durum"] = np.where(df["getiri_%"] > 0, "KAR",
                               np.where(df["getiri_%"] < 0, "ZARAR", "BASABAS"))
        cols = ["tarih", "hisse", "grup", "kat", "giris", "sebep", "durum", "getiri_%",
                "max_%", "min_%", "max_saat", "min_saat", "tf"]
        print(df[cols].to_string(index=False))

    print("\n-> haziran_2026_ozet.csv | haziran_2026_dipkir.csv | haziran_2026_dipkir_hisse.csv")


if __name__ == "__main__":
    main()
