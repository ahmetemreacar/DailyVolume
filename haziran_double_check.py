"""Haziran DIP+KIRILIM: bagimsiz double-check — her satir yeniden hesaplanir."""
from __future__ import annotations

import sys
from collections import defaultdict

import numpy as np
import pandas as pd

from portfoy_compound import gunluk
from simule_intraday import simule_gun, seans_filtre
from veri_cache import cek_saatlik, cek_1dk, cek_15dk

TARGET = STOP = 0.03
RT = 2 * (0.00009 + 0.000075)
SERMAYE = 100_000
TOL_CIKIS = 0.02  # TL
TOL_GETIRI = 0.02  # % puan


def _bars_by_day(df):
    if len(df) == 0:
        return {}
    gm = df.sort_index()
    gm["_t"] = gm.index.date
    return {t: g.sort_index() for t, g in gm.groupby("_t")}


def gun_bars(hisse: str, tarih: str):
    gun_dt = pd.Timestamp(tarih).date()
    for label, fn in [("1dk", cek_1dk), ("15dk", cek_15dk)]:
        df = fn(hisse)
        by = _bars_by_day(df)
        if gun_dt in by:
            return label, by[gun_dt]
    return None, None


def saatlik_acilis(hisse: str, tarih: str) -> float | None:
    h = cek_saatlik(hisse)
    if len(h) == 0:
        return None
    d = gunluk(h)
    t = pd.Timestamp(tarih).date()
    if t not in d.index:
        return None
    return float(d.loc[t, "Open"])


def mfe_mae(gun, giris):
    g = seans_filtre(gun)
    if len(g) == 0:
        g = gun.sort_index()
    mh, ml = float(g["High"].max()), float(g["Low"].min())
    max_saat, min_saat = "", ""
    for i in range(len(g)):
        hi, lo = float(g.iloc[i].High), float(g.iloc[i].Low)
        ts = str(g.index[i])[11:16]
        if hi >= mh - 1e-9:
            max_saat = ts
        if lo <= ml + 1e-9:
            min_saat = ts
    return {
        "max_fiyat": round(mh, 4),
        "min_fiyat": round(ml, 4),
        "max_%": round((mh / giris - 1) * 100, 2),
        "min_%": round((ml / giris - 1) * 100, 2),
        "max_saat": max_saat,
        "min_saat": min_saat,
    }


def compound_allin(rows):
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["tarih"]].append(r)
    cash = float(SERMAYE)
    for d in sorted(by_day.keys()):
        todays = by_day[d]
        poz = cash / len(todays)
        cash = sum(poz * (1 + t["getiri_%"] / 100) for t in todays)
    return cash


def verify_row(r: pd.Series) -> dict:
    hisse, tarih = r["hisse"], r["tarih"]
    tf, gun = gun_bars(hisse, tarih)
    hatalar = []

    if gun is None or len(gun) < 2:
        return {"tarih": tarih, "hisse": hisse, "durum": "FAIL", "hatalar": "intraday yok"}

    op = saatlik_acilis(hisse, tarih)
    giris_rapor = float(r["giris"])
    if op is not None and abs(op - giris_rapor) > 0.05:
        hatalar.append(f"giris rapor={giris_rapor} saatlik={op:.4f}")

    giris = op if op is not None else giris_rapor
    sebep, cikis, saat = simule_gun(gun, giris, TARGET, STOP)
    net = round((cikis / giris - 1 - RT) * 100, 2)
    mm = mfe_mae(gun, giris)

    if r["sebep"] != sebep:
        hatalar.append(f"sebep rapor={r['sebep']} sim={sebep}")
    if abs(float(r["cikis"]) - cikis) > TOL_CIKIS:
        hatalar.append(f"cikis rapor={r['cikis']} sim={round(cikis,4)}")
    if abs(float(r["getiri_%"]) - net) > TOL_GETIRI:
        hatalar.append(f"getiri rapor={r['getiri_%']} sim={net}")
    for k in ("max_%", "min_%", "max_fiyat", "min_fiyat"):
        if abs(float(r[k]) - mm[k]) > (0.15 if k.endswith("%") else 0.05):
            hatalar.append(f"{k} rapor={r[k]} sim={mm[k]}")

    return {
        "tarih": tarih, "hisse": hisse, "grup": r["grup"], "tf": tf,
        "giris": giris, "tp": round(giris * 1.03, 4), "sl": round(giris * 0.97, 4),
        "sebep": sebep, "cikis": round(cikis, 4), "cikis_saat": saat,
        "getiri_%": net, **mm,
        "durum": "PASS" if not hatalar else "FAIL",
        "hatalar": "; ".join(hatalar),
    }


def main():
    df = pd.read_csv("haziran_2026_dipkir.csv")
    print(f"Double-check: {len(df)} islem...", file=sys.stderr)
    rows = [verify_row(r) for _, r in df.iterrows()]
    out = pd.DataFrame(rows)
    out.to_csv("haziran_double_check.csv", index=False)

    fail = out[out["durum"] == "FAIL"]
    pass_n = (out["durum"] == "PASS").sum()

    # compound capraz
    sim_rows = out.to_dict("records")
    son = compound_allin(sim_rows)
    oz = pd.read_csv("haziran_2026_ozet.csv")
    rapor_son = float(oz[oz["grup"].str.contains("DIP")]["son_tl"].iloc[0])
    compound_ok = abs(son - rapor_son) < 50

    print("=" * 70)
    print("HAZIRAN DOUBLE-CHECK")
    print("=" * 70)
    print(f"PASS: {pass_n}/{len(out)}")
    print(f"Compound: sim={son:,.0f} rapor={rapor_son:,.0f} {'OK' if compound_ok else 'FAIL'}")
    if len(fail):
        print("\nFAIL satirlar:")
        print(fail[["tarih", "hisse", "hatalar"]].to_string(index=False))
    else:
        print("\nTum islemler dogrulandi.")
    print("\n-> haziran_double_check.csv")
    return 0 if len(fail) == 0 and compound_ok else 1


if __name__ == "__main__":
    sys.exit(main())
