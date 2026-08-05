"""2026 DIP+KIRILIM: bagimsiz double-check + gercekci compound senaryolari."""
from __future__ import annotations

import argparse
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
TOL_CIKIS = 0.05
TOL_GETIRI = 0.05


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


def compound_allin(rows, max_gunluk=None, key_sort=None):
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["tarih"]].append(r)
    cash = float(SERMAYE)
    gunluk = []
    for d in sorted(by_day.keys()):
        todays = sorted(by_day[d], key=key_sort or (lambda x: -x.get("kat", 0)))
        if max_gunluk and len(todays) > max_gunluk:
            todays = todays[:max_gunluk]
        poz = cash / len(todays)
        bas = cash
        cash = sum(poz * (1 + t["getiri_%"] / 100) for t in todays)
        gunluk.append({"tarih": d, "n": len(todays), "gun_%": (cash / bas - 1) * 100})
    return cash, pd.DataFrame(gunluk)


def verify_row(r: pd.Series) -> dict:
    hisse, tarih = r["hisse"], r["tarih"]
    tf, gun = gun_bars(hisse, tarih)
    hatalar = []

    if gun is None or len(gun) < 2:
        return {"tarih": tarih, "hisse": hisse, "durum": "NO_DATA", "hatalar": "intraday yok"}

    op = saatlik_acilis(hisse, tarih)
    giris_rapor = float(r["giris"])
    if op is not None and abs(op - giris_rapor) / max(giris_rapor, 0.01) > 0.005:
        hatalar.append(f"giris rapor={giris_rapor} saatlik={op:.4f}")

    giris = op if op is not None else giris_rapor
    sebep, cikis, saat = simule_gun(gun, giris, TARGET, STOP)
    net = round((cikis / giris - 1 - RT) * 100, 2)

    if r["sebep"] != sebep:
        hatalar.append(f"sebep rapor={r['sebep']} sim={sebep}")
    if abs(float(r["cikis"]) - cikis) > TOL_CIKIS:
        hatalar.append(f"cikis rapor={r['cikis']} sim={round(cikis,4)}")
    if abs(float(r["getiri_%"]) - net) > TOL_GETIRI:
        hatalar.append(f"getiri rapor={r['getiri_%']} sim={net}")

    return {
        "tarih": tarih, "hisse": hisse, "tf": tf,
        "giris_rapor": giris_rapor, "giris_sim": round(giris, 4),
        "sebep_rapor": r["sebep"], "sebep_sim": sebep,
        "getiri_rapor": r["getiri_%"], "getiri_sim": net,
        "durum": "PASS" if not hatalar else "FAIL",
        "hatalar": "; ".join(hatalar),
        "kat": r["kat"],
        "getiri_%": net,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="yil_2026_dipkir.csv")
    p.add_argument("--onek", default="yil_2026")
    p.add_argument("--ornek", type=int, default=0, help="sadece ilk N islem (test)")
    a = p.parse_args()

    df = pd.read_csv(a.csv)
    if a.ornek:
        df = df.head(a.ornek)

    print(f"Double-check: {len(df)} islem...", file=sys.stderr)
    rows = []
    for i, (_, r) in enumerate(df.iterrows(), 1):
        rows.append(verify_row(r))
        if i % 50 == 0:
            print(f"  ... {i}/{len(df)}", file=sys.stderr)

    out = pd.DataFrame(rows)
    out.to_csv(f"{a.onek}_double_check.csv", index=False)

    pass_n = (out["durum"] == "PASS").sum()
    fail = out[out["durum"] == "FAIL"]
    nodata = out[out["durum"] == "NO_DATA"]

    # compound senaryolari (simule getirilerle)
    sim_ok = out[out["durum"].isin(["PASS", "FAIL"])].copy()
    sim_ok["getiri_%"] = sim_ok["getiri_sim"]

    rapor_son, _ = compound_allin(df.to_dict("records"))
    sim_son, _ = compound_allin(sim_ok.to_dict("records"))
    n1, _ = compound_allin(df.to_dict("records"), max_gunluk=1)
    n3, _ = compound_allin(df.to_dict("records"), max_gunluk=3)
    n5, _ = compound_allin(df.to_dict("records"), max_gunluk=5)

    oz = pd.read_csv(f"{a.onek}_ozet.csv")
    rapor_oz = float(oz[oz["grup"].str.contains("DIP")]["son_tl"].iloc[0])

    print("=" * 80)
    print(f"2026 DOUBLE-CHECK | {a.csv}")
    print("=" * 80)
    print(f"PASS: {pass_n}/{len(out)} | FAIL: {len(fail)} | NO_DATA: {len(nodata)}")
    print(f"\nCompound (100k baslangic):")
    print(f"  Rapor CSV:           {rapor_oz:>12,.0f} TL ({(rapor_oz/SERMAYE-1)*100:+.2f}%)")
    print(f"  Rapor yeniden:       {rapor_son:>12,.0f} TL ({(rapor_son/SERMAYE-1)*100:+.2f}%)")
    print(f"  Simule yeniden:      {sim_son:>12,.0f} TL ({(sim_son/SERMAYE-1)*100:+.2f}%)")
    print(f"  Max 1 islem/gun:     {n1:>12,.0f} TL ({(n1/SERMAYE-1)*100:+.2f}%)")
    print(f"  Max 3 islem/gun:     {n3:>12,.0f} TL ({(n3/SERMAYE-1)*100:+.2f}%)")
    print(f"  Max 5 islem/gun:     {n5:>12,.0f} TL ({(n5/SERMAYE-1)*100:+.2f}%)")

    if len(fail):
        print("\n## FAIL (ilk 20)")
        print(fail[["tarih", "hisse", "hatalar"]].head(20).to_string(index=False))

    giris_fail = out[out["hatalar"].str.contains("giris", na=False)]
    if len(giris_fail):
        print(f"\n## Giris fiyat farki: {len(giris_fail)}")
        print(giris_fail[["tarih", "hisse", "giris_rapor", "giris_sim", "hatalar"]].head(15).to_string(index=False))

    print(f"\n-> {a.onek}_double_check.csv")


if __name__ == "__main__":
    main()
