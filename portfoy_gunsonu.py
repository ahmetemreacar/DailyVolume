"""DIP+KIRILIM | TP/SL yok | giris=acilis, cikis=ayni gun kapanis (n=bugun)."""
from __future__ import annotations
import datetime as dt
import sys
from collections import defaultdict

import pandas as pd
from evren import evren_yukle
from portfoy_compound import topla

RT = 2 * (0.00009 + 0.000075)
SERMAYE = 100_000


def simule_gunsonu(sinyaller, bar_veri, rt, sermaye):
    by_day = defaultdict(list)
    for s in sinyaller:
        by_day[s["tarih"]].append(s)
    gunler = sorted({d for h in bar_veri for d in bar_veri[h]})
    cash = float(sermaye)
    kapali = []

    for D in gunler:
        todays = by_day.get(D, [])
        if not todays or cash <= 1:
            continue
        poz = cash / len(todays)
        gun_toplam = 0.0
        for s in todays:
            h, gt, gf = s["hisse"], D, s["giris"]
            bd = bar_veri.get(h, {}).get(gt)
            if bd is None:
                gun_toplam += poz
                continue
            close = float(bd[2])
            highs = bd[1]
            mh = float(max(highs)) if len(highs) else gf
            brut = close / gf - 1
            net = brut - rt
            donen = poz * (1 + net)
            gun_toplam += donen
            kapali.append({
                "giris_tarih": gt, "cikis_tarih": gt, "hisse": h, "grup": s["grup"],
                "kat": s["kat"], "pos52": s["pos52"], "giris": round(gf, 4),
                "cikis": round(close, 4), "poz_tl": round(poz, 0),
                "sebep": "gun_kapanis", "getiri_%": round(net * 100, 2),
                "tl_kar": round(poz * net, 0),
                "max_gordugu_%": round((mh / gf - 1) * 100, 2),
                "tutus_gun": 0,
            })
        cash = gun_toplam
    return kapali, cash


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
        acilis_son = "10:05"

    hh, mm = map(int, Cfg.acilis_son.split(":"))
    acilis = dt.time(hh, mm)
    hisseler = evren_yukle(Cfg.evren)
    print(f"{len(hisseler)} hisse...", file=sys.stderr)
    sinyaller, bar_veri = topla(hisseler, Cfg(), acilis)
    gruplar = {"dip", "kirilim"}

    print("=" * 72)
    print("TP/SL YOK | giris=acilis open | cikis=ayni gun kapanis | slip yok")
    print(f"sermaye={SERMAYE:,.0f} | DIP+KIRILIM")
    print("=" * 72)

    for mk in [5.0, 8.0]:
        sub = [s for s in sinyaller if s["grup"] in gruplar and s["kat"] >= mk]
        kapali, son = simule_gunsonu(sub, bar_veri, RT, SERMAYE)
        df = pd.DataFrame(kapali).sort_values(["giris_tarih", "hisse"])
        tag = f"portfoy_gunsonu_{int(mk)}x.csv"
        df.to_csv(tag, index=False)
        win = (df["getiri_%"] > 0).mean() * 100 if len(df) else 0
        print(f"\n--- min_kat {int(mk)}x | sinyal={len(sub)} | islem={len(df)} | "
              f"son={son:,.0f} | getiri={(son/SERMAYE-1)*100:.2f}% | win={win:.1f}%")
        print(f"Ort getiri/islem: %{df['getiri_%'].mean():.2f} | "
              f"medyan: %{df['getiri_%'].median():.2f}")
        print(df[["giris_tarih", "hisse", "grup", "giris", "cikis", "getiri_%",
                  "tl_kar", "max_gordugu_%"]].to_string(index=False))
    print("\n-> portfoy_gunsonu_5x.csv / portfoy_gunsonu_8x.csv")


if __name__ == "__main__":
    main()
