"""2 Ocak 2026 -> bugun | 15dk bar | 5x DIP+KIRILIM | TP %3 SL %3."""
from __future__ import annotations
import datetime as dt
import sys
from collections import defaultdict

import pandas as pd
from evren import evren_yukle
from veri_cache import cek_saatlik, cek_15dk
from portfoy_compound import gunluk, simule

BASLANGIC = dt.date(2026, 1, 2)
TARGET = STOP = 0.03
RT = 2 * (0.00009 + 0.000075)
SERMAYE = 100_000
ACILIS_SON = dt.time(10, 5)


def topla_15dk(hisseler, p):
    sinyaller = []
    bar_veri = {}
    for i, h in enumerate(hisseler, 1):
        try:
            hourly = cek_saatlik(h, tv_user=p.tv_user, tv_pass=p.tv_pass)
            dk = cek_15dk(h, tv_user=p.tv_user, tv_pass=p.tv_pass)
            if len(hourly) == 0 or len(dk) == 0:
                continue
            d = gunluk(hourly)
            if len(d) < p.hafta52 + 5:
                continue
            baseline = d["ovol"].rolling(p.baseline, min_periods=p.baseline).mean().shift(1)
            hi52 = d["High"].rolling(p.hafta52, min_periods=p.hafta52 // 2).max().shift(1)
            lo52 = d["Low"].rolling(p.hafta52, min_periods=p.hafta52 // 2).min().shift(1)
            dunk = d["Close"].shift(1)
            gm = dk.sort_index().copy()
            gm["_t"] = gm.index.date
            by_day = {t: g.sort_index() for t, g in gm.groupby("_t")}
            h_sinyal = []
            for t in sorted(by_day.keys()):
                if t < BASLANGIC:
                    continue
                gun = by_day[t]
                if len(gun) < p.min_bar:
                    continue
                if gun.index[0].time() > ACILIS_SON:
                    continue
                if t not in baseline.index or pd.isna(baseline[t]) or pd.isna(hi52[t]) or pd.isna(lo52[t]):
                    continue
                bl = float(baseline[t])
                ov = float(d.loc[t, "ovol"]) if t in d.index else float("nan")
                if t not in d.index:
                    continue
                ov = float(d.loc[t, "ovol"])
                H, L, dk_c = float(hi52[t]), float(lo52[t]), float(dunk[t])
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
                taze = (dk_c < H) and (gy >= H)
                if pos52 <= p.dip_esik:
                    grup = "dip"
                elif taze:
                    grup = "kirilim"
                elif pos52 >= p.ust_esik:
                    grup = "tepe"
                else:
                    grup = "orta"
                h_sinyal.append({
                    "tarih": str(t), "hisse": h, "grup": grup,
                    "kat": round(kat, 1), "pos52": round(pos52, 3), "giris": giris,
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
            print(f"  [{i}/{len(hisseler)}] {h}: {len(h_sinyal)}", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)
    return sinyaller, bar_veri


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
        min_bar = 12
        son_gun = 9999
        komisyon = 0.00009
        bsmv = 0.000075

    hisseler = evren_yukle(Cfg.evren)
    print(f"15dk | {BASLANGIC} -> bugun | {len(hisseler)} hisse...", file=sys.stderr)
    sinyaller, bar_veri = topla_15dk(hisseler, Cfg())
    dipkir = [s for s in sinyaller if s["grup"] in ("dip", "kirilim") and s["kat"] >= 5]
    kapali, son, _ = simule(dipkir, bar_veri, TARGET, STOP, RT, SERMAYE)
    df = pd.DataFrame(kapali).sort_values(["giris_tarih", "hisse"])
    df["gun_sayisi"] = (pd.to_datetime(df["cikis_tarih"]) - pd.to_datetime(df["giris_tarih"])).dt.days
    df.to_csv("islemler_ocak_15dk_5x.csv", index=False)

    win = (df["getiri_%"] > 0).mean() * 100 if len(df) else 0
    sb = df["sebep"].value_counts().to_dict() if len(df) else {}
    print("=" * 72)
    print(f"15dk BAR | 2-Oca-2026 -> bugun | 5x DIP+KIRILIM | TP %3 SL %3 | compound")
    print("=" * 72)
    print(f"Sinyal: {len(dipkir)} | Islem: {len(df)} | Son: {son:,.0f} TL | "
          f"getiri={(son/SERMAYE-1)*100:.2f}% | win={win:.1f}%")
    print(f"Sebep: {sb}")
    print("-" * 72)
    if len(df):
        print(df[["giris_tarih", "hisse", "grup", "kat", "pos52", "giris", "poz_tl",
                  "cikis_tarih", "sebep", "getiri_%", "tl_kar", "max_gordugu_%", "gun_sayisi"]].to_string(index=False))
    print("\n-> islemler_ocak_15dk_5x.csv")


if __name__ == "__main__":
    main()
