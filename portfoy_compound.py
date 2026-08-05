from __future__ import annotations
import argparse, sys, datetime as dt
from collections import defaultdict
import numpy as np
import pandas as pd
from veri_cache import cek_saatlik, cek_1dk
from evren import evren_yukle

KURALLAR = [("1", 0.01), ("2", 0.02), ("3", 0.03), ("5", 0.05)]


def gunluk(df):
    g = df.sort_index().copy(); g["_t"] = g.index.date
    return g.groupby("_t").agg(Open=("Open", "first"), High=("High", "max"),
                               Low=("Low", "min"), Close=("Close", "last"), ovol=("Volume", "first"))


def topla(hisseler, p, acilis_son):
    sinyaller = []; bar_veri = {}
    for i, h in enumerate(hisseler, 1):
        try:
            hourly = cek_saatlik(h, tv_user=p.tv_user, tv_pass=p.tv_pass, sessiz=True)
            dk1 = cek_1dk(h, tv_user=p.tv_user, tv_pass=p.tv_pass)
            if len(hourly) == 0 or len(dk1) == 0:
                continue
            d = gunluk(hourly)
            if len(d) < p.hafta52 + 5:
                continue
            baseline = d["ovol"].rolling(p.baseline, min_periods=p.baseline).mean().shift(1)
            hi52 = d["High"].rolling(p.hafta52, min_periods=p.hafta52 // 2).max().shift(1)
            lo52 = d["Low"].rolling(p.hafta52, min_periods=p.hafta52 // 2).min().shift(1)
            dunk = d["Close"].shift(1)
            gm = dk1.sort_index().copy(); gm["_t"] = gm.index.date
            by_day = {t: g.sort_index() for t, g in gm.groupby("_t")}
            en_yeni = max(by_day.keys())
            h_sinyal = []
            for t in sorted(by_day.keys()):
                gun = by_day[t]
                if len(gun) < p.min_bar or (en_yeni - t).days > p.son_gun:
                    continue
                if gun.index[0].time() > acilis_son:
                    continue
                if t not in baseline.index or pd.isna(baseline[t]) or pd.isna(hi52[t]) or pd.isna(lo52[t]):
                    continue
                bl = float(baseline[t]); ov = float(d.loc[t, "ovol"])
                H, L, dk = float(hi52[t]), float(lo52[t]), float(dunk[t])
                if bl <= 0 or H <= L:
                    continue
                kat = ov / bl
                if kat < p.min_kat:
                    continue
                giris = float(gun.iloc[0]["Open"])
                if giris <= 0 or giris * ov < p.min_ciro:
                    continue
                pos52 = (giris - L) / (H - L)
                gy = float(gun["High"].max())
                taze = (dk < H) and (gy >= H)
                if pos52 <= p.dip_esik:
                    grup = "dip"
                elif taze:
                    grup = "kirilim"
                elif pos52 >= p.ust_esik:
                    grup = "tepe"
                else:
                    grup = "orta"
                h_sinyal.append({"tarih": str(t), "hisse": h, "grup": grup,
                                 "kat": round(kat, 1), "pos52": round(pos52, 3), "giris": giris})
            if h_sinyal:
                sinyaller.extend(h_sinyal)
                ilk = min(s["tarih"] for s in h_sinyal)
                bd = {}
                for t, g in by_day.items():
                    if str(t) >= ilk:
                        bd[str(t)] = (g["Low"].values.astype("float32"),
                                      g["High"].values.astype("float32"),
                                      float(g.iloc[-1]["Close"]))
                bar_veri[h] = bd
            print(f"  [{i}/{len(hisseler)}] {h} ({len(h_sinyal)} sinyal)", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)
    return sinyaller, bar_veri


def simule(sinyaller, bar_veri, target, stop, rt, sermaye):
    by_day = defaultdict(list)
    for s in sinyaller:
        by_day[s["tarih"]].append(s)
    gunler = sorted({d for h in bar_veri for d in bar_veri[h]})
    cash = float(sermaye); acik = []; kapali = []; equity = []
    for D in gunler:
        todays = by_day.get(D, [])
        if todays and cash > 1:
            n = len(todays); poz = cash / n
            for s in todays:
                acik.append({"hisse": s["hisse"], "gt": D, "gf": s["giris"], "poz": poz,
                             "grup": s["grup"], "kat": s["kat"], "pos52": s["pos52"], "mh": s["giris"]})
            cash = 0.0
        yeni = []
        for q in acik:
            bd = bar_veri.get(q["hisse"], {}).get(D)
            if bd is None:
                yeni.append(q); continue
            lows, highs, _ = bd
            ust = q["gf"] * (1 + target); alt = q["gf"] * (1 - stop)
            basla = 1 if D == q["gt"] else 0
            cikti = False; cf = None; sb = None
            for k in range(basla, len(highs)):
                hi = float(highs[k]); lo = float(lows[k])
                if hi > q["mh"]:
                    q["mh"] = hi
                hed = hi >= ust; stp = lo <= alt
                if stp and hed:
                    cf, sb = alt, "stop"; cikti = True; break
                if hed:
                    cf, sb = ust, "hedef"; cikti = True; break
                if stp:
                    cf, sb = alt, "stop"; cikti = True; break
            if cikti:
                brut = cf / q["gf"] - 1; net = brut - rt
                cash += q["poz"] * (1 + net)
                kapali.append({"giris_tarih": q["gt"], "hisse": q["hisse"], "grup": q["grup"],
                               "kat": q["kat"], "pos52": q["pos52"], "giris": round(q["gf"], 4),
                               "poz_tl": round(q["poz"], 0), "cikis_tarih": D, "cikis": round(cf, 4),
                               "sebep": sb, "getiri_%": round(net * 100, 2),
                               "tl_kar": round(q["poz"] * net, 0),
                               "max_gordugu_%": round((q["mh"] / q["gf"] - 1) * 100, 2)})
            else:
                yeni.append(q)
        acik = yeni
        deger = cash
        for q in acik:
            bd = bar_veri.get(q["hisse"], {}).get(D)
            sc = bd[2] if bd else q["gf"]
            deger += q["poz"] * (sc / q["gf"])
        equity.append((D, round(deger, 0)))
    for q in acik:
        gunlist = sorted(bar_veri.get(q["hisse"], {}).keys())
        sonD = [g for g in gunlist if g >= q["gt"]]
        sc = bar_veri[q["hisse"]][sonD[-1]][2] if sonD else q["gf"]
        net = (sc / q["gf"] - 1) - rt
        cash += q["poz"] * (1 + net)
        kapali.append({"giris_tarih": q["gt"], "hisse": q["hisse"], "grup": q["grup"],
                       "kat": q["kat"], "pos52": q["pos52"], "giris": round(q["gf"], 4),
                       "poz_tl": round(q["poz"], 0), "cikis_tarih": sonD[-1] if sonD else q["gt"],
                       "cikis": round(sc, 4), "sebep": "acik_kaldi", "getiri_%": round(net * 100, 2),
                       "tl_kar": round(q["poz"] * net, 0),
                       "max_gordugu_%": round((q["mh"] / q["gf"] - 1) * 100, 2)})
    return kapali, cash, equity


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--tv_user", default=None); p.add_argument("--tv_pass", default=None)
    p.add_argument("--sermaye", type=float, default=100_000)
    p.add_argument("--min_kat", type=float, default=8.0)
    p.add_argument("--stop", type=float, default=0.03)
    p.add_argument("--baseline", type=int, default=20)
    p.add_argument("--hafta52", type=int, default=252)
    p.add_argument("--dip_esik", type=float, default=0.20)
    p.add_argument("--ust_esik", type=float, default=0.80)
    p.add_argument("--min_ciro", type=float, default=200_000)
    p.add_argument("--min_bar", type=int, default=200)
    p.add_argument("--son_gun", type=int, default=90)
    p.add_argument("--komisyon", type=float, default=0.00009)
    p.add_argument("--bsmv", type=float, default=0.000075)
    p.add_argument("--slippage", type=float, default=0.003)
    p.add_argument("--acilis_son", default="10:05")
    a = p.parse_args()
    hh, mm = map(int, a.acilis_son.split(":")); acilis_son = dt.time(hh, mm)
    rt = 2 * (a.komisyon + a.bsmv + a.slippage)

    hisseler = evren_yukle(a.evren)
    print(f"{len(hisseler)} hisse taraniyor...", file=sys.stderr)
    sinyaller, bar_veri = topla(hisseler, a, acilis_son)
    if not sinyaller:
        print("Sinyal yok."); return
    tarihler = sorted({s["tarih"] for s in sinyaller})
    print("=" * 70)
    print(f"COMPOUND PORTFOY | sermaye {a.sermaye:,.0f} | all-in | cok-gunlu | maliyet cift-yon=%{rt*100:.3f}")
    print(f"Toplam sinyal: {len(sinyaller)} | {tarihler[0]} -> {tarihler[-1]}")
    grup_say = pd.Series([s['grup'] for s in sinyaller]).value_counts().to_dict()
    print(f"Grup dagilimi: {grup_say}")
    print("=" * 70)
    print(f"{'KURAL':>6} {'son_portfoy':>14} {'getiri_%':>9} {'islem':>6} {'win_%':>7} {'acik_kaldi':>11}")
    for ad, hedef in KURALLAR:
        kapali, son_cash, equity = simule(sinyaller, bar_veri, hedef, a.stop, rt, a.sermaye)
        df = pd.DataFrame(kapali).sort_values(["giris_tarih", "hisse"])
        df.to_csv(f"portfoy_{ad}.csv", index=False)
        win = (df["getiri_%"] > 0).mean() * 100
        ak = (df["sebep"] == "acik_kaldi").sum()
        print(f"{ad:>6} {son_cash:>14,.0f} {(son_cash/a.sermaye-1)*100:>8.2f}% {len(df):>6} {win:>6.1f}% {ak:>11}")
    print("-" * 70)
    print("-> portfoy_1.csv / _2 / _3 / _5.csv")


if __name__ == "__main__":
    main()
