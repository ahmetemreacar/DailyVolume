"""Erken kumulatif hacim (15/30/60 dk) + DIP+KIRILIM | TP %3 SL %3 | 4x/5x."""
from __future__ import annotations
import argparse
import datetime as dt
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
from evren import evren_yukle
from veri_cache import cek_saatlik, cek_1dk
from portfoy_compound import topla, simule as simule_open

TARGET = STOP = 0.03
RT = 2 * (0.00009 + 0.000075)
SERMAYE = 100_000
KATLAR = [4, 5]
DAKIKALAR = [15, 30, 60]
ACILIS_SON = dt.time(10, 5)


def _bar_ciro(row) -> float:
    p = float(row["Close"]) if float(row["Close"]) > 0 else float(row["Open"])
    return float(row["Volume"]) * p


def gunluk_tl_baseline(hourly: pd.DataFrame, baseline_gun: int) -> pd.Series:
    g = hourly.sort_index().copy()
    g["_d"] = g.index.date
    g["_ciro"] = g.apply(_bar_ciro, axis=1)
    gunluk = g.groupby("_d")["_ciro"].sum()
    return gunluk.rolling(baseline_gun, min_periods=baseline_gun).mean().shift(1)


def pencere_sinyal(gun: pd.DataFrame, dakika: int, bl: float, min_kat: float,
                   min_ciro: float):
    gun = gun.sort_index()
    if gun.index[0].time() > ACILIS_SON:
        return None
    t0 = gun.index[0]
    t_end = t0 + pd.Timedelta(minutes=dakika)
    pencere = gun[(gun.index >= t0) & (gun.index <= t_end)]
    if len(pencere) == 0:
        return None
    kum = sum(_bar_ciro(pencere.iloc[i]) for i in range(len(pencere)))
    if kum < min_ciro:
        return None
    kat = kum / bl
    if kat < min_kat:
        return None
    giris = float(pencere.iloc[-1]["Close"])
    if giris <= 0:
        return None
    entry_idx = int(gun.index.get_loc(pencere.index[-1]))
    return {"kat": round(kat, 2), "giris": giris, "entry_idx": entry_idx,
            "kum_ciro": round(kum, 0)}


def topla_kumulatif(hisseler, p, dakika: int):
    sinyaller = []
    bar_veri = {}
    baseline_cache = {}

    for i, h in enumerate(hisseler, 1):
        try:
            hourly = cek_saatlik(h, tv_user=p.tv_user, tv_pass=p.tv_pass)
            dk1 = cek_1dk(h, tv_user=p.tv_user, tv_pass=p.tv_pass)
            if len(hourly) == 0 or len(dk1) == 0:
                continue
            bl_ser = gunluk_tl_baseline(hourly, p.baseline)
            gm = dk1.sort_index().copy()
            gm["_t"] = gm.index.date
            by_day = {t: g.sort_index() for t, g in gm.groupby("_t")}
            en_yeni = max(by_day.keys())
            h_sinyal = []
            for t in sorted(by_day.keys()):
                gun = by_day[t]
                if len(gun) < p.min_bar or (en_yeni - t).days > p.son_gun:
                    continue
                if t not in bl_ser.index or pd.isna(bl_ser[t]) or bl_ser[t] <= 0:
                    continue
                sig = pencere_sinyal(gun, dakika, float(bl_ser[t]), p.min_kat, p.min_ciro)
                if sig is None:
                    continue
                h_sinyal.append({
                    "tarih": str(t), "hisse": h, "grup": "kumulatif",
                    "kat": sig["kat"], "pos52": None, "giris": sig["giris"],
                    "entry_idx": sig["entry_idx"], "dakika": dakika,
                    "kum_ciro": sig["kum_ciro"],
                })
            if h_sinyal:
                sinyaller.extend(h_sinyal)
                ilk = min(s["tarih"] for s in h_sinyal)
                bd = {}
                for t, g in by_day.items():
                    if str(t) >= ilk:
                        bd[str(t)] = (g["Low"].values.astype("float64"),
                                      g["High"].values.astype("float64"),
                                      float(g.iloc[-1]["Close"]))
                bar_veri[h] = bd
            print(f"  [{i}/{len(hisseler)}] {h} dk{dakika}: {len(h_sinyal)}", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)
    return sinyaller, bar_veri


def simule_gecikmis(sinyaller, bar_veri, target, stop, rt, sermaye):
    by_day = defaultdict(list)
    for s in sinyaller:
        by_day[s["tarih"]].append(s)
    gunler = sorted({d for h in bar_veri for d in bar_veri[h]})
    cash = float(sermaye)
    acik = []
    kapali = []

    for D in gunler:
        todays = by_day.get(D, [])
        if todays and cash > 1:
            poz = cash / len(todays)
            for s in todays:
                acik.append({
                    "hisse": s["hisse"], "gt": D, "gf": s["giris"], "poz": poz,
                    "grup": s.get("grup", ""), "kat": s["kat"],
                    "pos52": s.get("pos52"), "mh": s["giris"],
                    "entry_idx": s.get("entry_idx", 0),
                    "dakika": s.get("dakika"),
                })
            cash = 0.0

        yeni = []
        for q in acik:
            bd = bar_veri.get(q["hisse"], {}).get(D)
            if bd is None:
                yeni.append(q)
                continue
            lows, highs = bd[0], bd[1]
            eod = bd[3] if len(bd) > 3 else bd[2]
            ust = q["gf"] * (1 + target)
            alt = q["gf"] * (1 - stop)
            basla = (q["entry_idx"] + 1) if D == q["gt"] else 0
            cikti = False
            cf = sb = None
            for k in range(basla, len(highs)):
                hi = float(highs[k])
                lo = float(lows[k])
                if hi > q["mh"]:
                    q["mh"] = hi
                hed = hi >= ust
                stp = lo <= alt
                if stp and hed:
                    cf, sb = alt, "stop"
                    cikti = True
                    break
                if hed:
                    cf, sb = ust, "hedef"
                    cikti = True
                    break
                if stp:
                    cf, sb = alt, "stop"
                    cikti = True
                    break
            if cikti:
                net = cf / q["gf"] - 1 - rt
                cash += q["poz"] * (1 + net)
                kapali.append(_kayit(q, D, cf, sb, net))
            else:
                yeni.append(q)
        acik = yeni

    for q in acik:
        gunlist = sorted(bar_veri.get(q["hisse"], {}).keys())
        sonD = [g for g in gunlist if g >= q["gt"]]
        bd_end = bar_veri[q["hisse"]][sonD[-1]] if sonD else None
        sc = (bd_end[3] if bd_end and len(bd_end) > 3 else bd_end[2]) if bd_end else q["gf"]
        net = (sc / q["gf"] - 1) - rt
        cash += q["poz"] * (1 + net)
        kapali.append(_kayit(q, sonD[-1] if sonD else q["gt"], sc, "acik_kaldi", net))
    return kapali, cash


def _kayit(q, D, cf, sb, net):
    return {
        "giris_tarih": q["gt"], "hisse": q["hisse"], "grup": q["grup"],
        "kat": q["kat"], "pos52": q["pos52"], "giris": round(q["gf"], 4),
        "poz_tl": round(q["poz"], 0), "cikis_tarih": D, "cikis": round(cf, 4),
        "sebep": sb, "getiri_%": round(net * 100, 2),
        "tl_kar": round(q["poz"] * net, 0),
        "max_gordugu_%": round((q["mh"] / q["gf"] - 1) * 100, 2),
        "dakika": q.get("dakika"),
    }


def ozet_satir(test, mk, sinyal, df, son):
    sb = df["sebep"].value_counts().to_dict() if len(df) else {}
    return {
        "test": test,
        "min_kat": f"{mk}x",
        "sinyal": sinyal,
        "islem": len(df),
        "son_tl": round(son, 0),
        "getiri_%": round((son / SERMAYE - 1) * 100, 2) if len(df) else 0,
        "win_%": round((df["getiri_%"] > 0).mean() * 100, 1) if len(df) else 0,
        "hedef": sb.get("hedef", 0),
        "stop": sb.get("stop", 0),
        "acik_kaldi": sb.get("acik_kaldi", 0),
        "dip": (df["grup"] == "dip").sum() if len(df) and "grup" in df else 0,
        "kirilim": (df["grup"] == "kirilim").sum() if len(df) and "grup" in df else 0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    a = p.parse_args()

    class Cfg:
        evren = a.evren
        tv_user = a.tv_user
        tv_pass = a.tv_pass
        min_kat = 4.0
        baseline = 20
        hafta52 = 252
        dip_esik = 0.20
        ust_esik = 0.80
        min_ciro = 200_000
        min_bar = 200
        son_gun = 90
        komisyon = 0.00009
        bsmv = 0.000075
        slippage = 0.0
        acilis_son = "10:05"

    hisseler = evren_yukle(Cfg.evren)
    ozet = []

    print("=" * 78, file=sys.stderr)
    print(f"TP %3 | SL %3 | slip yok | baseline=20g gunluk TL | sermaye {SERMAYE:,.0f}",
          file=sys.stderr)
    print("=" * 78, file=sys.stderr)

    # --- Kumulatif 15/30/60 dk ---
    for dk in DAKIKALAR:
        print(f"\n--- Kumulatif {dk} dk taranıyor ---", file=sys.stderr)
        Cfg.min_kat = float(min(KATLAR))
        sinyal, bar_veri = topla_kumulatif(hisseler, Cfg(), dk)
        for mk in KATLAR:
            sub = [s for s in sinyal if s["kat"] >= mk]
            kapali, son = simule_gecikmis(sub, bar_veri, TARGET, STOP, RT, SERMAYE)
            df = pd.DataFrame(kapali)
            if len(df):
                df = df.sort_values(["giris_tarih", "hisse"])
            tag = f"portfoy_kum{dk}_{mk}x.csv"
            df.to_csv(tag, index=False)
            row = ozet_satir(f"kum_{dk}dk", mk, len(sub), df, son)
            ozet.append(row)
            print(f"kum_{dk}dk {mk}x | sinyal={len(sub)} islem={len(df)} "
                  f"son={son:,.0f} getiri={(son/SERMAYE-1)*100:.2f}% win={row['win_%']}%")

    # --- DIP+KIRILIM (acilis hacmi, ayni 4x/5x) ---
    print(f"\n--- DIP+KIRILIM taranıyor ---", file=sys.stderr)
    Cfg.min_kat = 4.0
    dip_sinyal, dip_bar = topla(hisseler, Cfg(), ACILIS_SON)
    for mk in KATLAR:
        sub = [s for s in dip_sinyal if s["grup"] in ("dip", "kirilim") and s["kat"] >= mk]
        kapali, son, _ = simule_open(sub, dip_bar, TARGET, STOP, RT, SERMAYE)
        df = pd.DataFrame(kapali).sort_values(["giris_tarih", "hisse"])
        tag = f"portfoy_dipkir_{mk}x.csv"
        df.to_csv(tag, index=False)
        row = ozet_satir("dip_kirilim", mk, len(sub), df, son)
        ozet.append(row)
        print(f"dip_kirilim {mk}x | sinyal={len(sub)} islem={len(df)} "
              f"son={son:,.0f} getiri={(son/SERMAYE-1)*100:.2f}% "
              f"win={row['win_%']}% dip={row['dip']} kir={row['kirilim']}")

    odf = pd.DataFrame(ozet)
    odf.to_csv("portfoy_erken_dk_ozet.csv", index=False)
    print("\n" + "=" * 78)
    print("OZET KARSILASTIRMA")
    print(odf.to_string(index=False))
    print("\n-> portfoy_erken_dk_ozet.csv")


if __name__ == "__main__":
    main()
