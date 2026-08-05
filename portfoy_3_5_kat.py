"""DIP+KIRILIM | TP %3 SL %5 | min_kat 2/3/4/5/8 karsilastirma."""
from __future__ import annotations
import datetime as dt
import sys

import pandas as pd
from evren import evren_yukle
from portfoy_compound import topla, simule

TARGET, STOP = 0.03, 0.05
RT = 2 * (0.00009 + 0.000075)
SERMAYE = 100_000
KATLAR = [2, 3, 4, 5, 8]


def main():
    class Cfg:
        evren = "evren_kucuk.csv"
        tv_user = tv_pass = None
        min_kat = 2.0
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
    print(f"{len(hisseler)} hisse taranıyor (min_kat>=2)...", file=sys.stderr)
    sinyaller, bar_veri = topla(hisseler, Cfg(), acilis)
    gruplar = {"dip", "kirilim"}

    ozet = []
    print("=" * 78)
    print(f"TP %{TARGET*100:.0f} | SL %{STOP*100:.0f} | DIP+KIRILIM | slip yok | sermaye {SERMAYE:,.0f}")
    print("=" * 78)

    for mk in KATLAR:
        sub = [s for s in sinyaller if s["grup"] in gruplar and s["kat"] >= mk]
        kapali, son, _ = simule(sub, bar_veri, TARGET, STOP, RT, SERMAYE)
        df = pd.DataFrame(kapali).sort_values(["giris_tarih", "hisse"])
        df.to_csv(f"portfoy_35_{mk}x.csv", index=False)
        win = (df["getiri_%"] > 0).mean() * 100 if len(df) else 0
        sb = df["sebep"].value_counts().to_dict() if len(df) else {}
        dip_n = (df["grup"] == "dip").sum() if len(df) else 0
        kir_n = (df["grup"] == "kirilim").sum() if len(df) else 0
        ozet.append({
            "min_kat": f"{mk}x",
            "sinyal": len(sub),
            "islem": len(df),
            "son_tl": round(son, 0),
            "getiri_%": round((son / SERMAYE - 1) * 100, 2),
            "win_%": round(win, 1),
            "hedef": sb.get("hedef", 0),
            "stop": sb.get("stop", 0),
            "acik_kaldi": sb.get("acik_kaldi", 0),
            "dip": dip_n,
            "kirilim": kir_n,
        })
        print(f"\n{'='*78}")
        print(f"min_kat {mk}x | sinyal={len(sub)} | islem={len(df)} | "
              f"son={son:,.0f} TL | getiri={(son/SERMAYE-1)*100:.2f}% | win={win:.1f}%")
        print(f"Sebep: {sb}")
        if len(df):
            print(df[["giris_tarih", "hisse", "grup", "kat", "giris", "cikis_tarih",
                      "sebep", "getiri_%", "tl_kar", "max_gordugu_%"]].to_string(index=False))

    odf = pd.DataFrame(ozet)
    odf.to_csv("portfoy_35_ozet.csv", index=False)
    print(f"\n{'='*78}")
    print("KARSILASTIRMA OZETI")
    print(odf.to_string(index=False))
    print("\n-> portfoy_35_2x.csv ... portfoy_35_8x.csv | portfoy_35_ozet.csv")


if __name__ == "__main__":
    main()
