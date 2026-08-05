"""DIP+KIRILIM | TP %5 SL %5 | max tutus: giris gunu + ertesi gun (n+1)."""
from __future__ import annotations
import argparse
import datetime as dt
import sys
from collections import defaultdict

import pandas as pd
from evren import evren_yukle
from portfoy_compound import topla

TARGET = STOP = 0.05
RT = 2 * (0.00009 + 0.000075)
SERMAYE = 100_000


def son_gun_limit(bar_veri, hisse, gt, max_ek=1):
    """gt = giris gunu, max_ek=1 -> en fazla gt ve gt+1 islem gunu."""
    gunler = sorted(bar_veri.get(hisse, {}).keys())
    if gt not in gunler:
        return gt
    i = gunler.index(gt)
    return gunler[min(i + max_ek, len(gunler) - 1)]


def gun_cikis(lows, highs, close, gf, target, stop, basla, son_gun_mu):
    """Tek gun icinde TP/SL; son gun ise kapanis zorunlu."""
    ust, alt = gf * (1 + target), gf * (1 - stop)
    mh = gf
    for k in range(basla, len(highs)):
        hi, lo = float(highs[k]), float(lows[k])
        if hi > mh:
            mh = hi
        hed, stp = hi >= ust, lo <= alt
        if stp and hed:
            return alt, "stop", mh
        if hed:
            return ust, "hedef", mh
        if stp:
            return alt, "stop", mh
    if son_gun_mu:
        return float(close), "sure_doldu", mh
    return None, None, mh


def simule_n1(sinyaller, bar_veri, target, stop, rt, sermaye, max_ek=1):
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
                    "grup": s["grup"], "kat": s["kat"], "pos52": s["pos52"],
                    "mh": s["giris"], "son_gun": son_gun_limit(bar_veri, s["hisse"], D, max_ek),
                })
            cash = 0.0

        yeni = []
        for q in acik:
            if D < q["gt"]:
                yeni.append(q)
                continue
            if D > q["son_gun"]:
                # gecikmis kapanis (veri atlama)
                bd = bar_veri.get(q["hisse"], {}).get(q["son_gun"])
                sc = bd[2] if bd else q["gf"]
                cf, sb, mh = sc, "sure_doldu", q["mh"]
            else:
                bd = bar_veri.get(q["hisse"], {}).get(D)
                if bd is None:
                    yeni.append(q)
                    continue
                lows, highs, close = bd
                basla = 1 if D == q["gt"] else 0
                son_mu = D == q["son_gun"]
                cf, sb, mh = gun_cikis(lows, highs, close, q["gf"], target, stop, basla, son_mu)
                q["mh"] = mh
                if cf is None:
                    yeni.append(q)
                    continue

            brut = cf / q["gf"] - 1
            net = brut - rt
            cash += q["poz"] * (1 + net)
            kapali.append({
                "giris_tarih": q["gt"], "hisse": q["hisse"], "grup": q["grup"],
                "kat": q["kat"], "pos52": q["pos52"], "giris": round(q["gf"], 4),
                "poz_tl": round(q["poz"], 0), "cikis_tarih": D, "cikis": round(cf, 4),
                "sebep": sb, "getiri_%": round(net * 100, 2),
                "tl_kar": round(q["poz"] * net, 0),
                "max_gordugu_%": round((q["mh"] / q["gf"] - 1) * 100, 2),
                "son_gun_limit": q["son_gun"],
                "tutus_gun": (pd.Timestamp(D) - pd.Timestamp(q["gt"])).days,
            })
        acik = yeni

    for q in acik:
        bd = bar_veri.get(q["hisse"], {}).get(q["son_gun"])
        sc = bd[2] if bd else q["gf"]
        net = (sc / q["gf"] - 1) - rt
        cash += q["poz"] * (1 + net)
        kapali.append({
            "giris_tarih": q["gt"], "hisse": q["hisse"], "grup": q["grup"],
            "kat": q["kat"], "pos52": q["pos52"], "giris": round(q["gf"], 4),
            "poz_tl": round(q["poz"], 0), "cikis_tarih": q["son_gun"],
            "cikis": round(sc, 4), "sebep": "sure_doldu", "getiri_%": round(net * 100, 2),
            "tl_kar": round(q["poz"] * net, 0),
            "max_gordugu_%": round((q["mh"] / q["gf"] - 1) * 100, 2),
            "son_gun_limit": q["son_gun"],
            "tutus_gun": (pd.Timestamp(q["son_gun"]) - pd.Timestamp(q["gt"])).days,
        })
    return kapali, cash


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--min_kat", type=float, default=5.0)
    p.add_argument("--grup", default="dip,kirilim")
    p.add_argument("--sermaye", type=float, default=SERMAYE)
    a = p.parse_args()
    gruplar = set(a.grup.split(","))

    class Cfg:
        evren = a.evren
        tv_user = tv_pass = None
        min_kat = a.min_kat
        stop = STOP
        baseline = 20
        hafta52 = 252
        dip_esik = 0.20
        ust_esik = 0.80
        min_ciro = 200_000
        min_bar = 200
        son_gun = 90
        komisyon = 0.00009
        bsmv = 0.000075
        acilis_son = "10:05"

    hh, mm = map(int, Cfg.acilis_son.split(":"))
    acilis = dt.time(hh, mm)
    hisseler = evren_yukle(Cfg.evren)
    print(f"{len(hisseler)} hisse...", file=sys.stderr)
    Cfg.min_kat = 5.0
    sinyaller, bar_veri = topla(hisseler, Cfg(), acilis)

    print("=" * 70)
    print(f"TP %{TARGET*100:.0f} | SL %{STOP*100:.0f} | max tutus giris+1 gun | slip yok")
    print(f"gruplar={a.grup} | sermaye={a.sermaye:,.0f}")
    print("=" * 70)

    results = []
    for mk in [5.0, 8.0]:
        sub = [s for s in sinyaller if s["grup"] in gruplar and s["kat"] >= mk]
        print(f"\nSinyal {int(mk)}x: {len(sub)} (dip={sum(1 for s in sub if s['grup']=='dip')}, "
              f"kirilim={sum(1 for s in sub if s['grup']=='kirilim')})")
        kapali, son = simule_n1(sub, bar_veri, TARGET, STOP, RT, a.sermaye)
        df = pd.DataFrame(kapali).sort_values(["giris_tarih", "hisse"])
        tag = f"portfoy_55_n1_{int(mk)}x.csv"
        df.to_csv(tag, index=False)
        win = (df["getiri_%"] > 0).mean() * 100
        sb = df["sebep"].value_counts().to_dict()
        results.append((mk, son, df, win, sb))
        print(f"\n--- min_kat {int(mk)}x | {len(df)} islem | son={son:,.0f} | "
              f"getiri={(son/a.sermaye-1)*100:.2f}% | win={win:.1f}%")
        print(f"Sebep: {sb}")
        print(df[["giris_tarih", "hisse", "grup", "giris", "cikis_tarih", "sebep",
                  "getiri_%", "tl_kar", "tutus_gun", "max_gordugu_%"]].to_string(index=False))

    print("\n-> portfoy_55_n1_5x.csv / portfoy_55_n1_8x.csv")


if __name__ == "__main__":
    main()
