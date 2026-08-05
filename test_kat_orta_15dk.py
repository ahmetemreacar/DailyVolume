"""15dk acilis | Oca-Haz 2026 | TP %3 SL %3 | 3x/5x x DIP+KIRILIM / +orta."""
from __future__ import annotations
import datetime as dt
import sys

import pandas as pd
from evren import evren_yukle
from portfoy_compound import simule
from portfoy_ocak_15dk import topla_15dk, BASLANGIC

TARGET = STOP = 0.03
RT = 2 * (0.00009 + 0.000075)
SERMAYE = 100_000

SENARYOLAR = [
    ("1_3x_dipkir", 3.0, {"dip", "kirilim"}),
    ("2_3x_dipkir_orta", 3.0, {"dip", "kirilim", "orta"}),
    ("3_5x_dipkir_orta", 5.0, {"dip", "kirilim", "orta"}),
    ("0_5x_dipkir_ref", 5.0, {"dip", "kirilim"}),
]


def ozet_satir(ad, mk, sub, df, son):
    sb = df["sebep"].value_counts().to_dict() if len(df) else {}
    return {
        "senaryo": ad,
        "min_kat": f"{mk}x",
        "gruplar": "+".join(sorted({s["grup"] for s in sub})) if sub else "-",
        "sinyal": len(sub),
        "islem": len(df),
        "son_tl": round(son, 0),
        "getiri_%": round((son / SERMAYE - 1) * 100, 2) if len(df) or sub else 0,
        "win_%": round((df["getiri_%"] > 0).mean() * 100, 1) if len(df) else 0,
        "hedef": sb.get("hedef", 0),
        "stop": sb.get("stop", 0),
        "acik": sb.get("acik_kaldi", 0),
        "dip": (df["grup"] == "dip").sum() if len(df) else 0,
        "kirilim": (df["grup"] == "kirilim").sum() if len(df) else 0,
        "orta": (df["grup"] == "orta").sum() if len(df) else 0,
    }


def main():
    class Cfg:
        evren = "evren.csv"
        tv_user = tv_pass = None
        min_kat = 2.0
        baseline = 20
        hafta52 = 252
        dip_esik = 0.20
        ust_esik = 0.80
        min_ciro = 200_000
        min_bar = 12
        son_gun = 9999

    hisseler = evren_yukle(Cfg.evren)
    print(f"15dk tarama | {len(hisseler)} hisse | {BASLANGIC}+ ...", file=sys.stderr)
    tum, bar_veri = topla_15dk(hisseler, Cfg())
    tum = [s for s in tum if dt.date.fromisoformat(s["tarih"]) >= BASLANGIC]

    if not tum:
        print("Sinyal yok.")
        return

    tarihler = sorted({s["tarih"] for s in tum})
    print("=" * 80)
    print(f"15DK ACILIS | TP %3 SL %3 | compound | slip yok | {Cfg.evren}")
    print(f"Veri araligi: {tarihler[0]} -> {tarihler[-1]} | toplam sinyal (tum gruplar): {len(tum)}")
    print("=" * 80)

    ozet = []
    for ad, mk, gruplar in SENARYOLAR:
        sub = [s for s in tum if s["kat"] >= mk and s["grup"] in gruplar]
        kapali, son, _ = simule(sub, bar_veri, TARGET, STOP, RT, SERMAYE)
        df = pd.DataFrame(kapali).sort_values(["giris_tarih", "hisse"]) if kapali else pd.DataFrame()
        tag = f"test_15dk_{ad}.csv"
        if len(df):
            df.to_csv(tag, index=False)
        row = ozet_satir(ad, mk, sub, df, son)
        ozet.append(row)
        print(f"\n{ad} | kat>={mk}x | {gruplar}")
        print(f"  sinyal={row['sinyal']} islem={row['islem']} son={row['son_tl']:,.0f} TL "
              f"getiri={row['getiri_%']}% win={row['win_%']}% "
              f"hedef={row['hedef']} stop={row['stop']} | dip={row['dip']} kir={row['kirilim']} orta={row['orta']}")

    odf = pd.DataFrame(ozet)
    odf.to_csv("test_kat_orta_15dk_ozet.csv", index=False)
    print("\n" + "=" * 80)
    print(odf.to_string(index=False))
    print("\n-> test_kat_orta_15dk_ozet.csv")


if __name__ == "__main__":
    main()
