"""Dinamik 5x — 5 iyilestirme testi."""
from __future__ import annotations
import sys
from collections import defaultdict

import pandas as pd
from evren import evren_yukle
from portfoy_dinamik_kat import topla_dinamik, BASLANGIC
from portfoy_erken_dk_dipkir import simule_gecikmis

SERMAYE = 100_000
RT = 2 * (0.00009 + 0.000075)
STOP = 0.03
MIN_KAT = 5.0


def _bd(bar_veri, hisse, gun):
    return bar_veri.get(hisse, {}).get(gun)


def sec_max_kat(sinyaller):
    gun = {}
    for s in sinyaller:
        t = s["tarih"]
        if t not in gun or s["kat"] > gun[t]["kat"]:
            gun[t] = s
        elif s["kat"] == gun[t]["kat"] and s["hisse"] < gun[t]["hisse"]:
            gun[t] = s
    return list(gun.values())


def filtre_chase(sinyaller, max_pct=0.03):
    out = []
    for s in sinyaller:
        ag = s.get("acilis_gun") or s["giris"]
        if ag <= 0:
            continue
        if s["giris"] / ag > 1 + max_pct:
            continue
        out.append(s)
    return out


def hedef_kat(kat: float) -> float:
  if kat < 8:
      return 0.03
  return 0.05


def simule_compound(sinyaller, bar_veri, target=0.03, stop=STOP, wick_safe=False,
                    hedef_fn=None):
    by_day = defaultdict(list)
    for s in sinyaller:
        by_day[s["tarih"]].append(s)
    gunler = sorted({d for h in bar_veri for d in bar_veri[h]})
    cash = float(SERMAYE)
    acik = []
    kapali = []

    for D in gunler:
        todays = by_day.get(D, [])
        if todays and cash > 1:
            poz = cash / len(todays)
            for s in todays:
                tg = hedef_fn(s["kat"]) if hedef_fn else target
                acik.append({**s, "gf": s["giris"], "gt": D, "poz": poz,
                             "mh": s["giris"], "target": tg})
            cash = 0.0

        yeni = []
        for q in acik:
            bd = _bd(bar_veri, q["hisse"], D)
            if bd is None:
                yeni.append(q)
                continue
            lows, highs = bd[0], bd[1]
            closes = bd[2] if len(bd) > 3 else None
            ust = q["gf"] * (1 + q["target"])
            alt = q["gf"] * (1 - stop)
            basla = (q["entry_idx"] + 1) if D == q["gt"] else 0
            cikti = cf = sb = None
            for k in range(basla, len(highs)):
                hi, lo = float(highs[k]), float(lows[k])
                cl = float(closes[k]) if closes is not None else lo
                if hi > q["mh"]:
                    q["mh"] = hi
                hed = hi >= ust
                stp = (cl <= alt) if wick_safe else (lo <= alt)
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
                net = cf / q["gf"] - 1 - RT
                cash += q["poz"] * (1 + net)
                kapali.append(_row(q, D, cf, sb, net))
            else:
                yeni.append(q)
        acik = yeni

    for q in acik:
        bd = _bd(bar_veri, q["hisse"], q["gt"])
        sc = bd[3] if bd and len(bd) > 3 else q["gf"]
        gunlist = sorted(bar_veri.get(q["hisse"], {}).keys())
        sonD = [g for g in gunlist if g >= q["gt"]]
        if sonD and bd:
            sc = _bd(bar_veri, q["hisse"], sonD[-1])[3]
        net = sc / q["gf"] - 1 - RT
        cash += q["poz"] * (1 + net)
        kapali.append(_row(q, sonD[-1] if sonD else q["gt"], sc, "acik_kaldi", net))
    return kapali, cash


def simule_sabit(sinyaller, bar_veri, target=0.03, stop=STOP, wick_safe=False,
                 hedef_fn=None):
    kapali = []
    for s in sinyaller:
        D = s["tarih"]
        gf = s["giris"]
        tg = hedef_fn(s["kat"]) if hedef_fn else target
        bd_days = sorted(bar_veri.get(s["hisse"], {}).keys())
        days = [d for d in bd_days if d >= D]
        cikti = False
        mh = gf
        for day in days:
            bd = _bd(bar_veri, s["hisse"], day)
            if bd is None:
                continue
            lows, highs = bd[0], bd[1]
            closes = bd[2] if len(bd) > 3 else None
            ust, alt = gf * (1 + tg), gf * (1 - stop)
            basla = (s["entry_idx"] + 1) if day == D else 0
            for k in range(basla, len(highs)):
                hi, lo = float(highs[k]), float(lows[k])
                cl = float(closes[k]) if closes is not None else lo
                mh = max(mh, hi)
                hed = hi >= ust
                stp = (cl <= alt) if wick_safe else (lo <= alt)
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
                break
        if not cikti:
            sc = _bd(bar_veri, s["hisse"], days[-1])[3]
            cf, sb = sc, "acik_kaldi"
        net = cf / gf - 1 - RT
        kapali.append(_row({**s, "gf": gf, "poz": SERMAYE}, days[-1] if days else D,
                           cf, sb, net))
    toplam = SERMAYE + sum(r["tl_kar"] for r in kapali)
    return kapali, toplam


def _row(q, D, cf, sb, net):
    return {
        "giris_tarih": q.get("gt", q["tarih"]), "hisse": q["hisse"],
        "grup": q.get("grup", ""), "kat": q["kat"], "pos52": q.get("pos52"),
        "giris": round(q["gf"] if "gf" in q else q["giris"], 4),
        "poz_tl": round(q["poz"], 0), "cikis_tarih": D, "cikis": round(cf, 4),
        "sebep": sb, "getiri_%": round(net * 100, 2),
        "tl_kar": round(q["poz"] * net, 0),
    }


def _ozet(ad, sinyal, kapali, son):
    df = pd.DataFrame(kapali)
    win = (df["getiri_%"] > 0).mean() * 100 if len(df) else 0
    sb = df["sebep"].value_counts().to_dict() if len(df) else {}
    return {
        "test": ad, "sinyal": len(sinyal), "islem": len(df),
        "son_tl": round(son, 0), "getiri_%": round((son / SERMAYE - 1) * 100, 2),
        "win_%": round(win, 1), "hedef": sb.get("hedef", 0), "stop": sb.get("stop", 0),
    }


def main():
    class Cfg:
        evren = "evren.csv"
        tv_user = tv_pass = None
        baseline = 20
        hafta52 = 252
        dip_esik = 0.20
        ust_esik = 0.80
        min_ciro = 200_000

    hisseler = evren_yukle(Cfg.evren)
    print(f"Sinyaller toplaniyor (5x)...", file=sys.stderr)
    bl_cache = {}
    tum, bar_veri = topla_dinamik(hisseler, Cfg(), MIN_KAT, bl_cache)
    dipkir = [s for s in tum if s["grup"] in ("dip", "kirilim")]
    baz_k, baz_s = simule_compound(dipkir, bar_veri)
    baz_o = _ozet("0_baz_5x_compound", dipkir, baz_k, baz_s)

    sonuclar = [baz_o]

    # 1) Max-kat compound + sabit
    mk = sec_max_kat(dipkir)
    k1, s1 = simule_compound(mk, bar_veri)
    sonuclar.append(_ozet("1_maxkat_compound", mk, k1, s1))
    k1b, s1b = simule_sabit(mk, bar_veri)
    sonuclar.append(_ozet("1b_maxkat_sabit100k", mk, k1b, s1b))

    # 2) Chase filtresi +%3
    ch = filtre_chase(dipkir, 0.03)
    k2, s2 = simule_compound(ch, bar_veri)
    sonuclar.append(_ozet("2_chase_max3pct", ch, k2, s2))

    # 3) DIP only / KIRILIM only
    dip = [s for s in dipkir if s["grup"] == "dip"]
    kir = [s for s in dipkir if s["grup"] == "kirilim"]
    k3a, s3a = simule_compound(dip, bar_veri)
    k3b, s3b = simule_compound(kir, bar_veri)
    sonuclar.append(_ozet("3a_dip_only", dip, k3a, s3a))
    sonuclar.append(_ozet("3b_kirilim_only", kir, k3b, s3b))

    # 4) Kat kovasi hedef: 5-8x %3, 8x+ %5
    k4, s4 = simule_compound(dipkir, bar_veri, hedef_fn=hedef_kat)
    sonuclar.append(_ozet("4_kat_hedef_3_5", dipkir, k4, s4))

    # 5) Wick-safe stop (15dk kapanis)
    k5, s5 = simule_compound(dipkir, bar_veri, wick_safe=True)
    sonuclar.append(_ozet("5_wick_safe_stop", dipkir, k5, s5))

    odf = pd.DataFrame(sonuclar)
    odf.to_csv("dinamik_5test_ozet.csv", index=False)

    print("=" * 78)
    print("DINAMIK 5x — 5 IYILESTIRME TESTI | TP %3 SL %3 (4: kat bazli hedef)")
    print("=" * 78)
    print(odf.to_string(index=False))
    print("\n-> dinamik_5test_ozet.csv")


if __name__ == "__main__":
    main()
