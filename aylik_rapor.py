"""Aylik rapor: DIP+KIRILIM vs elenen | 5x+ | TP3 SL3 | v2 sim."""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from collections import defaultdict

import numpy as np
import pandas as pd

from evren import evren_yukle
from portfoy_compound import gunluk
from simule_intraday import simule_gun, simule_tut, seans_filtre
from tavan import tavan_acilis_mi
from veri_cache import cek_saatlik, cek_1dk, cek_15dk

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


def _hisse_by_day(hisse, bar_cache, yenile=False):
    """Hisse icin tum gun -> bar sozlugu (cache)."""
    if hisse not in bar_cache:
        d1 = cek_1dk(hisse, yenile=yenile)
        d15 = cek_15dk(hisse, yenile=yenile)
        by = _bars_by_day(d1)
        by15 = _bars_by_day(d15)
        d1_days = set(by.keys())
        for k, v in by15.items():
            if k not in by:
                by[k] = v
        # anahtarlar date (simule_tut uyumu)
        by = {pd.Timestamp(k).date(): v for k, v in by.items()}
        d1_days = {pd.Timestamp(k).date() for k in d1_days}
        bar_cache[hisse] = {"by": by, "d1_days": d1_days}
    return bar_cache[hisse]


def gun_bars(hisse, gun_dt, bar_cache, yenile=False):
    rec = _hisse_by_day(hisse, bar_cache, yenile=yenile)
    by = rec["by"]
    if gun_dt not in by:
        return None, None
    tf = "1dk" if gun_dt in rec["d1_days"] else "15dk"
    return tf, by[gun_dt]


def _simule_sinyal(gun, giris, hisse, giris_gun, son_gun, bar_cache, mod, yenile):
    """mod: gunluk | tut | tut3"""
    giris_gun = pd.Timestamp(giris_gun).date()
    son_gun = pd.Timestamp(son_gun).date()
    sebep, cikis, cikis_t = simule_gun(gun, giris, TARGET, STOP)
    tut_gun = 0
    if mod == "gunluk" or sebep in ("hedef", "stop"):
        return sebep, cikis, cikis_t, tut_gun

    by = _hisse_by_day(hisse, bar_cache, yenile=yenile)["by"]
    gun_list = sorted(
        pd.Timestamp(d).date() for d in by
        if giris_gun <= pd.Timestamp(d).date() <= son_gun
    )
    if not gun_list:
        return sebep, cikis, cikis_t, tut_gun
    max_gun = 3 if mod == "tut3" else None
    sebep, cikis, cikis_t, tut_gun = simule_tut(
        by, gun_list, giris, TARGET, STOP, max_gun=max_gun)
    return sebep, cikis, cikis_t, tut_gun


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


def hisse_performans(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return pd.DataFrame()
    rows = []
    for (hisse, grup), g in df.groupby(["hisse", "grup"], sort=True):
        g = g.sort_values("tarih")
        rets = g["getiri_%"].values / 100
        compound = (np.prod(1 + rets) - 1) * 100 if len(rets) else 0
        sb = g["sebep"].value_counts().to_dict()
        rows.append({
            "hisse": hisse, "grup": grup.upper(), "olay": len(g),
            "hedef": sb.get("hedef", 0), "stop": sb.get("stop", 0),
            "gun_sonu": sb.get("gun_sonu", 0),
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


def topla(hisseler, bas, son, yenile=False, bekle=0.35, mod="tut"):
    sinyaller = []
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
                if t < bas or t > son:
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
                if H <= L or op * ov < 200_000:
                    continue
                pos52 = (op - L) / (H - L)
                dk_c = float(dunk.loc[t]) if not pd.isna(dunk.loc[t]) else np.nan
                # Kirilim: acilista 52h tepeye degmis (gun sonu high degil — lookahead)
                taze = (not np.isnan(dk_c)) and (dk_c < H) and (op >= H)
                grup = siniflendir(pos52, taze)

                tf, gun = gun_bars(h, t, bar_cache, yenile=yenile)
                if gun is None or len(gun) < 4:
                    continue
                giris = op
                if giris <= 0:
                    continue
                if not np.isnan(dk_c) and tavan_acilis_mi(giris, dk_c, float(d.loc[t, "High"])):
                    continue
                mm = mfe_mae(gun, giris)
                sebep, cikis, cikis_t, tut_gun = _simule_sinyal(
                    gun, giris, h, t, son, bar_cache, mod, yenile)
                net = (cikis / giris - 1) - RT
                kova = "dipkir" if grup in ("dip", "kirilim") else "elenen"
                sinyaller.append({
                    "tarih": str(t), "hisse": h, "kova": kova, "grup": grup,
                    "kat": round(kat, 1), "pos52": round(pos52, 3), "giris": giris,
                    "tf": tf, "sebep": sebep, "cikis": round(cikis, 4),
                    "cikis_saat": cikis_t, "getiri_%": round(net * 100, 2),
                    "tut_gun": tut_gun, **mm,
                })
        except Exception as e:
            print(f"  [{i}] {h}: {e}", file=sys.stderr)
        if yenile and i < len(hisseler):
            time.sleep(bekle)
        if i % 50 == 0:
            print(f"  ... {i}/{len(hisseler)}", file=sys.stderr)
    return sinyaller


def compound_grup(sinyaller):
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
        gun_son = sum(poz * (1 + s["getiri_%"] / 100) for s in todays)
        for s in todays:
            net = s["getiri_%"] / 100
            kapali.append({
                "tarih": d, "hisse": s["hisse"], "grup": s["grup"],
                "giris": s["giris"], "cikis": s["cikis"], "sebep": s["sebep"],
                "getiri_%": s["getiri_%"], "poz_tl": round(poz, 0),
                "tl_kar": round(poz * net, 0),
            })
        cash = gun_son
    return cash, pd.DataFrame(kapali)


def ozet(ad, rows, son):
    df = pd.DataFrame(rows)
    if len(df) == 0:
        return {"grup": ad, "olay": 0, "gun": 0, "son_tl": SERMAYE, "getiri_%": 0}
    sb = df["sebep"].value_counts().to_dict()
    return {
        "grup": ad, "olay": len(df), "gun": df["tarih"].nunique(),
        "son_tl": round(son, 0), "getiri_%": round((son / SERMAYE - 1) * 100, 2),
        "win_%": round((df["getiri_%"] > 0).mean() * 100, 1),
        "hedef": sb.get("hedef", 0), "stop": sb.get("stop", 0),
        "gun_sonu": sb.get("gun_sonu", 0),
        "ort_getiri_%": round(df["getiri_%"].mean(), 2),
        "ort_max_%": round(df["max_%"].mean(), 2),
        "ort_min_%": round(df["min_%"].mean(), 2),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bas", required=True, help="YYYY-MM-DD")
    p.add_argument("--son", required=True, help="YYYY-MM-DD")
    p.add_argument("--onek", required=True, help="dosya oneki orn temmuz_2026")
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--yenile", action="store_true")
    p.add_argument("--bekle", type=float, default=0.35)
    p.add_argument("--mod", default="tut", choices=["gunluk", "tut", "tut3"],
                   help="gunluk=ayni gun kapanis; tut=TP/SL'ye kadar; tut3=max 3 gun")
    a = p.parse_args()

    bas = pd.Timestamp(a.bas).date()
    son = pd.Timestamp(a.son).date()
    hisseler = evren_yukle(a.evren)
    print(f"{bas} -> {son} | mod={a.mod} | ({len(hisseler)} hisse)...", file=sys.stderr)
    tum = topla(hisseler, bas, son, yenile=a.yenile, bekle=a.bekle, mod=a.mod)

    dipkir = [s for s in tum if s["kova"] == "dipkir"]
    elenen = [s for s in tum if s["kova"] == "elenen"]
    df_dk = pd.DataFrame(dipkir).sort_values(["tarih", "hisse"])
    df_el = pd.DataFrame(elenen).sort_values(["tarih", "hisse"])
    df_hisse = hisse_performans(df_dk)
    son_dk, cmp_dk = compound_grup(dipkir)
    son_el, cmp_el = compound_grup(elenen)

    pre = a.onek
    pd.DataFrame(tum).to_csv(f"{pre}_tum_olaylar.csv", index=False)
    df_dk.to_csv(f"{pre}_dipkir.csv", index=False)
    df_el.to_csv(f"{pre}_elenen.csv", index=False)
    if len(cmp_dk):
        cmp_dk.to_csv(f"{pre}_dipkir_compound.csv", index=False)
    if len(df_hisse):
        df_hisse.to_csv(f"{pre}_dipkir_hisse.csv", index=False)
    oz = pd.DataFrame([ozet("DIP+KIRILIM", dipkir, son_dk),
                       ozet("ELENEN orta/tepe", elenen, son_el)])
    oz.to_csv(f"{pre}_ozet.csv", index=False)

    print("=" * 88)
    print(f"{bas} -> {son} | 5x+ DIP+KIRILIM | TP %3 SL %3 | mod={a.mod} | {a.evren}")
    if len(df_dk):
        g = sorted(df_dk["tarih"].unique())
        print(f"DIP+KIRILIM gunleri: {g[0]} .. {g[-1]} ({len(g)} gun)")
    print("=" * 88)
    print(oz.to_string(index=False))
    if len(df_dk):
        print(f"\n## DIP+KIRILIM ISLEMLER ({len(df_dk)})")
        cols = ["tarih", "hisse", "grup", "kat", "giris", "sebep", "getiri_%",
                "max_%", "min_%", "tut_gun", "cikis_saat", "tf"]
        print(df_dk[cols].to_string(index=False))
    print(f"\n-> {pre}_ozet.csv | {pre}_dipkir.csv")


if __name__ == "__main__":
    main()
