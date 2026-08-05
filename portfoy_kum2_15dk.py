"""Kum2 (09+10 saatlik hacim) | giris 11:00 sonrasi ilk 15dk | 5x DIP+KIRILIM %3/%3."""
from __future__ import annotations
import datetime as dt
import sys

import pandas as pd
from evren import evren_yukle
from veri_cache import cek_saatlik, cek_15dk
from portfoy_erken_dk_dipkir import simule_gecikmis
from sinyal_saat import gunluk_kum

BASLANGIC = dt.date(2026, 1, 2)
TARGET = STOP = 0.03
RT = 2 * (0.00009 + 0.000075)
SERMAYE = 100_000
GIRIS_EN_ERKEN = dt.time(11, 0)   # 10:00 saatlik bar kapanisi
N_BAR = 2


def giris_11h(gun: pd.DataFrame):
    """11:00 ve sonrasi ilk 15dk bar."""
    gun = gun.sort_index()
    for i in range(len(gun)):
        if gun.index[i].time() >= GIRIS_EN_ERKEN:
            return i, float(gun.iloc[i]["Open"])
    return None, None


def topla_15dk_kum2(hisseler, p):
    sinyaller = []
    bar_veri = {}
    for i, h in enumerate(hisseler, 1):
        try:
            hourly = cek_saatlik(h, tv_user=p.tv_user, tv_pass=p.tv_pass)
            dk = cek_15dk(h, tv_user=p.tv_user, tv_pass=p.tv_pass)
            if len(hourly) == 0 or len(dk) == 0:
                continue
            d = gunluk_kum(hourly, N_BAR)
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
                entry_idx, giris = giris_11h(gun)
                if entry_idx is None or giris <= 0:
                    continue
                if len(gun) - entry_idx < 4:
                    continue
                if t not in d.index or t not in baseline.index:
                    continue
                if pd.isna(baseline[t]) or pd.isna(hi52[t]) or pd.isna(lo52[t]):
                    continue
                bl = float(baseline[t])
                ov = float(d.loc[t, "ovol"])
                H, L, dk_c = float(hi52[t]), float(lo52[t]), float(dunk[t])
                if bl <= 0 or H <= L:
                    continue
                kat = ov / bl
                if kat < p.min_kat:
                    continue
                if giris * ov < p.min_ciro:
                    continue
                # grup: sinyal anina kadar (11:00) gorulen tepe
                tepe_gorulen = float(gun.iloc[: entry_idx + 1]["High"].max())
                pos52 = (giris - L) / (H - L)
                taze = (dk_c < H) and (tepe_gorulen >= H)
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
                    "entry_idx": entry_idx,
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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--evren", default="evren.csv")
    args = ap.parse_args()

    class Cfg:
        evren = args.evren
        tv_user = tv_pass = None
        min_kat = 5.0
        baseline = 20
        hafta52 = 252
        dip_esik = 0.20
        ust_esik = 0.80
        min_ciro = 200_000
        min_bar = 12
        son_gun = 9999

    hisseler = evren_yukle(Cfg.evren)
    print(f"KUM2 + giris 11:00 | 15dk | {len(hisseler)} hisse...", file=sys.stderr)
    sinyaller, bar_veri = topla_15dk_kum2(hisseler, Cfg())
    dipkir = [s for s in sinyaller if s["grup"] in ("dip", "kirilim") and s["kat"] >= 5]
    kapali, son = simule_gecikmis(dipkir, bar_veri, TARGET, STOP, RT, SERMAYE)
    df = pd.DataFrame(kapali).sort_values(["giris_tarih", "hisse"])
    tag = "kucuk" if "kucuk" in Cfg.evren else "evren"
    csv = f"islemler_kum2_11h_5x_{tag}.csv"
    df.to_csv(csv, index=False)

    win = (df["getiri_%"] > 0).mean() * 100 if len(df) else 0
    sb = df["sebep"].value_counts().to_dict() if len(df) else {}
    print("=" * 72)
    print("KUM2 (09+10 hacim) | GIRIS 11:00+ | 5x DIP+KIRILIM | TP %3 SL %3")
    print("=" * 72)
    print(f"Sinyal: {len(dipkir)} | Islem: {len(df)} | Son: {son:,.0f} TL | "
          f"getiri={(son/SERMAYE-1)*100:.2f}% | win={win:.1f}%")
    print(f"Sebep: {sb}")
    try:
        eski = pd.read_csv(f"islemler_kum2_15dk_5x_{tag}.csv")
        print(f"\nEski (acilis giris, lookahead): {len(eski)} islem, "
              f"~{100_000+eski['tl_kar'].sum():,.0f} TL")
    except Exception:
        pass
    print(f"\n-> {csv}")


if __name__ == "__main__":
    main()
