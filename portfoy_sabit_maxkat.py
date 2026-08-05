"""Sabit 100k + ayni gunde sadece en yuksek kat'li hisse (5x DIP+KIRILIM %3/%3)."""
from __future__ import annotations
import datetime as dt
import sys
from collections import defaultdict

import pandas as pd
from evren import evren_yukle
from portfoy_compound import topla, simule

SERMAYE = 100_000
TARGET = STOP = 0.03
RT = 2 * (0.00009 + 0.000075)


def sec_max_kat(sinyaller, min_kat: float, gruplar: set[str]):
    gunler = {}
    for s in sinyaller:
        if s["grup"] not in gruplar or s["kat"] < min_kat:
            continue
        t = s["tarih"]
        if t not in gunler or s["kat"] > gunler[t]["kat"]:
            gunler[t] = s
        elif s["kat"] == gunler[t]["kat"] and s["hisse"] < gunler[t]["hisse"]:
            gunler[t] = s
    return sorted(gunler.values(), key=lambda x: x["tarih"])


def simule_sabit_gunluk(secilen, bar_veri, target, stop, rt, sermaye):
    """Her gun tek secim, sabit sermaye; islemler bagimsiz (nakit blokaji yok)."""
    kapali = []
    for s in secilen:
        D = s["tarih"]
        bd0 = bar_veri.get(s["hisse"], {}).get(D)
        if bd0 is None:
            continue
        lows, highs, _ = bd0
        gf = s["giris"]
        ust, alt = gf * (1 + target), gf * (1 - stop)
        mh = gf
        cikti = False
        cf = sb = None
        cikis_gun = D
        for gun in sorted(bar_veri.get(s["hisse"], {})):
            if gun < D:
                continue
            bd = bar_veri[s["hisse"]][gun]
            lows, highs, close = bd
            basla = 1 if gun == D else 0
            for k in range(basla, len(highs)):
                hi = float(highs[k])
                lo = float(lows[k])
                if hi > mh:
                    mh = hi
                hed = hi >= ust
                stp = lo <= alt
                if stp and hed:
                    cf, sb, cikti, cikis_gun = alt, "stop", True, gun
                    break
                if hed:
                    cf, sb, cikti, cikis_gun = ust, "hedef", True, gun
                    break
                if stp:
                    cf, sb, cikti, cikis_gun = alt, "stop", True, gun
                    break
            if cikti:
                break
        if not cikti:
            son_gun = max(g for g in bar_veri[s["hisse"]] if g >= D)
            cf = bar_veri[s["hisse"]][son_gun][2]
            sb = "acik_kaldi"
            cikis_gun = son_gun
        net = cf / gf - 1 - rt
        kapali.append({
            "giris_tarih": D, "hisse": s["hisse"], "grup": s["grup"],
            "kat": s["kat"], "pos52": s["pos52"], "giris": round(gf, 4),
            "poz_tl": sermaye, "cikis_tarih": cikis_gun, "cikis": round(cf, 4),
            "sebep": sb, "getiri_%": round(net * 100, 2),
            "tl_kar": round(sermaye * net, 0),
            "max_gordugu_%": round((mh / gf - 1) * 100, 2),
        })
    toplam_kar = sum(r["tl_kar"] for r in kapali)
    return kapali, sermaye + toplam_kar


def main():
    class Cfg:
        evren = "evren_kucuk.csv"
        tv_user = tv_pass = None
        min_kat = 5.0
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

    hh, mm = map(int, Cfg.acilis_son.split(":"))
    acilis = dt.time(hh, mm)
    gruplar = {"dip", "kirilim"}

    hisseler = evren_yukle(Cfg.evren)
    print(f"{len(hisseler)} hisse...", file=sys.stderr)
    tum_sinyal, bar_veri = topla(hisseler, Cfg(), acilis)
    tum_dip = [s for s in tum_sinyal if s["grup"] in gruplar and s["kat"] >= 5]
    secilen = sec_max_kat(tum_sinyal, 5.0, gruplar)

    kapali, son = simule_sabit_gunluk(secilen, bar_veri, TARGET, STOP, RT, SERMAYE)
    df = pd.DataFrame(kapali)
    df.to_csv("portfoy_sabit_maxkat_5x.csv", index=False)

    _, son_comp, _ = simule(tum_dip, bar_veri, TARGET, STOP, RT, SERMAYE)

    win = (df["getiri_%"] > 0).mean() * 100 if len(df) else 0
    sb = df["sebep"].value_counts().to_dict() if len(df) else {}

    print("=" * 72)
    print("SABIT 100k + EN YUKSEK KAT | 5x DIP+KIRILIM | TP %3 SL %3")
    print("=" * 72)
    print(f"Islem: {len(df)} gun | atlanan sinyal: {len(tum_dip) - len(df)}")
    print(f"Son: {son:,.0f} TL | getiri: {(son/SERMAYE-1)*100:.2f}% | win: {win:.1f}%")
    print(f"Sebep: {sb}")
    print("-" * 72)
    print(f"Compound (tum 29):     118,833 TL (+18.83%)")
    print(f"Sabit 100k (tum 29):   134,690 TL (+34.69%)")
    print(f"Sabit max-kat ({len(df)}): {son:,.0f} TL ({(son/SERMAYE-1)*100:.2f}%)")
    print("-" * 72)
    print(df[["giris_tarih", "hisse", "grup", "kat", "sebep", "getiri_%", "tl_kar"]].to_string(index=False))
    print("\n-> portfoy_sabit_maxkat_5x.csv")


if __name__ == "__main__":
    main()
